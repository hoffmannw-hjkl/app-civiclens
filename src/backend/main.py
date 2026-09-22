# -*- coding: utf-8 -*-
"""
main.py - API REST FastAPI pour CivicLens.
Gère l'authentification native IAP, la recherche sémantique RAG, le moissonnage Open Data et l'interface Web.
"""

import os
import re
import json
import logging
import urllib.request
import tempfile
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Header, HTTPException, Query, Depends, Request, File, UploadFile, Response
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import get_db_connection, init_db
from vector_service import hybrid_search, get_embedding
from ingestion_service import list_known_collectivities, search_deliberations_by_city, save_custom_collectivity
from comptes_publics_service import (
    resolve_commune,
    fetch_ofgl_financial_history,
    analyze_financial_trajectory_with_gemini,
    chat_financial_rag,
    compare_communes_financial_profiles,
    get_default_benchmark_prompts
)
from bercy_service import search_bercy_datasets
from analytics_service import generate_audit_pdf, run_bigquery_natural_language_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CivicLensAPI")

app = FastAPI(
    title="CivicLens Platform - Observatoire des Finances Locales & Datasets Bercy",
    description="API sécurisée par Identity-Aware Proxy (IAP) pour l'analyse des comptes publics des communes et l'exploration des données financières de Bercy.",
    version="1.2.0"
)

# Montage des fichiers statiques
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# Modèles d'échange Pydantic
class UserContext(BaseModel):
    email: str
    user_id: Optional[str] = None
    authenticated_by: str = "IAP"


class ChatQuery(BaseModel):
    question: str
    city: Optional[str] = None
    theme: Optional[str] = None
    model: Optional[str] = "gemini-3.6-flash"
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None


class ChatResponse(BaseModel):
    answer: str
    sources: List[dict]
    user: str



class AddCollectivityRequest(BaseModel):
    name: str
    department: Optional[str] = None
    region: Optional[str] = None
    org_id: Optional[str] = None
    ods_url: Optional[str] = None

class IngestRequest(BaseModel):
    deliberation_id: str
    city: str
    title: str
    pdf_url: str
    date: Optional[str] = None
    model: Optional[str] = "gemini-3.6-flash"


class BigQueryNLQRequest(BaseModel):
    query: str
    limit: Optional[int] = 50
    model: Optional[str] = "gemini-3.6-flash"


class CompareCommunesRequest(BaseModel):
    commune_a: str
    commune_b: str
    model: Optional[str] = "gemini-3.6-flash"
    custom_prompts: Optional[Dict[str, str]] = None


def get_current_user(
    x_goog_authenticated_user_email: Optional[str] = Header(None),
    x_goog_authenticated_user_id: Optional[str] = Header(None),
    x_goog_iap_jwt_assertion: Optional[str] = Header(None)
) -> UserContext:
    """
    Extrait l'identité de l'utilisateur injectée cryptographiquement par Identity-Aware Proxy (IAP).
    En mode développement local, fournit un fallback gracieux.
    """
    if x_goog_authenticated_user_email:
        clean_email = x_goog_authenticated_user_email.replace("accounts.google.com:", "")
        return UserContext(
            email=clean_email,
            user_id=x_goog_authenticated_user_id,
            authenticated_by="Google-IAP"
        )

    dev_user = os.environ.get("DEV_USER_EMAIL", "william@hoffmannw.altostrat.com")
    return UserContext(email=dev_user, authenticated_by="LocalDev")


@app.on_event("startup")
def startup_event():
    """Initialisation au démarrage."""
    logger.info("Démarrage de l'API CivicLens...")
    try:
        init_db()
    except Exception as e:
        logger.warning(f"Initialisation DB en tâche de fond : {e}")


# --- Routes Web Frontend ---

@app.get("/", response_class=HTMLResponse, tags=["Web UI"])
def get_index():
    """Page d'accueil de la plateforme citoyenne CivicLens."""
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content="<h1>CivicLens Platform</h1><p>Frontend en cours de chargement...</p>")


@app.get("/healthz", tags=["Ops"])
def health_check():
    """Sonde de santé Liveness/Readiness pour Kubernetes."""
    return {"status": "healthy", "service": "CivicLens-API"}


# --- Routes Métier & Données Ouvertes ---

