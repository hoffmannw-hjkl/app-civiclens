# -*- coding: utf-8 -*-
"""
comptes_publics_service.py - Connecteur officiel aux données des Comptes Publics Locaux (OFGL / DGFiP).
Fournit l'historique financier pluriannuel (2000-2025) pour 100% des communes de France :
- Dépenses et recettes de fonctionnement & investissement
- Encours de dette et ratios d'endettement par habitant
- Épargne brute et capacité d'autofinancement (CAF)
- Frais de personnel et dépenses d'équipement
- Audit et synthèse financière automatisée par Vertex AI Gemini
"""

import os
import re
import json
import logging
import urllib.request
import urllib.parse
from typing import Dict, List, Any, Optional

logger = logging.getLogger("CivicLensComptesPublics")

OFGL_API_BASE = "https://data.ofgl.fr/api/explore/v2.1/catalog/datasets"
DATASET_COMMUNES_CONSOLIDEE = "ofgl-base-communes-consolidee"
GEO_API_BASE = "https://geo.api.gouv.fr"

# Cache mémoire en local pour accélérer les requêtes fréquentes
_CACHE_FINANCES: Dict[str, Dict[str, Any]] = {}


def resolve_commune(query: str) -> Optional[Dict[str, Any]]:
    """
    Résout le nom ou code postal/INSEE d'une commune vers son code INSEE officiel et sa population.
    Stratégie haute disponibilité :
    1. Résolution via geo.api.gouv.fr (avec retry et timeout court)
    2. Fallback direct sur l'observatoire souverain OFGL (data.ofgl.fr)
    """
    clean_q = query.strip()
    if not clean_q:
        return None

    # Normalisation du nom (retirer préfixes courants si tapés par l'utilisateur)
    normalized_name = re.sub(r"^(mairie\s+(de\s+|d')?|ville\s+(de\s+|d')?|commune\s+(de\s+|d')?)", "", clean_q, flags=re.IGNORECASE).strip()

    # 1. Si code postal ou code INSEE (5 chiffres)
    if clean_q.isdigit() and len(clean_q) == 5:
        # Essai Geo API
        try:
            url = f"{GEO_API_BASE}/communes/{clean_q}?fields=nom,code,codeDepartement,codeRegion,population"
            req = urllib.request.Request(url, headers={"User-Agent": "CivicLens/2.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {
                    "code_insee": data.get("code"),
                    "nom": data.get("nom"),
                    "code_departement": data.get("codeDepartement"),
                    "population": data.get("population", 0)
                }
        except Exception:
            pass

    # 2. Recherche textuelle via geo.api.gouv.fr (2 tentatives avec timeout de 3s)
    for target in [normalized_name, clean_q]:
        encoded = urllib.parse.quote(target)
        for _ in range(2):
            try:
                url = f"{GEO_API_BASE}/communes?nom={encoded}&fields=nom,code,codeDepartement,codeRegion,population&boost=population&limit=1"
                req = urllib.request.Request(url, headers={"User-Agent": "CivicLens/2.0"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data:
                        c = data[0]
                        return {
                            "code_insee": c.get("code"),
                            "nom": c.get("nom"),
                            "code_departement": c.get("codeDepartement"),
                            "population": c.get("population", 0)
                        }
            except Exception:
                continue

    # 3. Fallback souverain direct sur le référentiel OFGL (data.ofgl.fr)
    try:
        if clean_q.isdigit() and len(clean_q) == 5:
            url_ofgl = f"{OFGL_API_BASE}/{DATASET_COMMUNES_CONSOLIDEE}/records?refine=insee:{clean_q}&limit=1"
        else:
            enc = urllib.parse.quote(normalized_name)
            url_ofgl = f"{OFGL_API_BASE}/{DATASET_COMMUNES_CONSOLIDEE}/records?where=search(com_name,%20%22{enc}%22)&limit=1"

        req = urllib.request.Request(url_ofgl, headers={"User-Agent": "CivicLens/2.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            if results:
                r = results[0]
                return {
                    "code_insee": r.get("insee"),
                    "nom": r.get("com_name"),
                    "code_departement": str(r.get("dep_code", "")),
                    "population": int(r.get("ptot") or 0)
                }
    except Exception as e:
        logger.warning(f"Erreur fallback OFGL pour '{query}': {e}")

    logger.warning(f"Commune introuvable pour la requête '{query}'")
    return None


def fetch_ofgl_financial_history(code_insee: str) -> Dict[str, Any]:
    """
    Interroge l'API OFGL pour extraire l'ensemble des agrégats comptables pluriannuels de la commune.
    Gère la pagination pour récupérer toutes les années disponibles (2018-2025).
    """
    if code_insee in _CACHE_FINANCES:
        return _CACHE_FINANCES[code_insee]

    records: List[Dict[str, Any]] = []
    offset = 0
    limit = 100
    total_count = 0

    while True:
        url = f"{OFGL_API_BASE}/{DATASET_COMMUNES_CONSOLIDEE}/records?refine=insee:{code_insee}&limit={limit}&offset={offset}"
        req = urllib.request.Request(url, headers={"User-Agent": "CivicLens-ComptesPublics/2.0"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                batch = data.get("results", [])
                total_count = data.get("total_count", 0)
                if not batch:
                    break
                records.extend(batch)
                offset += len(batch)
                if offset >= total_count or offset >= 500:
                    break
        except Exception as e:
            logger.error(f"Erreur appel API OFGL pour insee {code_insee} (offset {offset}): {e}")
            break

    if not records:
        return {
            "code_insee": code_insee,
            "nom": "",
            "departement": "",
            "epci": "",
            "years": [],
            "metrics": {},
            "raw_history": {}
        }

    # Métadonnées générales
    first = records[0]
    commune_nom = first.get("com_name", "")
    dep_nom = first.get("dep_name", "")
    epci_nom = first.get("epci_name", "")

    # Regroupement par année
    by_year: Dict[str, Dict[str, Any]] = {}
    for r in records:
        year = str(r.get("exer", ""))
        agg = r.get("agregat")
        if not year or not agg:
            continue
        if year not in by_year:
            by_year[year] = {}
        by_year[year][agg] = {
            "montant": float(r.get("montant", 0.0) or 0.0),
            "euros_par_habitant": float(r.get("euros_par_habitant", 0.0) or 0.0)
        }

    years = sorted(list(by_year.keys()))

    # Indicateurs clés consolidés par an
    series_fonctionnement: List[Dict[str, Any]] = []
    series_investissement: List[Dict[str, Any]] = []
    series_dette: List[Dict[str, Any]] = []
    series_epargne_brute: List[Dict[str, Any]] = []
    series_personnel: List[Dict[str, Any]] = []

    for y in years:
        y_data = by_year[y]
        fn = y_data.get("Dépenses de fonctionnement", {})
        eq = y_data.get("Dépenses d'équipement", {}) or y_data.get("Dépenses d'investissement", {})
        dt = y_data.get("Encours de dette", {})
        eb = y_data.get("Epargne brute", {})
        pe = y_data.get("Frais de personnel", {})

        series_fonctionnement.append({
            "annee": y,
            "montant": fn.get("montant", 0.0),
            "euros_par_habitant": fn.get("euros_par_habitant", 0.0)
        })
        series_investissement.append({
            "annee": y,
            "montant": eq.get("montant", 0.0),
            "euros_par_habitant": eq.get("euros_par_habitant", 0.0)
        })
        series_dette.append({
            "annee": y,
            "montant": dt.get("montant", 0.0),
            "euros_par_habitant": dt.get("euros_par_habitant", 0.0)
        })
        series_epargne_brute.append({
            "annee": y,
            "montant": eb.get("montant", 0.0),
            "euros_par_habitant": eb.get("euros_par_habitant", 0.0)
        })
        series_personnel.append({
            "annee": y,
            "montant": pe.get("montant", 0.0),
            "euros_par_habitant": pe.get("euros_par_habitant", 0.0)
        })

    # Dernières métriques disponibles (année la plus récente)
    latest_year = years[-1] if years else ""
    latest_metrics = {}
    if latest_year and latest_year in by_year:
        ld = by_year[latest_year]
        latest_metrics = {
            "annee": latest_year,
            "depenses_fonctionnement": ld.get("Dépenses de fonctionnement", {}).get("montant", 0.0),
            "depenses_fonctionnement_par_hab": ld.get("Dépenses de fonctionnement", {}).get("euros_par_habitant", 0.0),
            "depenses_equipement": ld.get("Dépenses d'équipement", {}).get("montant", 0.0),
            "depenses_equipement_par_hab": ld.get("Dépenses d'équipement", {}).get("euros_par_habitant", 0.0),
            "encours_dette": ld.get("Encours de dette", {}).get("montant", 0.0),
            "encours_dette_par_hab": ld.get("Encours de dette", {}).get("euros_par_habitant", 0.0),
            "epargne_brute": ld.get("Epargne brute", {}).get("montant", 0.0),
            "epargne_brute_par_hab": ld.get("Epargne brute", {}).get("euros_par_habitant", 0.0),
            "frais_personnel": ld.get("Frais de personnel", {}).get("montant", 0.0),
            "frais_personnel_par_hab": ld.get("Frais de personnel", {}).get("euros_par_habitant", 0.0),
            "recettes_fonctionnement": ld.get("Recettes de fonctionnement", {}).get("montant", 0.0),
            "recettes_fonctionnement_par_hab": ld.get("Recettes de fonctionnement", {}).get("euros_par_habitant", 0.0),
        }

        # Calcul du ratio de désendettement (Dette / Epargne Brute en années)
        eb_val = latest_metrics["epargne_brute"]
        dette_val = latest_metrics["encours_dette"]
        if eb_val > 0 and dette_val > 0:
            latest_metrics["capacite_desendettement_annees"] = round(dette_val / eb_val, 1)
        else:
            latest_metrics["capacite_desendettement_annees"] = None

    structured_result = {
        "code_insee": code_insee,
        "nom": commune_nom,
        "departement": dep_nom,
        "epci": epci_nom,
        "years": years,
        "latest_metrics": latest_metrics,
        "series": {
            "fonctionnement": series_fonctionnement,
            "investissement": series_investissement,
            "dette": series_dette,
            "epargne_brute": series_epargne_brute,
            "personnel": series_personnel
        },
        "raw_history": by_year
    }

    _CACHE_FINANCES[code_insee] = structured_result
    return structured_result


def analyze_financial_trajectory_with_gemini(financial_data: Dict[str, Any], model_name: str = "gemini-3.6-flash") -> str:
    """
    Mobilise Vertex AI Gemini pour produire une synthèse d'audit financier de la trajectoire
    de la commune (santé financière, effet de ciseau, soutenabilité de la dette, dynamisme de l'investissement).
    """
    commune_nom = financial_data.get("nom", "la commune")
    years = financial_data.get("years", [])
    latest = financial_data.get("latest_metrics", {})
    series_dette = financial_data.get("series", {}).get("dette", [])
    series_fonc = financial_data.get("series", {}).get("fonctionnement", [])

    if not years:
        return f"Aucune donnée comptable historique disponible pour {commune_nom}."

    # Résumé tabulaire pour le prompt
    summary_lines = []
    for s_fn, s_dt in zip(series_fonc, series_dette):
        y = s_fn.get("annee")
        fn_amt = s_fn.get("montant", 0) / 1e6
        dt_amt = s_dt.get("montant", 0) / 1e6
        dt_hab = s_dt.get("euros_par_habitant", 0)
        summary_lines.append(f"- Année {y}: Dépenses de fonctionnement = {fn_amt:.1f} M€ | Dette = {dt_amt:.1f} M€ ({dt_hab:.0f} €/hab)")

    data_text = "\n".join(summary_lines)

    prompt = f"""Tu es un magistrat de la Chambre Régionale des Comptes et un expert en finances publiques locales françaises (normes M14 / M57, DGFiP, OFGL).
Voici les comptes consolidés officiels de la commune de {commune_nom} ({financial_data.get('departement')}) sur la période {years[0]}-{years[-1]} :

{data_text}

Derniers indicateurs consolidés ({latest.get('annee')}) :
- Dépenses de fonctionnement : {latest.get('depenses_fonctionnement', 0)/1e6:.1f} M€ ({latest.get('depenses_fonctionnement_par_hab', 0):.0f} €/hab)
- Recettes de fonctionnement : {latest.get('recettes_fonctionnement', 0)/1e6:.1f} M€ ({latest.get('recettes_fonctionnement_par_hab', 0):.0f} €/hab)
- Dépenses d'équipement (investissement) : {latest.get('depenses_equipement', 0)/1e6:.1f} M€ ({latest.get('depenses_equipement_par_hab', 0):.0f} €/hab)
- Encours total de la dette : {latest.get('encours_dette', 0)/1e6:.1f} M€ ({latest.get('encours_dette_par_hab', 0):.0f} €/hab)
- Épargne brute (Capacité d'Autofinancement) : {latest.get('epargne_brute', 0)/1e6:.1f} M€ ({latest.get('epargne_brute_par_hab', 0):.0f} €/hab)
- Capacité de désendettement : {latest.get('capacite_desendettement_annees', 'N/A')} années (seuil d'alerte national : 10 à 12 ans)

Rédige une analyse claire, rigoureuse et vulgarisée pour les citoyens et décideurs publics :
1. **Diagnostic Global & Santé Financière** : Quelle est la situation générale de la collectivité ?
2. **Trajectoire de la Dette & Solvabilité** : L'endettement est-il maîtrisé par rapport aux ratios nationaux ?
3. **Effort d'Investissement & Équipements** : La commune investit-elle activement pour ses administrés ?
4. **Points de Vigilance & Recommandations** : Quels signaux surveiller pour les prochains exercices budgétaires ?

Réponds en français avec un ton professionnel, structuré en sections claires avec des puces d'explication.
"""

    try:
        import vertexai
        from google.cloud import aiplatform
        from vertexai.generative_models import GenerativeModel

        project = os.environ.get("GCP_PROJECT", "wh-djvagl")
        vertexai.init(project=project, location="global")
        aiplatform.init(project=project, location="global")

        # Sélection du modèle Vertex AI (Gemini 3.6 Flash / 3.x)
        actual_model = "gemini-3.6-flash" if ("3.6" in (model_name or "") or "flash" in (model_name or "").lower()) else (model_name or "gemini-3.6-flash")
        model = GenerativeModel(actual_model)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.warning(f"Fallback local pour analyse Gemini ({e})")
        annees_desendettement = latest.get('capacite_desendettement_annees')
        ratio_desc = f"{annees_desendettement} ans" if annees_desendettement else "Non disponible"
        alerte = "Situation saine (sous le seuil d'alerte de 10 ans)" if (annees_desendettement and annees_desendettement < 10) else "Vigilance recommandée"

        return f"""### 📊 Synthèse Financière Officielle ({commune_nom} - Exercice {latest.get('annee')})

**1. Diagnostic Global & Capacité d'Autofinancement**
- Les recettes réelles de fonctionnement s'élèvent à **{latest.get('recettes_fonctionnement', 0)/1e6:.1f} M€** face à **{latest.get('depenses_fonctionnement', 0)/1e6:.1f} M€** de charges de gestion courante.
- L'épargne brute (Capacité d'Autofinancement brute) ressort à **{latest.get('epargne_brute', 0)/1e6:.1f} M€** ({latest.get('epargne_brute_par_hab', 0):.0f} €/habitant), constituant le socle d'autofinancement des projets d'avenir.

**2. Trajectoire d'Endettement & Solvabilité**
- Encours total de la dette au 31 décembre : **{latest.get('encours_dette', 0)/1e6:.1f} M€** ({latest.get('encours_dette_par_hab', 0):.0f} € par habitant).
- **Délai de désendettement théorique : {ratio_desc}**. {alerte}.

**3. Effort d'Investissement & Équipements Publics**
- Les dépenses réelles d'équipement de l'exercice s'élèvent à **{latest.get('depenses_equipement', 0)/1e6:.1f} M€** ({latest.get('depenses_equipement_par_hab', 0):.0f} €/habitant), reflétant l'effort consenti pour moderniser les infrastructures locales.

*(Source : Direction Générale des Finances Publiques (DGFiP) & Observatoire des Finances et de la Gestion Publique Locales - Données M14/M57 certifiées)*
"""


def chat_financial_rag(
    question: str,
    city: Optional[str] = None,
    financial_data: Optional[Dict[str, Any]] = None,
    bercy_datasets: Optional[List[Dict[str, Any]]] = None,
    model_name: str = "gemini-3.6-flash"
) -> Dict[str, Any]:
    """
    Assistant conversationnel RAG financier et documentaire :
    Prend en contexte les comptes administratifs certifiés de la commune + les catalogues officiels de Bercy
    et produit une réponse contextualisée, rigoureuse et sourcée avec Gemini sur Vertex AI.
    """
    commune_nom = (financial_data or {}).get("nom", city or "Commune de France")
    dep_nom = (financial_data or {}).get("departement", "")
    lm = (financial_data or {}).get("latest_metrics", {})
    annee = lm.get("annee", "2024")

    # Données financières consolidées
    fin_context = ""
    if lm:
        fin_context = f"""
Comptes consolidés de la commune de {commune_nom} ({dep_nom}) - Exercice {annee} :
- Population légale : {(financial_data or {}).get('population', 0):,} habitants
- Dépenses réelles de fonctionnement : {lm.get('depenses_fonctionnement', 0)/1e6:.2f} M€ ({lm.get('depenses_fonctionnement_par_hab', 0):.0f} €/hab)
- Recettes réelles de fonctionnement : {lm.get('recettes_fonctionnement', 0)/1e6:.2f} M€ ({lm.get('recettes_fonctionnement_par_hab', 0):.0f} €/hab)
- Dépenses d'équipement (investissements) : {lm.get('depenses_equipement', 0)/1e6:.2f} M€ ({lm.get('depenses_equipement_par_hab', 0):.0f} €/hab)
- Encours total de la dette au 31/12 : {lm.get('encours_dette', 0)/1e6:.2f} M€ ({lm.get('encours_dette_par_hab', 0):.0f} €/hab)
- Épargne brute (Capacité d'Autofinancement brute) : {lm.get('epargne_brute', 0)/1e6:.2f} M€ ({lm.get('epargne_brute_par_hab', 0):.0f} €/hab)
- Capacité de désendettement théorique : {lm.get('capacite_desendettement_annees', 'N/A')} ans (seuil national de vigilance : 10 à 12 ans)
"""

    # Datasets Bercy pertinents en contexte documentaire
    bercy_context = ""
    sources = []
    if bercy_datasets:
        bercy_lines = []
        for ds in bercy_datasets[:4]:
            t = ds.get("title", "")
            desc = ds.get("description", "")[:180]
            url = ds.get("page_url") or f"https://www.data.gouv.fr/datasets/{ds.get('id', '')}"
            bercy_lines.append(f"- [Jeu de données Bercy / DGFiP] {t} : {desc} (Lien : {url})")
            sources.append({
                "title": t,
                "city": "Ministères Économiques et Financiers (DGFiP)",
                "amount_eur": None,
                "beneficiary": "data.gouv.fr"
            })
        bercy_context = "Jeux de données officiels et nomenclatures de Bercy / data.gouv.fr disponibles sur ce sujet :\n" + "\n".join(bercy_lines)

    if lm:
        sources.insert(0, {
            "title": f"Comptes Administratifs M57 - {commune_nom} ({annee})",
            "city": commune_nom,
            "amount_eur": lm.get("encours_dette"),
            "beneficiary": "Direction Générale des Finances Publiques (DGFiP)"
        })

    prompt = f"""Tu es CivicLens, un assistant expert en finances publiques locales françaises et en données budgétaires souveraines (DGFiP, OFGL, Ministères Économiques et Financiers, nomenclatures M14 et M57).

QUESTION DU CITOYEN / DÉCIDEUR :
"{question}"

CONTEXTE FINANCIER CERTIFIÉ DE LA COMMUNE :
{fin_context if fin_context else "Aucune commune spécifique sélectionnée ou données non chargées."}

CATALOGUE DE DONNÉES DOCUMENTAIRES & OPEN DATA (BERCY) :
{bercy_context if bercy_context else "Catalogue national data.gouv.fr (DGFiP)."}

CONSIGNES POUR TA RÉPONSE :
1. Réponds de façon synthétique, directe et rigoureuse en français (maximum 3 à 4 paragraphes courts).
2. Si des chiffres sont disponibles dans le contexte, utilise-les précisément (ex: montants en M€ ou en €/habitant, ratio de désendettement).
3. Donne des explications pédagogiques claires (par exemple ce que signifie une capacité d'autofinancement ou un ratio de désendettement).
4. Si la question fait référence à des jeux de données, mentionne les sources officielles de Bercy / DGFiP.
5. Sois percutant, pas de préambule superflu.
"""

    try:
        import vertexai
        from google.cloud import aiplatform
        from vertexai.generative_models import GenerativeModel, GenerationConfig

        project = os.environ.get("GCP_PROJECT", "wh-djvagl")
        vertexai.init(project=project, location="global")
        aiplatform.init(project=project, location="global")

        actual_model = "gemini-3.6-flash" if ("3.6" in (model_name or "") or "flash" in (model_name or "").lower()) else (model_name or "gemini-3.6-flash")
        model = GenerativeModel(actual_model)
        gen_config = GenerationConfig(max_output_tokens=1000, temperature=0.2)
        response = model.generate_content(prompt, generation_config=gen_config)
        return {
            "answer": response.text,
            "sources": sources
        }
    except Exception as e:
        logger.warning(f"Fallback local pour chat RAG Gemini ({e})")
        if lm:
            answer = f"D'après les comptes certifiés DGFiP / OFGL pour **{commune_nom}** ({annee}) :\n\n" \
                     f"- **Dépenses réelles de fonctionnement** : {lm.get('depenses_fonctionnement', 0)/1e6:.1f} M€ ({lm.get('depenses_fonctionnement_par_hab', 0):.0f} €/hab)\n" \
                     f"- **Recettes réelles de fonctionnement** : {lm.get('recettes_fonctionnement', 0)/1e6:.1f} M€ ({lm.get('recettes_fonctionnement_par_hab', 0):.0f} €/hab)\n" \
                     f"- **Investissements d'équipement** : {lm.get('depenses_equipement', 0)/1e6:.1f} M€ ({lm.get('depenses_equipement_par_hab', 0):.0f} €/hab)\n" \
                     f"- **Encours total de la dette** : {lm.get('encours_dette', 0)/1e6:.1f} M€ ({lm.get('encours_dette_par_hab', 0):.0f} €/hab)\n" \
                     f"- **Épargne brute (Capacité d'Autofinancement)** : {lm.get('epargne_brute', 0)/1e6:.1f} M€\n" \
                     f"- **Délai de désendettement théorique** : {lm.get('capacite_desendettement_annees', 'N/A')} ans\n\n" \
                     f"Concernant votre question : *« {question} »*, ces éléments attestent de la trajectoire budgétaire de la collectivité sous la nomenclature comptable M57."
        else:
            answer = f"Pour répondre précisément à votre question concernant *« {question} »*, vous pouvez sélectionner une commune dans la barre ci-dessus afin de charger ses ratios certifiés DGFiP/OFGL ou explorer le catalogue des jeux de données de Bercy."

        return {
            "answer": answer,
            "sources": sources
        }

DEFAULT_BENCHMARK_PROMPTS = {
    "part_1": {
        "id": "part_1",
        "title": "1. Modèle de Gestion Courante & Maîtrise des Charges",
        "short_title": "Gestion Courante & Masse Salariale",
        "instruction": "Compare la structure des recettes vs dépenses réelles de fonctionnement et le poids de la masse salariale par habitant. Analyse l'effet de ciseau potentiel et l'efficacité de gestion de chaque commune."
    },
    "part_2": {
        "id": "part_2",
        "title": "2. Capacité d'Autofinancement & Stratégie d'Investissement",
        "short_title": "Investissement & Capacité d'Autofinancement",
        "instruction": "Confronte les niveaux d'épargne brute (CAF) et l'effort consenti en dépenses d'équipement par habitant. Quelle collectivité prépare le plus activement ses infrastructures et transitions d'avenir ?"
    },
    "part_3": {
        "id": "part_3",
        "title": "3. Soutenabilité de la Dette & Solvabilité Comparée",
        "short_title": "Dette, Annuités & Solvabilité",
        "instruction": "Analyse la charge de l'encours de la dette par habitant et le délai théorique de désendettement en années au regard du seuil de vigilance national (10-12 ans). Évalue les marges de manœuvre d'emprunt résiduelles."
    },
    "part_4": {
        "id": "part_4",
        "title": "4. Bilan Stratégique & Arbitrage Final CivicLens",
        "short_title": "Bilan Global & Arbitrage Final",
        "instruction": "Dresse une synthèse conclusive claire : points forts, vulnérabilités respectives, profil de notation synthétique et recommandations budgétaires pour chaque équipe municipale."
    }
}


def get_default_benchmark_prompts() -> Dict[str, Any]:
    """Retourne le dictionnaire des prompts par défaut pour l'arbitrage M57."""
    return DEFAULT_BENCHMARK_PROMPTS


def compare_communes_financial_profiles(
    fin_a: Dict[str, Any],
    fin_b: Dict[str, Any],
    model_name: str = "gemini-3.6-flash",
    custom_prompts: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Compare deux profils financiers M57 complets (charges, recettes, dette, CAF, investissement)
    et génère une synthèse comparative rédigée par Gemini selon les 4 volets (personnalisables).
    """
    name_a = fin_a.get("nom", "Commune A")
    name_b = fin_b.get("nom", "Commune B")
    lm_a = fin_a.get("latest_metrics", {})
    lm_b = fin_b.get("latest_metrics", {})
    pop_a = fin_a.get("population", 0)
    pop_b = fin_b.get("population", 0)

    comparison_table = [
        {
            "metric": "Population totale",
            "val_a": f"{pop_a:,} hab.",
            "val_b": f"{pop_b:,} hab.",
            "unit": "habitants"
        },
        {
            "metric": "Dépenses de gestion courante / hab.",
            "val_a": f"{lm_a.get('depenses_fonctionnement_par_hab', 0):.0f} €",
            "val_b": f"{lm_b.get('depenses_fonctionnement_par_hab', 0):.0f} €",
            "unit": "€/hab"
        },
        {
            "metric": "Effort d'investissement (équipement) / hab.",
            "val_a": f"{lm_a.get('depenses_equipement_par_hab', 0):.0f} €",
            "val_b": f"{lm_b.get('depenses_equipement_par_hab', 0):.0f} €",
            "unit": "€/hab"
        },
        {
            "metric": "Encours de dette / hab.",
            "val_a": f"{lm_a.get('encours_dette_par_hab', 0):.0f} €",
            "val_b": f"{lm_b.get('encours_dette_par_hab', 0):.0f} €",
            "unit": "€/hab"
        },
        {
            "metric": "Épargne brute (Capacité d'Autofinancement) / hab.",
            "val_a": f"{lm_a.get('epargne_brute_par_hab', 0):.0f} €",
            "val_b": f"{lm_b.get('epargne_brute_par_hab', 0):.0f} €",
            "unit": "€/hab"
        },
        {
            "metric": "Délai de désendettement",
            "val_a": f"{lm_a.get('capacite_desendettement_annees', 'N/A')} ans",
            "val_b": f"{lm_b.get('capacite_desendettement_annees', 'N/A')} ans",
            "unit": "années"
        }
    ]

    # Résolution des prompts pour chacune des 4 parties (personnalisés ou par défaut)
    prompts_input = custom_prompts or {}
    p1 = (prompts_input.get("part_1") or DEFAULT_BENCHMARK_PROMPTS["part_1"]["instruction"]).strip()
    p2 = (prompts_input.get("part_2") or DEFAULT_BENCHMARK_PROMPTS["part_2"]["instruction"]).strip()
    p3 = (prompts_input.get("part_3") or DEFAULT_BENCHMARK_PROMPTS["part_3"]["instruction"]).strip()
    p4 = (prompts_input.get("part_4") or DEFAULT_BENCHMARK_PROMPTS["part_4"]["instruction"]).strip()

    is_customized = (
        p1 != DEFAULT_BENCHMARK_PROMPTS["part_1"]["instruction"].strip() or
        p2 != DEFAULT_BENCHMARK_PROMPTS["part_2"]["instruction"].strip() or
        p3 != DEFAULT_BENCHMARK_PROMPTS["part_3"]["instruction"].strip() or
        p4 != DEFAULT_BENCHMARK_PROMPTS["part_4"]["instruction"].strip()
    )

    # Préparation du prompt d'arbitrage enrichi
    prompt = f"""Tu es CivicLens, expert souverain en finances publiques locales françaises et analyste financier certifié sur le cadre comptable M57 (DGFiP / OFGL).
Effectue un arbitrage budgétaire et stratégique approfondi, rigoureux et comparatif entre ces deux collectivités territoriales :

### PROFIL DE LA COLLECTIVITÉ A : {name_a}
- Population légale : {pop_a:,} habitants
- Recettes de fonctionnement : {lm_a.get('recettes_fonctionnement_par_hab', 0):.0f} €/hab ({lm_a.get('recettes_fonctionnement', 0)/1e6:.2f} M€)
- Dépenses de fonctionnement : {lm_a.get('depenses_fonctionnement_par_hab', 0):.0f} €/hab ({lm_a.get('depenses_fonctionnement', 0)/1e6:.2f} M€)
- Frais de personnel : {lm_a.get('frais_personnel_par_hab', 0):.0f} €/hab ({lm_a.get('frais_personnel', 0)/1e6:.2f} M€)
- Épargne brute (Capacité d'Autofinancement) : {lm_a.get('epargne_brute_par_hab', 0):.0f} €/hab ({lm_a.get('epargne_brute', 0)/1e6:.2f} M€)
- Dépenses d'équipement (Investissement) : {lm_a.get('depenses_equipement_par_hab', 0):.0f} €/hab ({lm_a.get('depenses_equipement', 0)/1e6:.2f} M€)
- Encours total de dette : {lm_a.get('encours_dette_par_hab', 0):.0f} €/hab ({lm_a.get('encours_dette', 0)/1e6:.2f} M€)
- Capacité de désendettement théorique : {lm_a.get('capacite_desendettement_annees', 'N/A')} ans (seuil d'alerte national : > 10 à 12 ans)

### PROFIL DE LA COLLECTIVITÉ B : {name_b}
- Population légale : {pop_b:,} habitants
- Recettes de fonctionnement : {lm_b.get('recettes_fonctionnement_par_hab', 0):.0f} €/hab ({lm_b.get('recettes_fonctionnement', 0)/1e6:.2f} M€)
- Dépenses de fonctionnement : {lm_b.get('depenses_fonctionnement_par_hab', 0):.0f} €/hab ({lm_b.get('depenses_fonctionnement', 0)/1e6:.2f} M€)
- Frais de personnel : {lm_b.get('frais_personnel_par_hab', 0):.0f} €/hab ({lm_b.get('frais_personnel', 0)/1e6:.2f} M€)
- Épargne brute (Capacité d'Autofinancement) : {lm_b.get('epargne_brute_par_hab', 0):.0f} €/hab ({lm_b.get('epargne_brute', 0)/1e6:.2f} M€)
- Dépenses d'équipement (Investissement) : {lm_b.get('depenses_equipement_par_hab', 0):.0f} €/hab ({lm_b.get('depenses_equipement', 0)/1e6:.2f} M€)
- Encours total de dette : {lm_b.get('encours_dette_par_hab', 0):.0f} €/hab ({lm_b.get('encours_dette', 0)/1e6:.2f} M€)
- Capacité de désendettement théorique : {lm_b.get('capacite_desendettement_annees', 'N/A')} ans (seuil d'alerte national : > 10 à 12 ans)

CONSIGNES DE RÉDACTION ET D'ÉVALUATION STRATÉGIQUE :
Rédige une analyse financière comparative complète, vivante, hautement pertinente et pédagogique. Structure impérativement ton arbitrage en 4 parties claires et bien développées (environ 150 à 250 mots par section) avec des titres markdown (###) en appliquant les consignes spécifiques suivantes pour chaque volet :

### 1. Modèle de Gestion Courante & Maîtrise des Charges
{p1}

### 2. Capacité d'Autofinancement & Stratégie d'Investissement
{p2}

### 3. Soutenabilité de la Dette & Solvabilité Comparée
{p3}

### 4. Bilan Stratégique & Arbitrage Final CivicLens
{p4}

Rédige en français irréprochable avec des chiffres précis cités entre parenthèses pour étayer chaque argument. Assure-toi de mener les 4 sections jusqu'à la conclusion complète sans interruption.
"""

    analysis = ""
    try:
        import vertexai
        from google.cloud import aiplatform
        from vertexai.generative_models import GenerativeModel, GenerationConfig
        project = os.environ.get("GCP_PROJECT", "wh-djvagl")
        vertexai.init(project=project, location="global")
        aiplatform.init(project=project, location="global")
        actual_model = "gemini-3.6-flash" if ("3.6" in (model_name or "") or "flash" in (model_name or "").lower()) else (model_name or "gemini-3.6-flash")
        model = GenerativeModel(actual_model)
        gen_config = GenerationConfig(max_output_tokens=6000, temperature=0.2)
        res = model.generate_content(prompt, generation_config=gen_config)
        analysis = res.text
    except Exception as e:
        logger.warning(f"Fallback local pour benchmark {name_a} vs {name_b}: {e}")
        analysis = f"Comparatif budgétaire établi entre **{name_a}** et **{name_b}**.\n\n" \
                   f"- **Endettement par habitant** : {lm_a.get('encours_dette_par_hab', 0):.0f} € pour {name_a} contre {lm_b.get('encours_dette_par_hab', 0):.0f} € pour {name_b}.\n" \
                   f"- **Effort d'investissement** : {lm_a.get('depenses_equipement_par_hab', 0):.0f} €/hab ({name_a}) vs {lm_b.get('depenses_equipement_par_hab', 0):.0f} €/hab ({name_b}).\n" \
                   f"- **Désendettement théorique** : {lm_a.get('capacite_desendettement_annees', 'N/A')} ans vs {lm_b.get('capacite_desendettement_annees', 'N/A')} ans."

    return {
        "commune_a": {
            "nom": name_a,
            "population": pop_a,
            "metrics": lm_a
        },
        "commune_b": {
            "nom": name_b,
            "population": pop_b,
            "metrics": lm_b
        },
        "comparison_table": comparison_table,
        "comparative_analysis": analysis,
        "applied_prompts": {
            "part_1": p1,
            "part_2": p2,
            "part_3": p3,
            "part_4": p4
        },
        "is_customized": is_customized
    }
