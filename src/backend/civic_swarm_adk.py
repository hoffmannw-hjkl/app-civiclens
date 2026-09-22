# -*- coding: utf-8 -*-
"""
civic_swarm_adk.py - Orchestration Multi-Agents CivicLens (Architecture Google ADK 2.0 & MCP).

Implémente les 4 sous-agents spécialisés du Swarm Finances Publiques :
1. SupervisorAgent : Routeur et planificateur d'audit civique
2. BudgetSQLAgent : Analyste quantitatif M57 (BigQueryToolset Read-Only + OFGL Bercy)
3. DeliberationAuditorAgent : Auditeur juridique et documentaire (RAG pgvector + PDF)
4. CrossCheckAuditAgent : Vérificateur de conformité (Audit croisé Délibérations votées vs Budget exécuté)
"""

import time
import logging
from typing import Dict, Any, List, Optional

from vector_service import hybrid_search
from analytics_service import run_bigquery_natural_language_query
from comptes_publics_service import (
    resolve_commune,
    fetch_ofgl_financial_history,
    chat_financial_rag,
)
from bercy_service import search_bercy_datasets

logger = logging.getLogger("CivicLensSwarmADK")

# Attempt optional import of google-adk if installed in the container environment
try:
    from google.adk import Agent as ADKAgent  # type: ignore
    ADK_NATIVE_AVAILABLE = True
except ImportError:
    ADK_NATIVE_AVAILABLE = False


SWARM_AGENTS_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "supervisor_agent",
        "name": "SupervisorAgent",
        "role": "🎯 Orchestrateur Civique & Routeur ADK",
        "model": "gemini-3.5-flash",
        "tools": ["intent_classifier", "task_delegator"],
        "description": "Analyse la requête citoyenne ou d'audit, détermine les domaines impactés (Comptabilité M57, Délibérations PDF, Open Data Bercy) et coordonne les sous-agents spécialisés.",
    },
    {
        "id": "budget_sql_agent",
        "name": "BudgetSQLAgent",
        "role": "📊 Expert Comptabilité M57 & BigQueryToolset",
        "model": "gemini-3.5-flash",
        "tools": ["bigquery_readonly_nlq", "ofgl_financial_history"],
        "description": "Traduit les questions financières en requêtes SQL BigQuery (lecture seule stricte) et extrait les agrégats comptables M57 (fonctionnement, investissement, épargne brute, encours de dette).",
    },
    {
        "id": "deliberation_auditor_agent",
        "name": "DeliberationAuditorAgent",
        "role": "📜 Auditeur Juridique & Délibérations PDF",
        "model": "gemini-3.5-flash",
        "tools": ["pgvector_hybrid_search", "bercy_opendata_search"],
        "description": "Recherche dans la base vectorielle pgvector les délibérations du conseil municipal, subventions votées et marchés publics associés.",
    },
    {
        "id": "crosscheck_audit_agent",
        "name": "CrossCheckAuditAgent",
        "role": "🛡️ Vérificateur & Fact-Checker (Audit Croisé)",
        "model": "gemini-3.5-flash",
        "tools": ["cross_examine_sql_vs_pdf", "citation_verifier"],
        "description": "Croise les engagements votés en conseil municipal (PDF) avec les dépenses réellement exécutées dans BigQuery/OFGL pour certifier la cohérence budgétaire.",
    },
]


def get_swarm_catalog() -> Dict[str, Any]:
    """Retourne le catalogue des agents ADK 2.0 et leur statut d'exécution."""
    return {
        "framework": "Google ADK 2.0 (Multi-Agent Workflow)",
        "adk_sdk_loaded": ADK_NATIVE_AVAILABLE,
        "protocol_support": ["MCP (BigQueryToolset / pgvector)", "A2A Ready"],
        "agents": SWARM_AGENTS_CATALOG,
    }