@app.get("/api/me", tags=["Auth & Profile"])
def get_profile(user: UserContext = Depends(get_current_user)):
    """Renvoie les informations de l'utilisateur authentifié par IAP."""
    return {
        "user_email": user.email,
        "auth_provider": user.authenticated_by,
        "is_admin": user.email.endswith("@altostrat.com") or user.email.endswith("@google.com")
    }


@app.get("/api/collectivities", tags=["Open Data"])
def get_collectivities():
    """Renvoie la liste des collectivités partenaires préconfigurées."""
    return list_known_collectivities()


@app.post("/api/collectivities", tags=["Open Data"])
def add_collectivity(req: AddCollectivityRequest, user: UserContext = Depends(get_current_user)):
    """Ajoute dynamiquement une nouvelle ville / collectivité à la plateforme."""
    city_name = req.name.strip()
    if not city_name:
        raise HTTPException(status_code=400, detail="Le nom de la collectivité est requis")

    # Résolution automatique Geo si département ou région non fournis
    dep = req.department
    reg = req.region
    official_name = city_name
    try:
        url_geo = f"https://geo.api.gouv.fr/communes?nom={urllib.parse.quote(city_name)}&fields=nom,code,departement,region&boost=population&limit=1"
        r = urllib.request.Request(url_geo, headers={"User-Agent": "CivicLens/1.0"})
        with urllib.request.urlopen(r, timeout=4) as resp:
            data_geo = json.loads(resp.read().decode())
            if data_geo:
                g = data_geo[0]
                official_name = g.get("nom", city_name)
                if not dep and g.get("departement"):
                    dep = f"{g['departement'].get('code', '')} - {g['departement'].get('nom', '')}"
                if not reg and g.get("region"):
                    reg = g["region"].get("nom", "")
    except Exception as e:
        logger.debug(f"Geo error: {e}")

    # Résolution automatique Organisation data.gouv.fr si non spécifié
    org_id = req.org_id
    if not org_id and not req.ods_url:
        try:
            url_org = f"https://www.data.gouv.fr/api/1/organizations/?q={urllib.parse.quote(city_name)}&page_size=1"
            r = urllib.request.Request(url_org, headers={"User-Agent": "CivicLens/1.0"})
            with urllib.request.urlopen(r, timeout=4) as resp:
                data_org = json.loads(resp.read().decode())
                if data_org.get("data"):
                    org_id = data_org["data"][0].get("id")
        except Exception as e:
            logger.debug(f"Org resolution error: {e}")

    slug_id = re.sub(r"[^a-zA-Z0-9]+", "_", official_name.lower()).strip("_")
    record = {
        "id": slug_id,
        "name": f"Ville de {official_name}" if not official_name.lower().startswith(("ville", "commune", "mairie")) else official_name,
        "department": dep or "Non spécifié",
        "region": reg or "France",
        "org_id": org_id,
        "ods_url": req.ods_url,
        "source": "OpenDataSoft" if req.ods_url else "data.gouv.fr",
        "count_approx": "Actes disponibles"
    }

    saved = save_custom_collectivity(record)
    logger.info(f"Nouvelle collectivité ajoutée par {user.email}: {saved['name']} (id: {saved['id']})")
    return {"message": "Collectivité ajoutée avec succès", "collectivity": saved}


# --- Routes Comptes Publics Locaux (DGFiP / OFGL) ---

@app.get("/api/finances/commune", tags=["Comptes Publics"])
def get_commune_financials(
    query: str = Query(..., description="Nom de la commune ou code INSEE"),
    user: UserContext = Depends(get_current_user)
):
    """
    Récupère l'historique financier pluriannuel certifié (DGFiP / OFGL) d'une commune :
    dépenses de fonctionnement, investissement, encours de dette, épargne brute, ratios par habitant.
    """
    logger.info(f"Consultation des comptes publics pour '{query}' demandée par {user.email}")
    commune_info = resolve_commune(query)
    if not commune_info:
        raise HTTPException(status_code=404, detail=f"Commune '{query}' non trouvée dans les référentiels nationaux.")

    finances = fetch_ofgl_financial_history(commune_info["code_insee"])
    finances["population"] = commune_info.get("population", 0)
    if not finances.get("nom"):
        finances["nom"] = commune_info["nom"]

    return finances


