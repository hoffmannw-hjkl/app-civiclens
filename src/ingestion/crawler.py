# -*- coding: utf-8 -*-
"""
crawler.py - Moissonneur automatisé de délibérations municipales Open Data via l'API data.gouv.fr.
"""

import os
import json
import logging
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CivicLensCrawler")

API_BASE_URL = "https://data.gouv.fr/api/1/datasets/"


class DataGouvCrawler:
    """Collecteur de documents et métadonnées Open Data depuis data.gouv.fr."""

    def __init__(self, download_dir: str = "./downloads"):
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)

    def search_deliberation_datasets(self, query: str = "deliberations conseil municipal", max_results: int = 10) -> List[Dict[str, Any]]:
        """Recherche des jeux de données contenant des délibérations sur data.gouv.fr."""
        params = urllib.parse.urlencode({"q": query, "page_size": max_results})
        url = f"{API_BASE_URL}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "CivicLens-OpenData/1.0"})

        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                datasets = data.get("data", [])
                logger.info(f"Trouvé {len(datasets)} jeux de données pour la requête '{query}'.")
                return datasets
        except Exception as e:
            logger.error(f"Erreur lors de l'appel API data.gouv.fr : {e}")
            return []

    def extract_pdf_resources(self, dataset: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extrait les ressources PDF associées à un jeu de données."""
        resources = dataset.get("resources", [])
        pdf_list = []
        org_name = dataset.get("organization", {}).get("name", "Collectivité Inconnue")

        for r in resources:
            fmt = r.get("format", "").lower()
            url = r.get("url", "")
            if fmt == "pdf" or url.lower().endswith(".pdf"):
                pdf_list.append({
                    "dataset_title": dataset.get("title"),
                    "organization": org_name,
                    "title": r.get("title"),
                    "url": url,
                    "published_at": r.get("created_at") or r.get("published"),
                    "filesize": r.get("filesize")
                })
        return pdf_list

    def download_pdf(self, pdf_meta: Dict[str, Any]) -> Optional[str]:
        """Télécharge un document PDF de délibération en local pour traitement IA."""
        url = pdf_meta.get("url")
        if not url:
            return None

        clean_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in pdf_meta.get("title", "deliberation"))
        if not clean_name.lower().endswith(".pdf"):
            clean_name += ".pdf"

        dest_path = os.path.join(self.download_dir, clean_name)
        if os.path.exists(dest_path):
            logger.info(f"Fichier déjà en cache local : {dest_path}")
            return dest_path

        try:
            logger.info(f"Téléchargement de : {url} -> {dest_path}")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (CivicLens Crawler)"})
            with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as out_file:
                out_file.write(resp.read())
            logger.info(f"Téléchargement réussi : {dest_path} ({os.path.getsize(dest_path)} octets)")
            return dest_path
        except Exception as e:
            logger.error(f"Échec du téléchargement pour {url} : {e}")
            return None


if __name__ == "__main__":
    crawler = DataGouvCrawler(download_dir="./data/samples")
    datasets = crawler.search_deliberation_datasets("deliberations conseil municipal", max_results=5)
    all_pdfs = []
    for d in datasets:
        pdfs = crawler.extract_pdf_resources(d)
        if pdfs:
            logger.info(f"[{d.get('organization', {}).get('name')}] {len(pdfs)} PDF(s) disponible(s).")
            all_pdfs.extend(pdfs[:2]) # Limiter à 2 exemples par collectivité pour le test

    logger.info(f"Total de {len(all_pdfs)} délibérations PDF identifiées.")
