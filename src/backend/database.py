# -*- coding: utf-8 -*-
"""
database.py - Connexion PostgreSQL 16 avec extension pgvector pour CivicLens.
Gère les pools de connexions et l'authentification IAM Google Cloud sans mot de passe statique.
"""

import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Generator

logger = logging.getLogger("CivicLensDB")

DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "civiclens_db")
DB_USER = os.environ.get("DB_USER", "civiclens-app")
DB_PASSWORD = os.environ.get("DB_PASSWORD", None)


def get_iam_token() -> Optional[str]:
    """Récupère un jeton OAuth2 pour l'authentification IAM Cloud SQL."""
    try:
        import google.auth
        import google.auth.transport.requests
        scopes = ["https://www.googleapis.com/auth/sqlservice.admin"]
        creds, _ = google.auth.default(scopes=scopes)
        auth_req = google.auth.transport.requests.Request()
        creds.refresh(auth_req)
        return creds.token
    except Exception as e:
        logger.debug(f"Impossible de récupérer le token google-auth : {e}")
        try:
            import subprocess
            cmd = ["gcloud", "auth", "print-access-token"]
            return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        except Exception:
            return None


def get_db_connection():
    """Crée une connexion à la base Cloud SQL PostgreSQL avec support IAM ou mot de passe."""
    # En environnement GCP / Cloud SQL IAM, le mot de passe est un jeton OAuth2
    password = DB_PASSWORD or os.environ.get("PGPASSWORD")
    if not password:
        password = get_iam_token()

    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=password,
        sslmode="require",
        cursor_factory=RealDictCursor
    )
    return conn


def init_db():
    """Initialise les extensions et la table deliberations si nécessaire."""
    create_table_sql = """
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    CREATE EXTENSION IF NOT EXISTS "vector";

    CREATE TABLE IF NOT EXISTS deliberations (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        deliberation_id VARCHAR(100) NOT NULL,
        city VARCHAR(100) NOT NULL,
        session_date DATE,
        theme VARCHAR(100) NOT NULL,
        title TEXT NOT NULL,
        summary TEXT NOT NULL,
        beneficiary TEXT,
        amount_eur NUMERIC(15, 2),
        vote_result VARCHAR(50),
        gcs_pdf_uri TEXT,
        embedding vector(768),
        legal_references JSONB,
        key_entities JSONB,
        keywords JSONB,
        raw_json JSONB,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_deliberations_embedding 
    ON deliberations USING hnsw (embedding vector_cosine_ops) 
    WITH (m = 16, ef_construction = 64);

    CREATE INDEX IF NOT EXISTS idx_deliberations_city_date 
    ON deliberations (city, session_date DESC);

    CREATE INDEX IF NOT EXISTS idx_deliberations_theme 
    ON deliberations (theme);
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(create_table_sql)
            conn.commit()
            logger.info("Base de données et tables CivicLens initialisées avec succès.")
    except Exception as e:
        logger.warning(f"Note: initialisation DB différée (connexion Cloud SQL non établie) : {e}")