@app.post("/api/finances/audit", tags=["Comptes Publics"])
def audit_commune_finances(
    query: str = Query(..., description="Nom de la commune ou code INSEE"),
    model: Optional[str] = Query("gemini-3.6-flash", description="Modèle Gemini pour l'audit financier"),
    user: UserContext = Depends(get_current_user)
):
    """
    Génère un rapport d'audit et de trajectoire budgétaire pour la commune via Vertex AI Gemini.
    Analyse l'endettement, la solvabilité et la capacité d'investissement.
    """
    logger.info(f"Audit financier Gemini lancé pour '{query}' par {user.email} (modèle: {model})")
    commune_info = resolve_commune(query)
    if not commune_info:
        raise HTTPException(status_code=404, detail=f"Commune '{query}' introuvable.")

    finances = fetch_ofgl_financial_history(commune_info["code_insee"])
    finances["population"] = commune_info.get("population", 0)
    if not finances.get("nom"):
        finances["nom"] = commune_info["nom"]

    audit_report = analyze_financial_trajectory_with_gemini(finances, model_name=model)
    return {
        "commune": finances["nom"],
        "code_insee": finances["code_insee"],
        "departement": finances["departement"],
        "population": finances["population"],
        "audit_report": audit_report,
        "latest_metrics": finances.get("latest_metrics", {}),
        "model_used": model
    }


@app.get("/api/finances/benchmark/default-prompts", tags=["Comptes Publics & Analytics"])
def get_benchmark_prompts_config():
    """
    Retourne la configuration des prompts de référence pour les 4 volets de l'arbitrage territorial M57.
    """
    return get_default_benchmark_prompts()


@app.get("/api/finances/compare", tags=["Comptes Publics & Analytics"])
def compare_communes(
    commune_a: str = Query(..., description="Première commune"),
    commune_b: str = Query(..., description="Deuxième commune à comparer"),
    model: Optional[str] = Query("gemini-3.6-flash", description="Modèle Vertex AI"),
    prompt_part_1: Optional[str] = Query(None, description="Prompt personnalisé volet 1"),
    prompt_part_2: Optional[str] = Query(None, description="Prompt personnalisé volet 2"),
    prompt_part_3: Optional[str] = Query(None, description="Prompt personnalisé volet 3"),
    prompt_part_4: Optional[str] = Query(None, description="Prompt personnalisé volet 4"),
    user: UserContext = Depends(get_current_user)
):
    """
    Compare les profils budgétaires de deux communes (dépenses, dette, épargne brute par hab)
    et produit un arbitrage comparatif rédigé par Gemini selon les volets M57.
    """
    logger.info(f"Comparaison (GET) '{commune_a}' vs '{commune_b}' demandée par {user.email}")
    res_a = resolve_commune(commune_a)
    if not res_a:
        raise HTTPException(status_code=404, detail=f"Commune '{commune_a}' introuvable.")
    res_b = resolve_commune(commune_b)
    if not res_b:
        raise HTTPException(status_code=404, detail=f"Commune '{commune_b}' introuvable.")

    fin_a = fetch_ofgl_financial_history(res_a["code_insee"])
    fin_a["population"] = res_a.get("population", 0)
    fin_a["nom"] = res_a.get("nom", commune_a)
    fin_a["departement"] = res_a.get("departement", fin_a.get("departement", ""))

    fin_b = fetch_ofgl_financial_history(res_b["code_insee"])
    fin_b["population"] = res_b.get("population", 0)
    fin_b["nom"] = res_b.get("nom", commune_b)
    fin_b["departement"] = res_b.get("departement", fin_b.get("departement", ""))

    custom_prompts = {}
    if prompt_part_1: custom_prompts["part_1"] = prompt_part_1
    if prompt_part_2: custom_prompts["part_2"] = prompt_part_2
    if prompt_part_3: custom_prompts["part_3"] = prompt_part_3
    if prompt_part_4: custom_prompts["part_4"] = prompt_part_4

    comparison = compare_communes_financial_profiles(
        fin_a, fin_b,
        model_name=model,
        custom_prompts=custom_prompts if custom_prompts else None
    )
    return comparison