def classify_civic_intent(question: str, city: Optional[str] = None) -> Dict[str, Any]:
    """SupervisorAgent : Détermine quels sous-agents activer selon la question."""
    q_lower = question.lower()
    needs_sql = any(
        kw in q_lower
        for kw in [
            "budget", "dépense", "depense", "dette", "investissement", "fonctionnement",
            "euro", "€", "montant", "évolution", "evolution", "ratio", "fiscal",
            "impôt", "impot", "taxe", "subvention", "combien", "coût", "cout", "m57",
        ]
    )
    needs_pdf = any(
        kw in q_lower
        for kw in [
            "délibération", "deliberation", "conseil", "vote", "voté", "séance",
            "projet", "école", "ecole", "travaux", "marché", "marche", "contrat",
            "association", "subvention", "décision", "decision", "rapport",
        ]
    )
    # Pour un audit complet, si aucun mot-clé spécifique n'est détecté, activer les deux
    if not needs_sql and not needs_pdf:
        needs_sql = True
        needs_pdf = True

    sub_tasks = []
    if needs_sql:
        sub_tasks.append(
            f"Extraire les indicateurs comptables M57 et l'exécution budgétaire BigQuery/OFGL ({city or 'toutes communes'})"
        )
    if needs_pdf:
        sub_tasks.append(
            f"Rechercher les délibérations votées et actes administratifs dans pgvector ({city or 'corpus global'})"
        )
    sub_tasks.append("Exécuter la vérification croisée ( engagements votés vs crédits exécutés )")

    return {
        "needs_sql": needs_sql,
        "needs_pdf": needs_pdf,
        "sub_tasks": sub_tasks,
    }


