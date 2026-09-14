# -*- coding: utf-8 -*-
"""
ingestion_service.py - Service de recherche, téléchargement et ingestion de délibérations PDF par ville.
Supporte data.gouv.fr (organisations & recherche textuelle), geo.api.gouv.fr, et les portails Open Data des collectivités.
"""

import os
import re
import json
import logging
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Optional

logger = logging.getLogger("CivicLensIngestion")

# Collectivités prédéfinies avec identifiants data.gouv.fr ou OpenDataSoft vérifiés
KNOWN_COLLECTIVITIES = [
    {
        "id": "pantin",
        "name": "Ville de Pantin",
        "department": "93 - Seine-Saint-Denis",
        "region": "Île-de-France",
        "source": "OFGL & data.gouv.fr",
        "count_approx": "Comptes certifiés & Datasets"
    },
    {
        "id": "bordeaux",
        "name": "Ville de Bordeaux",
        "department": "33 - Gironde",
        "region": "Nouvelle-Aquitaine",
        "source": "OFGL & data.gouv.fr",
        "count_approx": "Comptes certifiés & Datasets"
    },
    {
        "id": "castelmaurou",
        "name": "Commune de Castelmaurou",
        "department": "31 - Haute-Garonne",
        "region": "Occitanie",
        "org_id": "68efa088b9f4814438471eb5",
        "source": "data.gouv.fr",
        "count_approx": "80+ délibérations PDF"
    },
    {
        "id": "jouarre",
        "name": "Mairie de Jouarre",
        "department": "77 - Seine-et-Marne",
        "region": "Île-de-France",
        "org_id": "5fcb9638de0dbe60edb348ce",
        "source": "data.gouv.fr",
        "count_approx": "250+ délibérations PDF"
    },
    {
        "id": "orvault",
        "name": "Ville d'Orvault (Nantes Métropole)",
        "department": "44 - Loire-Atlantique",
        "region": "Pays de la Loire",
        "source": "ods_nantes",
        "count_approx": "150+ délibérations PDF"
    },
    {
        "id": "tartas",
        "name": "Commune de Tartas",
        "department": "40 - Landes",
        "region": "Nouvelle-Aquitaine",
        "org_id": "606d7f3644b7c6a93cf48e8d",
        "source": "data.gouv.fr",
        "count_approx": "70+ délibérations PDF"
    },
    {
        "id": "nogent",
        "name": "Ville de Nogent-sur-Marne",
        "department": "94 - Val-de-Marne",
        "region": "Île-de-France",
        "org_id": "54ca2b22c751df5273467389",
        "source": "data.gouv.fr",
        "count_approx": "25+ délibérations PDF"
    },
    {
        "id": "rosny",
        "name": "Ville de Rosny-sous-Bois",
        "department": "93 - Seine-Saint-Denis",
        "region": "Île-de-France",
        "org_id": "5b28f5b288ee38047e62143e",
        "source": "data.gouv.fr",
        "count_approx": "60+ actes administratifs PDF"
    },
    {
        "id": "soissons",
        "name": "Ville de Soissons",
        "department": "02 - Aisne",
        "region": "Hauts-de-France",
        "org_id": "6095142a84c45b36441511eb",
        "source": "data.gouv.fr",
        "count_approx": "5000+ délibérations PDF"
    },
    {
        "id": "leslilas",
        "name": "Ville des Lilas",
        "department": "93 - Seine-Saint-Denis",
        "region": "Île-de-France",
        "org_id": "534fff86a3a7292c64a77eab",
        "source": "data.gouv.fr",
        "count_approx": "1200+ arrêtés et actes PDF"
    },
    {
        "id": "grandsoissons",
        "name": "GrandSoissons Agglomération",
        "department": "02 - Aisne",
        "region": "Hauts-de-France",
        "org_id": "6810c7bb09c320c354c233f4",
        "source": "data.gouv.fr",
        "count_approx": "1000+ délibérations PDF"
    },
    {
        "id": "templemars",
        "name": "Commune de Templemars",
        "department": "59 - Nord",
        "region": "Hauts-de-France",
        "org_id": "6a465eee670e9b6d34e26eed",
        "source": "data.gouv.fr",
        "count_approx": "70+ actes et délibérations PDF"
    },
    {
        "id": "faugeres",
        "name": "Commune de Faugères",
        "department": "07 - Ardèche",
        "region": "Auvergne-Rhône-Alpes",
        "org_id": "57ad996ac751df5e2c97bae5",
        "source": "data.gouv.fr",
        "count_approx": "50+ délibérations PDF"
    },
    {
        "id": "pirae",
        "name": "Ville de Pirae",
        "department": "987 - Polynésie Française",
        "region": "Outre-Mer",
        "org_id": "56bac12ec751df6c539f9dea",
        "source": "data.gouv.fr",
        "count_approx": "800+ délibérations PDF"
    },
    {
        "id": "mery",
        "name": "Mairie de Méry-sur-Marne",
        "department": "77 - Seine-et-Marne",
        "region": "Île-de-France",
        "org_id": "6005ae216c957d96087bb80b",
        "source": "data.gouv.fr",
        "count_approx": "5 délibérations PDF"
    }
]