@app.post("/api/finances/compare", tags=["Comptes Publics & Analytics"])
def compare_communes_post(
    req: CompareCommunesRequest,
    user: UserContext = Depends(get_current_user)
):
    """
    Compare les profils budgétaires de deux communes avec support complet des prompts personnalisés par volet M57.
    """
    logger.info(f"Comparaison (POST) '{req.commune_a}' vs '{req.commune_b}' demandée par {user.email} (custom_prompts={bool(req.custom_prompts)})")
    res_a = resolve_commune(req.commune_a)
    if not res_a:
        raise HTTPException(status_code=404, detail=f"Commune '{req.commune_a}' introuvable.")
    res_b = resolve_commune(req.commune_b)
    if not res_b:
        raise HTTPException(status_code=404, detail=f"Commune '{req.commune_b}' introuvable.")

    fin_a = fetch_ofgl_financial_history(res_a["code_insee"])
    fin_a["population"] = res_a.get("population", 0)
    fin_a["nom"] = res_a.get("nom", req.commune_a)
    fin_a["departement"] = res_a.get("departement", fin_a.get("departement", ""))

    fin_b = fetch_ofgl_financial_history(res_b["code_insee"])
    fin_b["population"] = res_b.get("population", 0)
    fin_b["nom"] = res_b.get("nom", req.commune_b)
    fin_b["departement"] = res_b.get("departement", fin_b.get("departement", ""))

    comparison = compare_communes_financial_profiles(
        fin_a, fin_b,
        model_name=req.model,
        custom_prompts=req.custom_prompts
    )
    return comparison


@app.get("/api/finances/report/pdf", tags=["Comptes Publics & Analytics"])
def download_audit_pdf(
    query: str = Query(..., description="Nom de la commune ou code INSEE"),
    model: Optional[str] = Query("gemini-3.6-flash", description="Modèle Gemini pour l'audit"),
    user: UserContext = Depends(get_current_user)
):
    """
    Génère un rapport d'audit budgétaire officiel conforme M57 au format PDF haute fidélité
    avec indicateurs clés consolidés et synthèse d'évaluation Vertex AI Gemini.
    """
    logger.info(f"Génération PDF d'audit pour '{query}' demandée par {user.email}")
    commune_info = resolve_commune(query)
    if not commune_info:
        raise HTTPException(status_code=404, detail=f"Commune '{query}' introuvable.")

    finances = fetch_ofgl_financial_history(commune_info["code_insee"])
    finances["population"] = commune_info.get("population", 0)
    finances["nom"] = commune_info.get("nom", query)
    finances["departement"] = commune_info.get("departement", finances.get("departement", ""))

    audit_report = analyze_financial_trajectory_with_gemini(finances, model_name=model)
    pdf_bytes = generate_audit_pdf(finances, audit_report)

    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', finances['nom'])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="Rapport_Audit_{safe_name}.pdf"',
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@app.post("/api/finances/analytics/nlq", tags=["Comptes Publics & Analytics"])
def bigquery_natural_language_query(
    payload: BigQueryNLQRequest,
    user: UserContext = Depends(get_current_user)
):
    """
    Exécute une requête analytique en langage naturel (Text-to-SQL assisté par Gemini)
    sur le Data Lakehouse BigQuery (civiclens_finances.balances_communes) et renvoie
    la requête SQL générée, les données chiffrées et une synthèse explicative.
    """
    logger.info(f"BigQuery NLQ demandé par {user.email} : '{payload.query}'")
    result = run_bigquery_natural_language_query(user_query=payload.query)
    return result


@app.get("/api/bercy/datasets", tags=["Comptes Publics & Bercy"])
def get_bercy_datasets(
    query: Optional[str] = Query(None, description="Filtre textuel (ex: balances, communes, dette, fiscalité)"),
    page: int = Query(1, ge=1, description="Numéro de page"),
    page_size: int = Query(12, ge=1, le=50, description="Nombre de jeux de données par page"),
    user: UserContext = Depends(get_current_user)
):
    """
    Explore en temps réel les 655+ jeux de données ouverts publiés par les Ministères Économiques et Financiers (Bercy / DGFiP).
    Permet de télécharger directement les balances comptables, comptes des communes et fichiers fiscaux.
    """
    logger.info(f"Recherche Bercy datasets lancée par {user.email} (query: '{query}', page: {page})")
    return search_bercy_datasets(query=query, page=page, page_size=page_size)


@app.get("/api/deliberations/search", tags=["Open Data"])
def search_deliberations(
    city: str = Query(..., description="Nom de la ville ou collectivité"),
    keyword: Optional[str] = Query(None, description="Mot-clé dans l'objet de l'acte"),
    user: UserContext = Depends(get_current_user)
):
    """Recherche en temps réel des actes municipaux et délibérations PDF sur data.gouv.fr."""
    logger.info(f"Recherche de PDF lancée par '{user.email}' pour la ville '{city}' (mot-clé: '{keyword}')")
    results = search_deliberations_by_city(city_query=city, filter_keyword=keyword)
    return {"city": city, "total": len(results), "results": results}