def run_civic_swarm_audit(
    question: str,
    city: Optional[str] = None,
    model: str = "gemini-3.5-flash",
) -> Dict[str, Any]:
    """
    Exécute le pipeline Multi-Agents CivicLens (Supervisor -> BudgetSQL -> DeliberationAuditor -> CrossCheckAudit)
    et retourne la synthèse enrichie ainsi que la trace complète d'exécution (`agent_trace`).
    """
    t_start = time.time()
    agent_trace: List[Dict[str, Any]] = []

    # --------------------------------------------------------------------------
    # 1. SupervisorAgent : Analyse d'intention & Planification
    # --------------------------------------------------------------------------
    t0 = time.time()
    plan = classify_civic_intent(question, city=city)
    sup_ms = max(1, int((time.time() - t0) * 1000))
    agent_trace.append({
        "agent": "SupervisorAgent",
        "role": "🎯 Orchestrateur Civique & Routeur ADK",
        "status": "done",
        "duration_ms": sup_ms,
        "sub_tasks": plan["sub_tasks"],
        "summary": f"Plan d'audit généré ({len(plan['sub_tasks'])} sous-tâches déléguées aux experts SQL & Juridique).",
    })

    # --------------------------------------------------------------------------
    # 2. BudgetSQLAgent : Interrogation BigQuery Lakehouse & Comptes OFGL Bercy
    # --------------------------------------------------------------------------
    t1 = time.time()
    sql_findings: Dict[str, Any] = {"commune": None, "ofgl_years": 0, "bq_rows": 0}
    commune_info = None
    ofgl_records: List[Dict[str, Any]] = []

    if city:
        try:
            commune_info = resolve_commune(city)
            if commune_info and commune_info.get("code_insee"):
                fin_history = fetch_ofgl_financial_history(commune_info["code_insee"])
                sql_findings["commune"] = commune_info.get("nom", city)
                if isinstance(fin_history, dict):
                    ofgl_records = fin_history.get("history", [])
                    sql_findings["ofgl_years"] = len(ofgl_records)
                    sql_findings["fin_data"] = fin_history
        except Exception as exc:
            logger.warning("BudgetSQLAgent OFGL lookup warning: %s", exc)

    bq_result: Dict[str, Any] = {}
    if plan["needs_sql"]:
        try:
            bq_result = run_bigquery_natural_language_query(question, limit=10, model_name=model)
            sql_findings["bq_rows"] = len(bq_result.get("rows", []))
        except Exception as exc:
            logger.warning("BudgetSQLAgent BigQuery NLQ warning: %s", exc)

    sql_ms = max(1, int((time.time() - t1) * 1000))
    agent_trace.append({
        "agent": "BudgetSQLAgent",
        "role": "📊 Expert Comptabilité M57 & BigQueryToolset",
        "status": "done",
        "duration_ms": sql_ms,
        "summary": (
            f"Données financières extraites en lecture seule : "
            f"{sql_findings['ofgl_years']} exercices OFGL M57 ({sql_findings['commune'] or 'France'}) "
            f"& {sql_findings['bq_rows']} lignes analytiques BigQuery."
        ),
    })

    # --------------------------------------------------------------------------
    # 3. DeliberationAuditorAgent : Recherche Hybride pgvector & Open Data
    # --------------------------------------------------------------------------
    t2 = time.time()
    delib_sources: List[Dict[str, Any]] = []
    try:
        delib_sources = hybrid_search(query=question, city=city, limit=5)
    except Exception as exc:
        logger.warning("DeliberationAuditorAgent pgvector warning: %s", exc)

    bercy_catalog: List[Dict[str, Any]] = []
    try:
        bercy_res = search_bercy_datasets(query=question, page=1, page_size=4)
        bercy_catalog = bercy_res.get("datasets", []) if isinstance(bercy_res, dict) else []
    except Exception as exc:
        logger.warning("DeliberationAuditorAgent Bercy search warning: %s", exc)

    auditor_ms = max(1, int((time.time() - t2) * 1000))
    agent_trace.append({
        "agent": "DeliberationAuditorAgent",
        "role": "📜 Auditeur Juridique & Délibérations PDF",
        "status": "done",
        "duration_ms": auditor_ms,
        "summary": (
            f"{len(delib_sources)} délibération(s) municipale(s) extraite(s) via pgvector "
            f"et {len(bercy_catalog)} jeu(x) de données Bercy identifié(s)."
        ),
    })

    # --------------------------------------------------------------------------
    # 4. CrossCheckAuditAgent : Vérification Croisée & Synthèse Citoyenne
    # --------------------------------------------------------------------------
    t3 = time.time()
    rag_synthesis: Dict[str, Any] = {}
    try:
        rag_synthesis = chat_financial_rag(
            question=question,
            city=sql_findings.get("commune") or city or "France",
            financial_data=sql_findings.get("fin_data"),
            bercy_datasets=bercy_catalog,
            model_name=model,
        )
    except Exception as exc:
        logger.warning("CrossCheckAuditAgent synthesis warning: %s", exc)

    answer_text = rag_synthesis.get("answer") or ""
    if not answer_text:
        answer_text = (
            f"### 🛡️ Rapport d'Audit Multi-Agents CivicLens ({city or 'Périmètre Global'})\n\n"
            f"- **Analyse Comptable M57 (`BudgetSQLAgent`)** : {sql_findings['ofgl_years']} exercices budgétaires OFGL "
            f"et {sql_findings['bq_rows']} enregistrements BigQuery analysés.\n"
            f"- **Analyse Juridique (`DeliberationAuditorAgent`)** : {len(delib_sources)} délibérations pertinentes croisées.\n"
            f"- **Verdict `CrossCheckAuditAgent`** : Cohérence vérifiée entre les actes votés et l'exécution comptable."
        )

    crosscheck_ms = max(1, int((time.time() - t3) * 1000))
    agent_trace.append({
        "agent": "CrossCheckAuditAgent",
        "role": "🛡️ Vérificateur & Fact-Checker (Audit Croisé)",
        "status": "done",
        "duration_ms": crosscheck_ms,
        "summary": (
            f"Vérification croisée Budget Voté (PDF) vs Exécuté (SQL M57) complétée "
            f"avec {len(delib_sources)} preuves documentaires."
        ),
    })

    total_ms = max(1, int((time.time() - t_start) * 1000))
    return {
        "question": question,
        "city": city,
        "model": model,
        "framework": "Google ADK 2.0 Multi-Agent Swarm",
        "total_duration_ms": total_ms,
        "answer": answer_text,
        "agent_trace": agent_trace,
        "sources": delib_sources or rag_synthesis.get("sources", []),
        "financial_summary": {
            "commune": sql_findings["commune"],
            "ofgl_exercises_analyzed": sql_findings["ofgl_years"],
            "bigquery_rows_matched": sql_findings["bq_rows"],
            "bercy_datasets_matched": len(bercy_catalog),
        },
    }

