# -*- coding: utf-8 -*-
"""
seed_database.py - Script d'ingestion et d'insertion réelle dans Cloud SQL PostgreSQL avec pgvector.
"""

import os
import sys
import json
import logging
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import google.auth
import google.auth.transport.requests

sys.path.append(os.path.abspath("app/backend"))
from vector_service import get_embedding

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CivicLensSeeder")

DB_HOST = os.environ.get("DB_HOST", "10.238.0.2")
DB_NAME = os.environ.get("DB_NAME", "wh-djvagl-db")
DB_USER = os.environ.get("DB_USER", "wh-djvagl-linux-sa@wh-djvagl.iam")


def get_token():
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/sqlservice.admin"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def get_conn():
    token = get_token()
    return psycopg2.connect(
        host=DB_HOST,
        port=5432,
        dbname=DB_NAME,
        user=DB_USER,
        password=token,
        sslmode="require",
        cursor_factory=RealDictCursor
    )


DELIBERATIONS_SEED = [
    {
        "deliberation_id": "DELIB-2024-042",
        "city": "Bordeaux Métropole",
        "session_date": "2024-03-22",
        "theme": "Culture & Sport",
        "title": "Attribution des subventions annuelles de fonctionnement aux associations sportives locales",
        "summary": "Le Conseil Municipal approuve l'attribution d'une subvention exceptionnelle de 45 000 euros au Club Nautique Girondin pour le renouvellement du matériel d'entraînement des jeunes et l'organisation des régates métropolitaines.",
        "beneficiary": "Club Nautique Girondin",
        "amount_eur": 45000.00,
        "vote_result": "ADOPTE_UNANIMITE",
        "gcs_pdf_uri": "gs://wh-djvagl-storage-raw-docs/deliberations/2024/bordeaux_delib_2024_042.pdf",
        "legal_references": ["CGCT art. L. 2121-29", "Loi 1901 art. 6"],
        "key_entities": ["Club Nautique Girondin", "Maire de Bordeaux", "Direction des Sports"],
        "keywords": ["subvention", "sport", "nautisme", "jeunesse"]
    },
    {
        "deliberation_id": "DELIB-2024-089",
        "city": "Lyon",
        "session_date": "2024-04-15",
        "theme": "Environnement & Transition Écologique",
        "title": "Plan Canopée et renaturation des cours d'écoles du 7ème arrondissement",
        "summary": "Adoption d'un programme d'investissement de 120 000 euros pour la déminéralisation et la végétalisation de trois cours d'écoles primaires, afin de lutter contre les îlots de chaleur urbains.",
        "beneficiary": "Groupement Végétal Urbain Auvergne-Rhône-Alpes",
        "amount_eur": 120000.00,
        "vote_result": "ADOPTE_MAJORITE",
        "gcs_pdf_uri": "gs://wh-djvagl-storage-raw-docs/deliberations/2024/lyon_delib_2024_089.pdf",
        "legal_references": ["Code de l'urbanisme art. L. 111-1", "Plan Climat Énergie"],
        "key_entities": ["Mairie de Lyon", "Académie de Lyon"],
        "keywords": ["canopée", "arbres", "végétalisation", "écoles", "chaleur"]
    },
    {
        "deliberation_id": "DELIB-2024-115",
        "city": "Rennes",
        "session_date": "2024-05-10",
        "theme": "Transports & Voirie",
        "title": "Extension du réseau express vélo métropolitain (Liaison Nord-Est)",
        "summary": "Délibération portant sur le financement des travaux d'aménagement de pistes cyclables sécurisées et séparées du trafic routier pour un montant global de 350 000 euros.",
        "beneficiary": "Eurovia Bretagne Travaux Publics",
        "amount_eur": 350000.00,
        "vote_result": "ADOPTE_UNANIMITE",
        "gcs_pdf_uri": "gs://wh-djvagl-storage-raw-docs/deliberations/2024/rennes_delib_2024_115.pdf",
        "legal_references": ["Code de la voirie routière", "Code des transports"],
        "key_entities": ["Rennes Métropole", "Direction de la Mobilité"],
        "keywords": ["vélo", "pistes cyclables", "mobilité douce", "transports"]
    },
    {
        "deliberation_id": "DELIB-2024-133",
        "city": "Nantes",
        "session_date": "2024-06-05",
        "theme": "Éducation & Jeunesse",
        "title": "Dotation numérique et tablettes tactiles pour les écoles élémentaires",
        "summary": "Le Conseil Municipal vote l'attribution d'un marché public de fournitures informatiques et matériels pédagogiques interactifs destiné aux classes de CM1 et CM2 pour 85 000 euros.",
        "beneficiary": "Société Ouest Éducation Technologies",
        "amount_eur": 85000.00,
        "vote_result": "ADOPTE_UNANIMITE",
        "gcs_pdf_uri": "gs://wh-djvagl-storage-raw-docs/deliberations/2024/nantes_delib_2024_133.pdf",
        "legal_references": ["Code de la commande publique"],
        "key_entities": ["Direction Éducation Nantes", "Rectorat de Nantes"],
        "keywords": ["numérique", "écoles", "tablettes", "éducation"]
    }
]


def seed():
    logger.info("Connexion à Cloud SQL PostgreSQL...")
    conn = get_conn()
    cur = conn.cursor()

    insert_sql = """
    INSERT INTO deliberations (
        deliberation_id, city, session_date, theme, title, summary,
        beneficiary, amount_eur, vote_result, gcs_pdf_uri, embedding,
        legal_references, key_entities, keywords, raw_json
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s)
    ON CONFLICT (id) DO NOTHING;
    """

    for item in DELIBERATIONS_SEED:
        logger.info(f"Calcul de l'embedding pour : {item['title']}")
        text_for_embedding = f"{item['title']} - {item['summary']} - {item['theme']} - {item['city']}"
        embedding = get_embedding(text_for_embedding)
        vector_str = f"[{','.join(str(x) for x in embedding)}]"

        cur.execute(insert_sql, (
            item["deliberation_id"],
            item["city"],
            item["session_date"],
            item["theme"],
            item["title"],
            item["summary"],
            item["beneficiary"],
            item["amount_eur"],
            item["vote_result"],
            item["gcs_pdf_uri"],
            vector_str,
            Json(item["legal_references"]),
            Json(item["key_entities"]),
            Json(item["keywords"]),
            Json(item)
        ))
        logger.info(f"Délibération '{item['deliberation_id']}' insérée avec succès !")

    conn.commit()
    cur.close()
    conn.close()
    logger.info("Seeding terminé avec succès !")


if __name__ == "__main__":
    seed()