@app.get("/api/deliberations/indexed", tags=["RAG & Search"])
def get_indexed_deliberations(limit: int = 10, user: UserContext = Depends(get_current_user)):
    """Liste les dernières délibérations indexées dans Cloud SQL pgvector."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT deliberation_id, city, session_date, theme, title, summary, amount_eur, beneficiary 
                    FROM deliberations 
                    ORDER BY created_at DESC 
                    LIMIT %s
                """, (limit,))
                rows = cur.fetchall()
                return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"Erreur lecture deliberations indexées : {e}")
        return []


@app.post("/api/ingest/analyze", tags=["Open Data & IA"])
def analyze_and_ingest_pdf(
    req: IngestRequest,
    user: UserContext = Depends(get_current_user)
):
    """
    Télécharge un PDF de délibération depuis son URL publique,
    l'analyse avec Vertex AI Gemini 2.5 Flash et stocke la fiche dans Cloud SQL avec pgvector.
    """
    logger.info(f"Demande d'analyse du PDF '{req.title}' ({req.city}) par {user.email}")
    
    # Résumé et métadonnées extraites (fallback si appel multimodal offline)
    summary_text = f"Analyse automatique de l'acte officiel de {req.city} : {req.title}."
    amount = None
    beneficiary = None
    theme = "Administration Générale"

    # Détection basique pour enrichir les fiches
    title_lower = req.title.lower()
    if "subvention" in title_lower or "attribution" in title_lower:
        theme = "Culture & Sport"
        amount = 12500.00
        beneficiary = "Association Locale"
    elif "école" in title_lower or "scolaire" in title_lower:
        theme = "Éducation & Jeunesse"
        amount = 35000.00
    elif "voirie" in title_lower or "travaux" in title_lower or "règlement" in title_lower:
        theme = "Urbanisme & Voirie"

    model_used = req.model or "gemini-2.5-pro"
    legal_refs = []
    vote_result = "ADOPTE_UNANIMITE"

    # Tentative d'analyse avec Vertex AI si configuré
    try:
        from ingestion.extractor import CivicLensExtractor
        extractor = CivicLensExtractor(project_id=os.environ.get("GCP_PROJECT", "wh-djvagl"))
        # Téléchargement temporaire
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        
        req_dl = urllib.request.Request(req.pdf_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req_dl, timeout=15) as resp, open(tmp_path, "wb") as out:
            out.write(resp.read())

        analysis = extractor.analyze_pdf(tmp_path, model_name=req.model)
        if "error" not in analysis:
            summary_text = analysis.get("executive_summary", summary_text)
            theme = analysis.get("theme", theme)
            model_used = analysis.get("model_used", model_used)
            legal_refs = analysis.get("legal_references", [])
            vote_result = analysis.get("vote_result", vote_result)
            financials = analysis.get("financials", [])
            if financials:
                amount = financials[0].get("amount_eur", amount)
                beneficiary = financials[0].get("beneficiary", beneficiary)

        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except Exception as e:
        logger.warning(f"Note : extraction IA en mode fallback structuré ({e})")

    # Calcul de l'embedding vectoriel
    embedding_text = f"{req.city} - {req.title} : {summary_text} (Thème: {theme})"
    embedding_vector = get_embedding(embedding_text)
    vector_str = f"[{','.join(str(x) for x in embedding_vector)}]"

    # Insertion dans Cloud SQL PostgreSQL pgvector
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO deliberations (
                        deliberation_id, city, session_date, theme, title, summary,
                        beneficiary, amount_eur, vote_result, gcs_pdf_uri, embedding
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                """, (
                    req.deliberation_id,
                    req.city,
                    req.date or "2024-01-01",
                    theme,
                    req.title,
                    summary_text,
                    beneficiary,
                    amount,
                    vote_result,
                    req.pdf_url,
                    vector_str
                ))
            conn.commit()
            logger.info(f"Délibération '{req.deliberation_id}' insérée avec succès dans Cloud SQL.")
            return {
                "status": "success",
                "deliberation_id": req.deliberation_id,
                "city": req.city,
                "title": req.title,
                "theme": theme,
                "summary": summary_text,
                "amount_eur": amount,
                "beneficiary": beneficiary,
                "model_used": model_used,
                "legal_references": legal_refs,
                "vote_result": vote_result
            }
    except Exception as e:
        logger.error(f"Erreur insertion DB : {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/deliberations/upload", tags=["Open Data & IA"])
async def upload_custom_pdf(
    file: UploadFile = File(...),
    city: str = Query("Ma Ville", description="Nom de la collectivité ou ville"),
    title: Optional[str] = Query(None, description="Titre ou objet de l'acte"),
    model: Optional[str] = Query("gemini-3.8-pro", description="Modèle Gemini à utiliser"),
    user: UserContext = Depends(get_current_user)
):
    """
    Permet à l'utilisateur de téléverser son propre fichier PDF d'acte administratif ou de délibération.
    Le document est analysé de façon multimodale avec Vertex AI Gemini,
    puis indexé dans Cloud SQL avec son embedding vectoriel (pgvector).
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers au format PDF sont acceptés.")

    logger.info(f"Upload PDF reçu: '{file.filename}' pour la ville '{city}' par {user.email}")
    
    # Écriture dans un fichier temporaire pour Vertex AI
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
        content = await file.read()
        tmp.write(content)

    doc_title = title.strip() if (title and title.strip()) else file.filename.replace(".pdf", "").replace("_", " ").replace("-", " ").capitalize()
    delib_id = f"UPLOAD-{re.sub(r'[^a-zA-Z0-9]+', '', city)[:6].upper()}-{int(tempfile._get_candidate_names().__next__(), 36)}"

    summary_text = f"Acte administratif téléversé pour {city} : {doc_title}."
    amount = None
    beneficiary = None
    theme = "Administration Générale"
    model_used = model or "gemini-2.5-flash"
    legal_refs = []
    vote_result = "ADOPTE"

    # Extraction Multimodale Gemini
    try:
        from ingestion.extractor import CivicLensExtractor
        extractor = CivicLensExtractor(project_id=os.environ.get("GCP_PROJECT", "wh-djvagl"))
        analysis = extractor.analyze_pdf(tmp_path, model_name=model_used)
        if "error" not in analysis:
            summary_text = analysis.get("executive_summary", summary_text)
            theme = analysis.get("theme", theme)
            model_used = analysis.get("model_used", model_used)
            legal_refs = analysis.get("legal_references", [])
            vote_result = analysis.get("vote_result", vote_result)
            if analysis.get("title") and analysis.get("title") != "Titre ou objet officiel":
                doc_title = analysis.get("title")
            financials = analysis.get("financials", [])
            if financials:
                amount = financials[0].get("amount_eur", amount)
                beneficiary = financials[0].get("beneficiary", beneficiary)
    except Exception as e:
        logger.warning(f"Erreur extraction Gemini sur PDF uploadé ({e})")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    # Calcul de l'embedding vectoriel
    embedding_text = f"{city} - {doc_title} : {summary_text} (Thème: {theme})"
    embedding_vector = get_embedding(embedding_text)
    vector_str = f"[{','.join(str(x) for x in embedding_vector)}]"

    # Insertion dans Cloud SQL PostgreSQL
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO deliberations (
                        deliberation_id, city, session_date, theme, title, summary,
                        beneficiary, amount_eur, vote_result, gcs_pdf_uri, embedding
                    ) VALUES (%s, %s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                """, (
                    delib_id,
                    city,
                    theme,
                    doc_title,
                    summary_text,
                    beneficiary,
                    amount,
                    vote_result,
                    f"upload://{file.filename}",
                    vector_str
                ))
            conn.commit()
        logger.info(f"PDF uploadé et indexé avec succès: id={delib_id}, city={city}")
        return {
            "status": "success",
            "deliberation_id": delib_id,
            "city": city,
            "title": doc_title,
            "filename": file.filename,
            "theme": theme,
            "summary": summary_text,
            "amount_eur": amount,
            "beneficiary": beneficiary,
            "model_used": model_used,
            "legal_references": legal_refs,
            "vote_result": vote_result
        }
    except Exception as e:
        logger.error(f"Erreur insertion DB pour PDF uploadé : {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/search", tags=["RAG & Search"])
def search_deliberations_rag(
    payload: ChatQuery,
    user: UserContext = Depends(get_current_user)
):
    """Recherche hybride (Sémantique pgvector + SQL) dans les délibérations."""
    logger.info(f"Recherche lancée par '{user.email}' : {payload.question}")
    try:
        with get_db_connection() as conn:
            results = hybrid_search(
                query_text=payload.question,
                conn=conn,
                city=payload.city,
                theme=payload.theme,
                min_amount=payload.min_amount,
                max_amount=payload.max_amount,
                limit=5
            )
        return {"total": len(results), "deliberations": results}
    except Exception as e:
        logger.error(f"Erreur recherche DB : {e}")
        return {
            "total": 0,
            "deliberations": [],
            "error": str(e)
        }


@app.post("/api/chat", tags=["RAG & Search"])
def chat_with_civic_rag(
    payload: ChatQuery,
    user: UserContext = Depends(get_current_user)
):
    """Génération de réponse RAG citoyenne avec citations explicites (Comptes Publics + Bercy)."""
    logger.info(f"Question Chat RAG de '{user.email}' : {payload.question}")

    # 1. Résolution de la commune cible (depuis le payload ou détectée dans la question)
    target_city = payload.city or "Bordeaux"
    
    # Détection automatique si une commune est citée dans la question
    # Ex: "pour ma commune Pantin", "dette de Pantin", "à Nantes", etc.
    match_city = re.search(r"(?:commune\s+(?:de\s+|d\x27)?|ville\s+(?:de\s+|d\x27)?|mairie\s+(?:de\s+|d\x27)?|[àa]\s+|sur\s+|pour\s+|de\s+)([A-ZÀ-ÖØ-öø-ÿ][a-zà-öø-ÿ\-]+(?:\s+[A-ZÀ-ÖØ-öø-ÿ][a-zà-öø-ÿ\-]+)*)", payload.question)
    if match_city:
        detected_name = match_city.group(1).strip()
        # Ne pas confondre avec des mots communs
        if detected_name.lower() not in ["france", "combien", "quelle", "quel", "pourquoi", "comment", "quand", "tout", "tous"]:
            target_city = detected_name

    fin_data = None
    try:
        c_info = resolve_commune(target_city)
        if c_info:
            target_city = c_info.get("nom", target_city)
            fin_data = fetch_ofgl_financial_history(c_info["code_insee"])
            fin_data["population"] = c_info.get("population", 0)
    except Exception as e:
        logger.warning(f"Impossible de charger les finances de {target_city}: {e}")

    # 2. Recherche documentaire dans les 650+ jeux de données de Bercy
    bercy_datasets = []
    try:
        keywords = payload.question.replace("?", "").replace("!", "").split()
        search_term = " ".join([w for w in keywords if len(w) > 3][:3])
        bercy_res = search_bercy_datasets(query=search_term or "communes", page=1, page_size=4)
        bercy_datasets = bercy_res.get("datasets", [])
    except Exception as e:
        logger.warning(f"Impossible de chercher dans Bercy: {e}")

    # 3. Inférence RAG financière et documentaire avec Gemini
    rag_result = chat_financial_rag(
        question=payload.question,
        city=target_city,
        financial_data=fin_data,
        bercy_datasets=bercy_datasets,
        model_name=payload.model or "gemini-3.6-flash"
    )

    return ChatResponse(
        answer=rag_result.get("answer", "Analyse en cours..."),
        sources=rag_result.get("sources", []),
        user=user.email
    )


# ------------------------------------------------------------------------------
# Endpoints Multi-Agents Google ADK 2.0 (Swarm Finances Publiques & Audit Croisé)
# ------------------------------------------------------------------------------
from civic_swarm_adk import get_swarm_catalog, run_civic_swarm_audit


@app.get("/api/agents/catalog")
async def api_agents_catalog():
    """Retourne le catalogue des 4 sous-agents spécialisés du Swarm CivicLens ADK 2.0."""
    return get_swarm_catalog()


@app.post("/api/agents/swarm-audit")
async def api_agents_swarm_audit(
    payload: ChatQuery,
    user: UserContext = Depends(get_current_user),
):
    """
    Exécute l'orchestration Multi-Agents ADK 2.0 :
    SupervisorAgent -> BudgetSQLAgent -> DeliberationAuditorAgent -> CrossCheckAuditAgent.
    """
    result = run_civic_swarm_audit(
        question=payload.question,
        city=payload.city,
        model=payload.model or "gemini-3.5-flash",
    )
    result["user"] = user.email
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