CUSTOM_COLLECTIVITIES_FILE = os.path.join(os.path.dirname(__file__), "custom_collectivities.json")

def load_custom_collectivities() -> List[Dict[str, Any]]:
    if os.path.exists(CUSTOM_COLLECTIVITIES_FILE):
        try:
            with open(CUSTOM_COLLECTIVITIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_custom_collectivity(data: Dict[str, Any]) -> Dict[str, Any]:
    customs = load_custom_collectivities()
    # Check if already exists
    cid = data.get("id") or data.get("name", "").lower().replace(" ", "_")
    for c in customs:
        if c.get("id") == cid:
            return c
    customs.append(data)
    with open(CUSTOM_COLLECTIVITIES_FILE, "w", encoding="utf-8") as f:
        json.dump(customs, f, ensure_ascii=False, indent=2)
    return data

def list_known_collectivities() -> List[Dict[str, Any]]:
    """Retourne la liste des collectivités (statiques + ajoutées par les utilisateurs)."""
    return KNOWN_COLLECTIVITIES + load_custom_collectivities()


def search_deliberations_by_city(
    city_query: str,
    filter_keyword: Optional[str] = None,
    max_results: int = 30
) -> List[Dict[str, Any]]:
    """
    Recherche en profondeur des délibérations / actes municipaux PDF pour toute ville française.
    Stratégie en cascade :
    1. Portails partenaires spécialisés (ex: Nantes Métropole / Orvault)
    2. Correspondance avec la table de collectivités pré-identifiées
    3. Résolution dynamique de l'organisation municipale sur data.gouv.fr
    4. Recherche multi-mots-clés sur les jeux de données publics
    """
    results: List[Dict[str, Any]] = []
    seen_urls = set()
    city_clean = city_query.strip().lower()

    # 1. Cas spécial Orvault / Nantes Métropole via portail OpenDataSoft
    if "orvault" in city_clean or "nantes" in city_clean:
        try:
            ods_url = "https://data.nantesmetropole.fr/api/explore/v2.1/catalog/datasets/214401143_deliberations-du-conseil-municipal-de-la-ville-dorvault-en-2023-delibe/records?limit=40"
            if filter_keyword:
                search_expr = f'search(delib_objet, "{filter_keyword}")'
                ods_url += f"&where={urllib.parse.quote(search_expr)}"
            req = urllib.request.Request(ods_url, headers={"User-Agent": "CivicLens/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                for r in data.get("results", []):
                    pdf_info = r.get("delib_url") or {}
                    u = pdf_info.get("url")
                    if u and u not in seen_urls:
                        seen_urls.add(u)
                        results.append({
                            "deliberation_id": r.get("delib_id", "ACTE-ORVAULT"),
                            "city": "Ville d'Orvault (44)",
                            "date": r.get("delib_date"),
                            "title": r.get("delib_objet") or "Délibération municipale",
                            "pdf_url": u,
                            "filename": pdf_info.get("filename", "deliberation.pdf"),
                            "filesize": None,
                            "source": "OpenData Nantes Métropole",
                            "status": "DISPONIBLE"
                        })
            if results:
                return results[:max_results]
        except Exception as e:
            logger.warning(f"Erreur API Nantes: {e}")

    # 2. Vérifier si c'est une collectivité connue dans notre annuaire local
    matched_org_id = None
    collectivity_label = city_query
    for c in list_known_collectivities():
        if c["id"] in city_clean or city_clean in c["name"].lower() or c["name"].lower() in city_clean:
            matched_org_id = c.get("org_id")
            collectivity_label = c["name"]
            break

    target_orgs = []
    if matched_org_id:
        target_orgs.append((matched_org_id, collectivity_label))
    else:
        # 3. Résolution dynamique de l'organisation municipale sur data.gouv.fr
        try:
            url_org = f"https://www.data.gouv.fr/api/1/organizations/?q={urllib.parse.quote(city_query)}&page_size=6"
            req_org = urllib.request.Request(url_org, headers={"User-Agent": "CivicLens/1.0"})
            with urllib.request.urlopen(req_org, timeout=8) as resp:
                data_org = json.loads(resp.read().decode())
                for o in data_org.get("data", []):
                    o_id = o.get("id")
                    o_name = o.get("name", "")
                    if o_id:
                        target_orgs.append((o_id, o_name))
        except Exception as e:
            logger.warning(f"Erreur recherche orgs data.gouv.fr pour '{city_query}': {e}")

    # Récupérer les jeux de données des organisations identifiées
    for org_id, org_name in target_orgs:
        try:
            url_ds = f"https://www.data.gouv.fr/api/1/datasets/?organization={org_id}&page_size=20"
            req_ds = urllib.request.Request(url_ds, headers={"User-Agent": "CivicLens/1.0"})
            with urllib.request.urlopen(req_ds, timeout=8) as resp_ds:
                data_ds = json.loads(resp_ds.read().decode())
                for d in data_ds.get("data", []):
                    ds_title = d.get("title", "")
                    for r in d.get("resources", []):
                        fmt = (r.get("format") or "").lower()
                        u = r.get("url") or ""
                        r_title = r.get("title") or "Délibération"
                        if fmt == "pdf" or u.lower().endswith(".pdf"):
                            if filter_keyword:
                                if filter_keyword.lower() not in r_title.lower() and filter_keyword.lower() not in ds_title.lower():
                                    continue
                            if u not in seen_urls:
                                seen_urls.add(u)
                                results.append({
                                    "deliberation_id": r_title.replace(".pdf", ""),
                                    "city": org_name or collectivity_label,
                                    "date": r.get("created_at", "")[:10] if r.get("created_at") else None,
                                    "title": f"{r_title} - {ds_title}" if r_title != ds_title else r_title,
                                    "pdf_url": u,
                                    "filename": r_title if r_title.endswith(".pdf") else f"{r_title}.pdf",
                                    "filesize": r.get("filesize"),
                                    "source": "data.gouv.fr",
                                    "status": "DISPONIBLE"
                                })
                                if len(results) >= max_results:
                                    return results
        except Exception as e:
            logger.debug(f"Scan org {org_id} exception: {e}")

    # 4. Repli : Recherche multi-termes sur l'API globale data.gouv.fr
    if not results:
        fallback_queries = [
            f"deliberations {city_query}",
            f"{city_query} deliberations",
            f"actes administratifs {city_query}",
            city_query
        ]
        for q in fallback_queries:
            try:
                url_q = f"https://www.data.gouv.fr/api/1/datasets/?q={urllib.parse.quote(q)}&page_size=15"
                req_q = urllib.request.Request(url_q, headers={"User-Agent": "CivicLens/1.0"})
                with urllib.request.urlopen(req_q, timeout=8) as resp_q:
                    data_q = json.loads(resp_q.read().decode())
                    for d in data_q.get("data", []):
                        ds_title = d.get("title", "")
                        org_obj = d.get("organization") or {}
                        org_name = org_obj.get("name", city_query)
                        for r in d.get("resources", []):
                            fmt = (r.get("format") or "").lower()
                            u = r.get("url") or ""
                            r_title = r.get("title") or "Délibération"
                            if fmt == "pdf" or u.lower().endswith(".pdf"):
                                if filter_keyword:
                                    if filter_keyword.lower() not in r_title.lower() and filter_keyword.lower() not in ds_title.lower():
                                        continue
                                if u not in seen_urls:
                                    seen_urls.add(u)
                                    results.append({
                                        "deliberation_id": r_title.replace(".pdf", ""),
                                        "city": org_name,
                                        "date": r.get("created_at", "")[:10] if r.get("created_at") else None,
                                        "title": f"{r_title} - {ds_title}" if r_title != ds_title else r_title,
                                        "pdf_url": u,
                                        "filename": r_title if r_title.endswith(".pdf") else f"{r_title}.pdf",
                                        "filesize": r.get("filesize"),
                                        "source": "data.gouv.fr",
                                        "status": "DISPONIBLE"
                                    })
                                    if len(results) >= max_results:
                                        return results
            except Exception as e:
                logger.debug(f"Query {q} error: {e}")
            if len(results) >= 5:
                break

    return results
