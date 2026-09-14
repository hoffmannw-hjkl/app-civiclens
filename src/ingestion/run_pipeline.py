# -*- coding: utf-8 -*-
"""
run_pipeline.py - Pipeline E2E : Téléchargement Open Data (data.gouv.fr) -> Ingestion Gemini 2.5 Flash -> Fiche Structurée.
"""

import os
import json
import logging
from crawler import DataGouvCrawler
from extractor import CivicLensExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CivicLensPipeline")


def run_pipeline(query: str = "deliberation conseil municipal subvention", sample_limit: int = 2):
    output_dir = "./data/processed"
    raw_dir = "./data/raw_pdfs"
    os.makedirs(output_dir, exist_ok=True)

    crawler = DataGouvCrawler(download_dir=raw_dir)
    extractor = CivicLensExtractor()

    logger.info(f"Étape 1 : Recherche de délibérations sur data.gouv.fr ('{query}')")
    datasets = crawler.search_deliberation_datasets(query=query, max_results=5)

    processed_count = 0
    results = []

    for dataset in datasets:
        if processed_count >= sample_limit:
            break

        pdfs = crawler.extract_pdf_resources(dataset)
        for pdf_meta in pdfs:
            if processed_count >= sample_limit:
                break

            logger.info(f"Traitement du document : {pdf_meta['title']}")
            local_pdf = crawler.download_pdf(pdf_meta)
            if not local_pdf or not os.path.exists(local_pdf):
                continue

            # Inférence Multimodale Gemini 2.5 Flash
            logger.info(f"Étape 2 : Analyse par Gemini 2.5 Flash...")
            analysis = extractor.analyze_pdf(local_pdf)
            analysis["source_url"] = pdf_meta["url"]
            analysis["dataset"] = pdf_meta["dataset_title"]
            analysis["organization_source"] = pdf_meta["organization"]

            # Sauvegarde de la fiche structurée
            doc_id = analysis.get("deliberation_id", f"doc_{processed_count}").replace("/", "_").replace(" ", "_")
            out_json = os.path.join(output_dir, f"{doc_id}.json")
            with open(out_json, "w", encoding="utf-8") as f:
                json.dump(analysis, f, ensure_ascii=False, indent=2)

            logger.info(f"Fiche générée avec succès : {out_json}")
            results.append(analysis)
            processed_count += 1

    summary_file = os.path.join(output_dir, "pipeline_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info(f"Pipeline terminé ! {processed_count} document(s) traité(s). Synthèse : {summary_file}")


if __name__ == "__main__":
    run_pipeline()
