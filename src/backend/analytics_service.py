# -*- coding: utf-8 -*-
"""
analytics_service.py - Service Analytique BigQuery & Génération de Rapports PDF pour CivicLens.
Architecture Google Cloud :
- BigQuery Studio (Dataset 'civiclens_finances', Table partitionnée 'balances_communes')
- Text-to-SQL & Synthèse Assistée par Vertex AI Gemini
- Générateur de Rapports d'Audit Budgétaire Officiels (PDF haute fidélité via ReportLab)
- Export Cloud Storage signé
"""

import os
import io
import re
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm

logger = logging.getLogger("CivicLensAnalytics")

PROJECT_ID = os.environ.get("GCP_PROJECT", "wh-djvagl")
DATASET_ID = "civiclens_finances"
TABLE_ID = "balances_communes"
REPORTS_BUCKET = os.environ.get("REPORTS_BUCKET", f"{PROJECT_ID}-civiclens-reports")


def generate_audit_pdf(
    commune_data: Dict[str, Any],
    audit_text: str,
    output_stream: Optional[io.BytesIO] = None
) -> bytes:
    """
    Génère un document PDF d'audit budgétaire officiel haute fidélité aux normes M57.
    """
    buf = output_stream or io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    
    # Styles personnalisés
    style_title = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=4
    )
    style_subtitle = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=15
    )
    style_h2 = ParagraphStyle(
        'SectionH2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#0369a1"),
        spaceBefore=12,
        spaceAfter=6
    )
    style_body = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6
    )
    style_callout = ParagraphStyle(
        'Callout',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#475569")
    )

    story = []

    commune_nom = commune_data.get("nom", "Commune")
    dep = commune_data.get("departement", "")
    pop = commune_data.get("population", 0)
    lm = commune_data.get("latest_metrics", {})
    annee = lm.get("annee", "2025")

    # En-tête officiel
    story.append(Paragraph(f"Rapport d'Audit Budgétaire & Trajectoire Financière", style_title))
    story.append(Paragraph(f"Collectivité : <b>{commune_nom}</b> ({dep}) • Exercice certifié M57 : <b>{annee}</b> • Population : <b>{pop:,} hab.</b>", style_subtitle))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284c7"), spaceAfter=15))

    # Tableau des Chiffres Clés Consolidés
    story.append(Paragraph("1. Indicateurs Budgétaires Certifiés (DGFiP / OFGL)", style_h2))

    data_table = [
        ["Agrégat Comptable (M14 / M57)", "Montant Global (M€)", "Ratio par Habitant (€/hab)", "Appréciation"],
        [
            "Dépenses réelles de fonctionnement",
            f"{(lm.get('depenses_fonctionnement', 0)/1e6):.2f} M€",
            f"{lm.get('depenses_fonctionnement_par_hab', 0):.0f} €/hab",
            "Charges courantes"
        ],
        [
            "Recettes réelles de fonctionnement",
            f"{(lm.get('recettes_fonctionnement', 0)/1e6):.2f} M€",
            f"{lm.get('recettes_fonctionnement_par_hab', 0):.0f} €/hab",
            "Ressources fiscales et DGF"
        ],
        [
            "Épargne brute (CAF)",
            f"{(lm.get('epargne_brute', 0)/1e6):.2f} M€",
            f"{lm.get('epargne_brute_par_hab', 0):.0f} €/hab",
            "Capacité d'autofinancement"
        ],
        [
            "Dépenses réelles d'équipement",
            f"{(lm.get('depenses_equipement', 0)/1e6):.2f} M€",
            f"{lm.get('depenses_equipement_par_hab', 0):.0f} €/hab",
            "Effort d'investissement"
        ],
        [
            "Encours de dette au 31/12",
            f"{(lm.get('encours_dette', 0)/1e6):.2f} M€",
            f"{lm.get('encours_dette_par_hab', 0):.0f} €/hab",
            "Solvabilité globale"
        ],
        [
            "Capacité de désendettement",
            f"{lm.get('capacite_desendettement_annees', 'N/A')} ans",
            "-",
            "Seuil d'alerte national: 10-12 ans"
        ]
    ]

    t = Table(data_table, colWidths=[200, 100, 110, 110])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8.5),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))

    # Synthèse d'Audit Rédigée par Vertex AI Gemini
    story.append(Paragraph("2. Synthèse d'Évaluation & Perspectives (Inférence Vertex AI Gemini)", style_h2))

    clean_text = audit_text.replace("###", "").replace("**", "")
    for paragraph in clean_text.split("\n\n"):
        p_strip = paragraph.strip()
        if p_strip:
            story.append(Paragraph(p_strip, style_body))

    story.append(Spacer(1, 15))

    # Pied de page légal et souverain
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=8))
    footer_text = f"Document certifié conforme généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} par la plateforme CivicLens • Modèle souverain Vertex AI (europe-west1) • Sources : DGFiP / OFGL (Nomenclature M57 certifiée)."
    story.append(Paragraph(footer_text, style_callout))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def build_chart_payload(
    rows: List[Dict[str, Any]],
    user_query: str,
    suggested_title: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Analyse les résultats BigQuery pour déterminer si une visualisation graphique (Chart.js)
    est pertinente, et construit la structure des données (labels, datasets, options, unit).
    """
    if not rows or len(rows) < 1:
        return None

    first = rows[0]
    keys = list(first.keys())

    # Identifier colonnes numériques et colonnes textuelles/catégorielles
    numeric_cols = []
    text_cols = []
    for k in keys:
        val = None
        for r in rows:
            if r.get(k) is not None:
                val = r.get(k)
                break
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            numeric_cols.append(k)
        else:
            text_cols.append(k)

    if not numeric_cols:
        return None

    # Choix du label d'axe X
    label_col = None
    for cand in ["nom_commune", "commune", "nom", "agregat", "exercice", "annee", "date_exercice", "nom_departement"]:
        if cand in keys:
            label_col = cand
            break
    if not label_col and text_cols:
        label_col = text_cols[0]
    elif not label_col and "exercice" in numeric_cols:
        label_col = "exercice"

    if not label_col:
        return None

    # Choix des colonnes métriques
    metric_cols = [c for c in numeric_cols if c != label_col and c not in ["code_insee", "code_departement", "id"]]
    if "exercice" in metric_cols and label_col != "exercice":
        metric_cols.remove("exercice")

    if not metric_cols:
        return None

    # Détection de multi-séries (ex: nom_commune ET agregat)
    is_multi_series = False
    series_col = None
    if label_col in ["nom_commune", "commune"] and "agregat" in text_cols:
        agregats = set(str(r.get("agregat")) for r in rows if r.get("agregat"))
        if len(agregats) > 1:
            series_col = "agregat"
            is_multi_series = True
    elif label_col == "agregat" and any(c in text_cols for c in ["nom_commune", "commune"]):
        c_col = "nom_commune" if "nom_commune" in text_cols else "commune"
        cities = set(str(r.get(c_col)) for r in rows if r.get(c_col))
        if len(cities) > 1:
            series_col = c_col
            is_multi_series = True

    # Déterminer le type de graphique : line si série temporelle, bar sinon
    chart_type = "bar"
    if label_col in ["exercice", "annee", "date_exercice", "year"]:
        chart_type = "line"

    # Détection de l'unité
    primary_metric = metric_cols[0]
    unit = "€"
    if any(term in primary_metric.lower() for term in ["habitant", "par_hab", "hab"]):
        unit = "€/hab"
    elif any(term in primary_metric.lower() for term in ["pourcentage", "taux", "pct"]):
        unit = "%"
    elif any(term in primary_metric.lower() for term in ["annee", "delai"]):
        unit = "ans"
    elif "population" in primary_metric.lower():
        unit = "hab."
    elif any(term in primary_metric.lower() for term in ["montant", "total", "recettes", "depenses"]):
        unit = "€"

    # Titre du graphique
    chart_title = suggested_title
    if not chart_title:
        metric_disp = primary_metric.replace("_", " ").title()
        if "top" in user_query.lower():
            chart_title = f"Classement comparatif ({metric_disp})"
        elif "evolution" in user_query.lower() or "évolution" in user_query.lower() or chart_type == "line":
            chart_title = f"Évolution temporelle ({metric_disp})"
        elif "compare" in user_query.lower() or "différence" in user_query.lower():
            chart_title = f"Comparaison budgétaire ({metric_disp})"
        else:
            chart_title = f"Visualisation : {metric_disp}"

    # Construction des labels et datasets
    if is_multi_series and series_col:
        unique_labels = []
        for r in rows:
            l = str(r.get(label_col) or "")
            if l and l not in unique_labels:
                unique_labels.append(l)

        unique_series = []
        for r in rows:
            s = str(r.get(series_col) or "")
            if s and s not in unique_series:
                unique_series.append(s)

        data_matrix = {s: {l: 0.0 for l in unique_labels} for s in unique_series}
        for r in rows:
            l = str(r.get(label_col) or "")
            s = str(r.get(series_col) or "")
            v = r.get(primary_metric)
            if v is not None and s in data_matrix and l in data_matrix[s]:
                try:
                    data_matrix[s][l] = float(v)
                except (ValueError, TypeError):
                    pass

        datasets = []
        palette = [
            {"bg": "rgba(217, 119, 6, 0.85)", "border": "#d97706"},   # amber
            {"bg": "rgba(2, 132, 199, 0.85)", "border": "#0284c7"},   # sky
            {"bg": "rgba(99, 102, 241, 0.85)", "border": "#6366f1"},  # indigo
            {"bg": "rgba(16, 185, 129, 0.85)", "border": "#10b981"},  # emerald
            {"bg": "rgba(244, 63, 94, 0.85)", "border": "#f43f5e"},   # rose
            {"bg": "rgba(168, 85, 247, 0.85)", "border": "#a855f7"},  # purple
        ]

        for i, s in enumerate(unique_series[:6]):
            color = palette[i % len(palette)]
            series_data = [data_matrix[s][l] for l in unique_labels]
            datasets.append({
                "label": s,
                "data": series_data,
                "backgroundColor": color["bg"],
                "borderColor": color["border"],
                "borderWidth": 1.5,
                "borderRadius": 6 if chart_type == "bar" else 0,
                "tension": 0.3 if chart_type == "line" else 0,
                "fill": chart_type != "line"
            })

        return {
            "can_visualize": True,
            "type": chart_type,
            "title": chart_title,
            "labels": unique_labels,
            "datasets": datasets,
            "unit": unit,
            "metric_name": primary_metric.replace("_", " ").title()
        }

    else:
        labels = [str(r.get(label_col) or f"Ligne {i+1}") for i, r in enumerate(rows[:15])]
        
        if len(metric_cols) == 1:
            values = []
            for r in rows[:15]:
                try:
                    values.append(float(r.get(primary_metric) or 0))
                except (ValueError, TypeError):
                    values.append(0.0)

            dataset = {
                "label": primary_metric.replace("_", " ").title(),
                "data": values,
                "backgroundColor": "rgba(217, 119, 6, 0.85)",
                "borderColor": "#d97706",
                "borderWidth": 1.5,
                "borderRadius": 6 if chart_type == "bar" else 0,
                "tension": 0.3 if chart_type == "line" else 0,
                "fill": chart_type != "line"
            }
            datasets = [dataset]
        else:
            palette = [
                {"bg": "rgba(217, 119, 6, 0.85)", "border": "#d97706"},   # amber
                {"bg": "rgba(2, 132, 199, 0.85)", "border": "#0284c7"},   # sky
                {"bg": "rgba(99, 102, 241, 0.85)", "border": "#6366f1"},  # indigo
                {"bg": "rgba(16, 185, 129, 0.85)", "border": "#10b981"},  # emerald
            ]
            datasets = []
            for i, m_col in enumerate(metric_cols[:4]):
                c = palette[i % len(palette)]
                vals = []
                for r in rows[:15]:
                    try:
                        vals.append(float(r.get(m_col) or 0))
                    except (ValueError, TypeError):
                        vals.append(0.0)
                datasets.append({
                    "label": m_col.replace("_", " ").title(),
                    "data": vals,
                    "backgroundColor": c["bg"],
                    "borderColor": c["border"],
                    "borderWidth": 1.5,
                    "borderRadius": 6 if chart_type == "bar" else 0,
                    "tension": 0.3 if chart_type == "line" else 0,
                    "fill": chart_type != "line"
                })

        return {
            "can_visualize": True,
            "type": chart_type,
            "title": chart_title,
            "labels": labels,
            "datasets": datasets,
            "unit": unit,
            "metric_name": primary_metric.replace("_", " ").title()
        }


def run_bigquery_natural_language_query(user_query: str) -> Dict[str, Any]:
    """
    Traduit une question en langage naturel en requête SQL BigQuery via Gemini,
    l'exécute de façon sécurisée (Read-Only), construit une visualisation graphique si pertinent
    et génère la synthèse des résultats.
    """
    import vertexai
    from google.cloud import bigquery
    from google.cloud import aiplatform
    from vertexai.generative_models import GenerativeModel, GenerationConfig

    # Gemini 3.6 Flash est hébergé sur le point de terminaison global Vertex AI
    vertexai.init(project=PROJECT_ID, location="global")
    aiplatform.init(project=PROJECT_ID, location="global")
    model = GenerativeModel("gemini-3.6-flash")

    schema_info = """
Table: `wh-djvagl.civiclens_finances.balances_communes`
Périmètre: Intégralité des ~1 260 communes d'Île-de-France (départements 75, 77, 78, 91, 92, 93, 94, 95) + métropoles nationales pilotes.
Colonnes:
- date_exercice (DATE)
- exercice (INTEGER, historique disponible : 2021 à 2025)
- code_insee (STRING, ex: '75056', '93055')
- nom_commune (STRING, ex: 'Paris', 'Pantin', 'Boulogne-Billancourt', 'Versailles')
- code_departement (STRING, ex: '75', '92', '93', '78', '91', '94', '95', '77')
- nom_departement (STRING, ex: 'Paris', 'Seine-Saint-Denis', 'Hauts-de-Seine', 'Yvelines')
- nom_epci (STRING)
- population (INTEGER)
- agregat (STRING, valeurs exemples: 'Dépenses de fonctionnement', 'Dépenses d\'équipement', 'Encours de dette', 'Epargne brute', 'Frais de personnel', 'Recettes de fonctionnement', 'Fiscalité reversée', 'Impôts locaux', 'Dotation globale de fonctionnement', 'Achats et charges externes', 'Charges financières', 'Epargne nette')
- montant (FLOAT)
- euros_par_habitant (FLOAT)
"""

    prompt_sql = f"""Tu es un expert BigQuery SQL pour les finances publiques locales françaises.
Génère une unique requête SQL GoogleSQL SELECT sécurisée répondant à la question.
RÈGLES STRICTES :
1. Renvoie UNIQUEMENT le code SQL dans un bloc ```sql ... ```.
2. Limite toujours avec LIMIT 20 maximum pour éviter les scans volumineux.
3. Requête uniquement la table `wh-djvagl.civiclens_finances.balances_communes`.
4. N'utilise JAMAIS de commandes DROP, DELETE, INSERT, UPDATE, ALTER.
5. GESTION TEMPORELLE (EXERCICE) :
   - Inclure TOUJOURS la colonne `exercice` dans le SELECT pour expliciter l'année concernée.
   - Si la question porte sur un état présent, une liste ou un classement sans préciser d'année ou sans demander explicitement un historique/une évolution dans le temps, filtre sur le dernier exercice disponible (ex: `exercice = (SELECT MAX(exercice) FROM `wh-djvagl.civiclens_finances.balances_communes`)`).
   - Si une année spécifique est demandée (ex: 2024, 2025), filtre sur `exercice = 2024` ou `exercice = 2025`.

SCHÉMA DE LA TABLE :
{schema_info}

QUESTION :
"{user_query}"
"""

    try:
        res_sql = model.generate_content(prompt_sql, generation_config=GenerationConfig(temperature=0.0, max_output_tokens=4000))
        
        # Vérifier si la génération a été interrompue prématurément par un quota de tokens
        candidate = res_sql.candidates[0] if res_sql.candidates else None
        if candidate and candidate.finish_reason and candidate.finish_reason.name == "MAX_TOKENS":
            raise ValueError("Génération SQL incomplète (dépassement de tokens). Veuillez reformuler la question.")

        raw_sql = res_sql.text
        # Extraction du bloc SQL
        m = re.search(r"```(?:sql)?\s*(.*?)(?:```|$)", raw_sql, re.DOTALL | re.IGNORECASE)
        sql_query = m.group(1).strip() if m else raw_sql.strip()

        # Nettoyage résiduel d'éventuels backticks
        sql_query = re.sub(r"^```(?:sql)?\s*", "", sql_query, flags=re.IGNORECASE)
        sql_query = re.sub(r"```\s*$", "", sql_query).strip()

        # Vérification de complétude minimale de la requête SQL
        if not re.search(r"\b(FROM|WHERE|LIMIT)\b", sql_query, re.IGNORECASE):
            raise ValueError("La requête SQL générée est incomplète ou tronquée.")

        # Sécurité : nettoyage des commentaires pour vérification de la structure SQL
        cleaned_sql = re.sub(r"/\*.*?\*/", "", sql_query, flags=re.DOTALL)
        cleaned_sql = re.sub(r"--[^\n]*", "", cleaned_sql).strip()

        # Vérification lecture seule : doit débuter par SELECT ou WITH (CTEs)
        if not re.match(r"^(SELECT|WITH)\b", cleaned_sql, re.IGNORECASE):
            raise ValueError("Seules les requêtes SELECT / WITH en lecture seule sont autorisées.")

        # Vérification stricte anti-DML / anti-DDL
        forbidden = r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|TRUNCATE|MERGE|CREATE|GRANT|REVOKE)\b"
        if re.search(forbidden, cleaned_sql, re.IGNORECASE):
            raise ValueError("Opération d'écriture ou de modification non autorisée détectée.")

        client = bigquery.Client(project=PROJECT_ID)
        job_config = bigquery.QueryJobConfig(maximum_bytes_billed=100 * 1024 * 1024) # Plafond 100 Mo par requête
        query_job = client.query(sql_query, job_config=job_config)
        rows = [dict(row) for row in query_job.result()]

        # Synthèse en langage naturel par Gemini
        prompt_summary = f"""Voici les résultats extraits de BigQuery pour la question: "{user_query}"
Données brutes SQL ({len(rows)} lignes) :
{json.dumps(rows[:10], default=str, ensure_ascii=False)}

Rédige une synthèse analytique claire, concise et pédagogique en 2 paragraphes en français avec les chiffres clés.
Si les données se prêtent à une visualisation graphique (classement, comparaison, évolution), termine impérativement par une dernière ligne :
TITRE_GRAPHIQUE: <Titre concis du graphique>
"""
        res_summary = model.generate_content(prompt_summary, generation_config=GenerationConfig(max_output_tokens=700, temperature=0.2))
        raw_summary = res_summary.text

        # Extraire le titre suggéré pour le graphique si présent
        suggested_title = None
        m_title = re.search(r"TITRE_GRAPHIQUE:\s*(.+)", raw_summary, re.IGNORECASE)
        if m_title:
            suggested_title = m_title.group(1).strip().strip('"').strip('*')
            summary_clean = re.sub(r"\n*TITRE_GRAPHIQUE:\s*.+", "", raw_summary, flags=re.IGNORECASE).strip()
        else:
            summary_clean = raw_summary.strip()

        # Construction intelligente du payload graphique
        chart_payload = build_chart_payload(rows=rows, user_query=user_query, suggested_title=suggested_title)

        return {
            "sql_query": sql_query,
            "row_count": len(rows),
            "rows": rows[:15],
            "summary": summary_clean,
            "chart": chart_payload
        }
    except Exception as e:
        logger.error(f"Erreur NLQ BigQuery: {e}")
        return {
            "error": str(e),
            "sql_query": None,
            "rows": [],
            "summary": f"Impossible d'exécuter l'analyse BigQuery : {e}",
            "chart": None
        }

