# -*- coding: utf-8 -*-
"""
vector_service.py - Calcul des embeddings sémantiques (Vertex AI text-embedding-005)
et recherche hybride (Filtres SQL + Cosine Distance).
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
import psycopg2

logger = logging.getLogger("CivicLensVector")

PROJECT_ID = os.environ.get("GCP_PROJECT", "wh-testagy")
LOCATION = os.environ.get("GCP_LOCATION", "europe-west1")
EMBEDDING_MODEL_NAME = "text-embedding-005"


def get_embedding(text: str) -> List[float]:
    """Génère l'embedding vectoriel (768 dimensions) via Vertex AI."""
    try:
        import vertexai
        from vertexai.language_models import TextEmbeddingModel
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        model = TextEmbeddingModel.from_pretrained(EMBEDDING_MODEL_NAME)
        embeddings = model.get_embeddings([text])
        return embeddings[0].values
    except Exception as e:
        logger.warning(f"Fallback local/mock d'embedding (Vertex AI non accessible directement) : {e}")
        # Vecteur de dimension 768 normalisé pour les tests hors ligne
        import hashlib
        h = hashlib.sha256(text.encode()).digest()
        vec = [(float(b) / 255.0) - 0.5 for b in h]
        # Étendre à 768 dimensions
        full_vec = (vec * (768 // len(vec) + 1))[:768]
        norm = sum(x**2 for x in full_vec) ** 0.5
        return [x / norm for x in full_vec]


def hybrid_search(
    query_text: str,
    conn,
    city: Optional[str] = None,
    theme: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Recherche sémantique hybride combinant :
    1. Distance Cosinus via l'opérateur pgvector <=>
    2. Filtres stricts SQL (Commune, Thématique, Montant financier)
    """
    query_vector = get_embedding(query_text)
    vector_str = f"[{','.join(str(x) for x in query_vector)}]"

    sql = """
    SELECT 
        deliberation_id,
        city,
        session_date,
        theme,
        title,
        summary,
        beneficiary,
        amount_eur,
        vote_result,
        gcs_pdf_uri,
        legal_references,
        key_entities,
        1 - (embedding <=> %s::vector) AS similarity_score
    FROM deliberations
    WHERE 1=1
    """
    params = [vector_str]

    if city:
        sql += " AND city ILIKE %s"
        params.append(f"%{city}%")
    if theme:
        sql += " AND theme ILIKE %s"
        params.append(f"%{theme}%")
    if min_amount is not None:
        sql += " AND amount_eur >= %s"
        params.append(min_amount)
    if max_amount is not None:
        sql += " AND amount_eur <= %s"
        params.append(max_amount)

    sql += " ORDER BY embedding <=> %s::vector ASC LIMIT %s;"
    params.extend([vector_str, limit])

    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        results = cur.fetchall()

    return [dict(r) for r in results]
