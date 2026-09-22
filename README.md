> 🇫🇷 **[Version Française](README.md)** | 🇬🇧 **[English Version](README-EN.md)**
>
> 🔗 **Écosystème EMEA SPARK :**
> Ce dépôt contient le **code source et les manifests applicatifs** de CivicLens. Pour déployer l'infrastructure cloud sous-jacente (GKE Autopilot privé, Cloud Armor WAF, IAP, Backup DR, FinOps), utilisez le **[GCP AI Foundation Blueprint (cloud-gtm/gcp-ai-foundation-blueprint)](https://github.com/cloud-gtm/gcp-ai-foundation-blueprint)**.

# 🏛️ CivicLens Application (`app-civiclens`)

[![EMEA SPARK Asset](https://img.shields.io/badge/SPARK_Build-EMEA_Asset-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white)](https://github.com/cloud-gtm/app-civiclens)
[![SPARK Pillar](https://img.shields.io/badge/SPARK_Pillar-Customer_Solutions_%26_AI-34A853?style=for-the-badge)](https://goto.google.com/emea-spark-overview-page)
[![GitHub Repository](https://img.shields.io/badge/GitHub-cloud--gtm%2Fapp--civiclens-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/cloud-gtm/app-civiclens)
[![GCP Blueprint Companion](https://img.shields.io/badge/Infrastructure-GCP_AI_Foundation_Blueprint-EA4335?style=for-the-badge)](https://github.com/cloud-gtm/gcp-ai-foundation-blueprint)

Plateforme d'Intelligence Artificielle citoyenne et d'aide à la décision publique sur Google Cloud. **CivicLens** permet d'analyser en temps réel les comptes administratifs et balances comptables (M14 / M57) de **100% des 35 000 communes françaises (DGFiP & OFGL 2000-2025)**, d'ingérer des délibérations municipales (PDF) et d'effectuer des requêtes décisionnelles en langage naturel via **Vertex AI Gemini**.

---

## 🌟 Fonctionnalités Clés de l'Application

- **Observatoire Financier Intégral :** 35 000 communes françaises couvertes, évolution de la dette, rigidité des charges et capacité d'autofinancement (épargne brute).
- **Générateur de Rapports PDF M57 :** Synthèse d'audit haute-fidélité générée à la volée, prête pour les commissions municipales.
- **Benchmark & Duel de Communes :** Comparaison côte-à-côte avec arbitrage stratégique impartial rédigé par **Gemini 2.5 Flash / Pro**.
- **Data Lakehouse BigQuery Text-to-SQL :** Requêtage analytique en langage naturel directement traduit en GoogleSQL sécurisé avec garde-fou anti-surcoût (100 Mo max scan).
- **Recherche Sémantique Hybride & RAG :** Base vectorielle PostgreSQL (`pgvector` avec index HNSW) couplée aux modèles d'embedding Google Cloud (`text-embedding-005`).

---

## 🏗️ Structure du Dépôt

```text
app-civiclens/
├── src/                           # 🧠 Code Source Applicatif
│   ├── backend/                   # API FastAPI (RAG, Gemini, BigQuery Lakehouse, pgvector)
│   ├── frontend/                  # Interface web citoyenne & explorateur
│   ├── ingestion/                 # Pipeline Open Data (data.gouv.fr) & analyse vision PDF
│   └── Dockerfile                 # Image multi-stage optimisée (Python 3.11-slim)
│
├── deploy/                        # 📦 Manifests de Déploiement
│   └── k8s/                       # Manifests GKE Autopilot (Workload Identity, IAP, Ingress)
│
├── scripts/                       # ⚡ Scripts d'Automatisation
│   ├── deploy-to-blueprint.sh     # Déploiement "One-Click" sur le Blueprint GCP
│   └── sync-gtm.sh                # Synchronisation Git vers le dépôt officiel cloud-gtm
│
└── docs/                          # 📚 Documentation Technique
    └── DEPLOYMENT_GUIDE.md        # Guide complet de déploiement et d'intégration
```

---

## 🚀 Déploiement Rapide sur le Blueprint

Si vous avez déjà déployé le [GCP AI Foundation Blueprint](https://github.com/cloud-gtm/gcp-ai-foundation-blueprint) :

```bash
# 1. Cloner ce dépôt applicatif
git clone https://github.com/cloud-gtm/app-civiclens.git
cd app-civiclens

# 2. Déployer en une commande (build conteneur + injection manifests + kubectl apply via Bastion IAP)
./scripts/deploy-to-blueprint.sh --blueprint-dir=/chemin/vers/gcp-ai-foundation-blueprint
```

Pour les instructions détaillées de déploiement manuel ou pas-à-pas, consultez le **[Guide de Déploiement](docs/DEPLOYMENT_GUIDE.md)**.

---

## 🔒 Sécurité & Intégration Google Cloud

- **Zéro Clé Statique :** L'application utilise nativement **Workload Identity** pour s'authentifier auprès de Vertex AI, BigQuery et Cloud Storage.
- **Accès Sécurisé par IAP :** L'accès web est protégé en amont par **Identity-Aware Proxy (IAP)**, garantissant une authentification Google Workspace sans exposition directe de code d'authentification.
- **Résilience WAF :** Protégé par **Google Cloud Armor** contre les attaques du Top 10 OWASP.

---

## 🤖 Architecture Agentique Dual-Layer (Swarm Google ADK 2.0 & M1L1 Skills)

Ce dépôt implémente une architecture agentique à deux niveaux pour l'audit des finances publiques municipales (nomenclature M57) :

### 1. Couche 2 (Runtime Production) — Swarm Multi-Agents Google ADK 2.0 (`civic_swarm_adk.py`)
Exposé via les routes FastAPI **`GET /api/agents/catalog`** et **`POST /api/agents/swarm-audit`** :
1. **`SupervisorAgent` (Orchestrateur Principal)** : Analyse l'intention citoyenne ou d'audit financier et route dynamiquement vers les sous-agents spécialisés.
2. **`BudgetSQLAgent` (Analyste Comptable M57 & BigQuery)** : Génère et exécute des requêtes SQL en lecture seule (`SELECT`/`WITH`) sur le Lakehouse BigQuery (`civic_budget_lakehouse.m57_budget_lines`) et les données OFGL, en distinguant Section de Fonctionnement (`011`, `012`, `65`) et Section d'Investissement (`20`, `21`, `23`).
3. **`DeliberationAuditorAgent` (Auditeur Sémantique `pgvector` & Open Data Bercy)** : Recherche les délibérations municipales et arrêtés votés en Conseil Municipal via recherche vectorielle (`text-embedding-004`).
4. **`CrossCheckAuditAgent` (Contrôleur de Conformité Croisée)** : Croise les engagements votés en délibération (PDF) avec les mandats effectivement exécutés en comptabilité M57 (SQL) et calcule un **Score de Conformité Budgétaire (`/100`)**.

### 2. Couche 1 (Ingénierie Assistée par IA) — Sous-Agents & Skill M1L1 (`.agents/`)
Découverts automatiquement par **Jetski**, **Antigravity** et **Gemini CLI** (voir [`AGENTS.md`](AGENTS.md)) :
- **Sous-Agents spécialisés (`.agents/agents/`)** :
  - **[`data-governance-steward`](.agents/agents/data-governance-steward.md)** : Gouvernance BigQuery Lakehouse, comptabilité publique française M57, indexation `pgvector` et conformité RGPD.
  - **[`fastapi-adk-architect`](.agents/agents/fastapi-adk-architect.md)** : Orchestration multi-agents Google ADK 2.0, routes FastAPI SSE et sécurité GKE Workload Identity.
- **Skill Procédural M1L1 (`civiclens-verification`)** :
  - **Référence** : [`.agents/skills/civiclens-verification/SKILL.md`](.agents/skills/civiclens-verification/SKILL.md)
  - **Script Gatekeeper (`verify.sh`)** :
    ```bash
    ./.agents/skills/civiclens-verification/scripts/verify.sh
    ```
    Vérifie la compilation Python (`py_compile`), l'intégrité du Swarm ADK 2.0 (`4 agents`), l'alignement des manifestes GKE Autopilot (`deploy/gke/civiclens-manifest.yaml`) et nettoie les caches `__pycache__` avant commit.

---

## 📄 Licence
Apache License 2.0. Voir [LICENSE](LICENSE) pour plus d'informations.

