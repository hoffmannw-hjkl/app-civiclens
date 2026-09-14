# -*- coding: utf-8 -*-
"""
bercy_service.py - Connecteur aux 650+ jeux de données officiels des Ministères Économiques et Financiers (Bercy / DGFiP).
Permet de rechercher et d'explorer les catalogues de données de Bercy sur data.gouv.fr :
- Balances comptables annuelles des communes et groupements
- Comptes individuels des communes (fichiers globaux 2000-2025)
- Fichier REI (Fiscalité directe locale)
- Délais de paiement des collectivités locales
- Décisions et statistiques de la commande publique
"""

import os
import json
import logging
import urllib.request
import urllib.parse
from typing import Dict, List, Any, Optional

logger = logging.getLogger("CivicLensBercy")

BERCY_ORG_ID = "534fff8ea3a7292c64a77f02"
DATAGOUV_BASE_URL = "https://www.data.gouv.fr/api/1"

_CACHE_BERCY: Dict[str, Dict[str, Any]] = {}


def search_bercy_datasets(query: Optional[str] = None, page: int = 1, page_size: int = 12) -> Dict[str, Any]:
    """
    Recherche les jeux de données publiés par les Ministères Économiques et Financiers (Bercy).
    """
    cache_key = f"{query or ''}_{page}_{page_size}"
    if cache_key in _CACHE_BERCY:
        return _CACHE_BERCY[cache_key]

    params = {
        "organization": BERCY_ORG_ID,
        "page": page,
        "page_size": page_size
    }
    if query and query.strip():
        params["q"] = query.strip()

    encoded_params = urllib.parse.urlencode(params)
    url = f"{DATAGOUV_BASE_URL}/datasets/?{encoded_params}"

    req = urllib.request.Request(url, headers={"User-Agent": "CivicLens-BercyExplorer/2.0"})
    try:
        raw = None
        source_scope = "Bercy (DGFiP)"
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read().decode("utf-8"))

        # Fallback intelligent : si aucun résultat trouvé dans l'organisation Bercy pour ce mot-clé (ex: "pantin", "rennes", etc.)
        # on recherche sur l'ensemble de data.gouv.fr pour remonter les jeux de données publics associés à la collectivité.
        if (not raw or raw.get("total", 0) == 0) and query and query.strip():
            url_fallback = f"{DATAGOUV_BASE_URL}/datasets/?q={urllib.parse.quote(query.strip())}&page={page}&page_size={page_size}"
            req_fb = urllib.request.Request(url_fallback, headers={"User-Agent": "CivicLens-DataGouv/2.0"})
            with urllib.request.urlopen(req_fb, timeout=10) as resp_fb:
                raw = json.loads(resp_fb.read().decode("utf-8"))
                source_scope = "data.gouv.fr (National)"

        datasets = []
        for item in (raw.get("data", []) if raw else []):
            resources = []
            for r in item.get("resources", [])[:6]:
                resources.append({
                    "id": r.get("id"),
                    "title": r.get("title") or r.get("description") or "Ressource de données",
                    "format": (r.get("format") or "csv").lower(),
                    "url": r.get("url"),
                    "filesize": r.get("filesize"),
                    "last_modified": r.get("last_modified")
                })

            org_name = (item.get("organization") or {}).get("name") if item.get("organization") else source_scope

            datasets.append({
                "id": item.get("id"),
                "title": item.get("title"),
                "slug": item.get("slug"),
                "description": (item.get("description") or "")[:350],
                "page_url": item.get("page"),
                "organization_name": org_name,
                "created_at": item.get("created_at"),
                "last_update": item.get("last_update"),
                "views": item.get("metrics", {}).get("views", 0),
                "resources_count": len(item.get("resources", [])),
                "resources": resources
            })

        result = {
            "total": raw.get("total", 0) if raw else 0,
            "page": page,
            "page_size": page_size,
            "query": query or "",
            "source_scope": source_scope,
            "datasets": datasets
        }
        _CACHE_BERCY[cache_key] = result
        return result
    except Exception as e:
        logger.error(f"Erreur recherche Bercy/data.gouv datasets ({e})")
        return {"total": 0, "page": page, "page_size": page_size, "query": query or "", "datasets": []}
