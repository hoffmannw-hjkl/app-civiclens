> 🇫🇷 **[Version Française](README.md)** | 🇬🇧 **[English Version](README-EN.md)**
>
> 🔗 **EMEA SPARK Ecosystem:**
> This repository contains the **application source code and deployment manifests** for CivicLens. To deploy the underlying cloud infrastructure (Private GKE Autopilot, Cloud Armor WAF, IAP, Backup DR, FinOps), use the **[GCP AI Foundation Blueprint (cloud-gtm/gcp-ai-foundation-blueprint)](https://github.com/cloud-gtm/gcp-ai-foundation-blueprint)**.

# 🏛️ CivicLens Application (`app-civiclens`)

[![EMEA SPARK Asset](https://img.shields.io/badge/SPARK_Build-EMEA_Asset-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white)](https://github.com/cloud-gtm/app-civiclens)
[![SPARK Pillar](https://img.shields.io/badge/SPARK_Pillar-Customer_Solutions_%26_AI-34A853?style=for-the-badge)](https://goto.google.com/emea-spark-overview-page)
[![GitHub Repository](https://img.shields.io/badge/GitHub-cloud--gtm%2Fapp--civiclens-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/cloud-gtm/app-civiclens)
[![GCP Blueprint Companion](https://img.shields.io/badge/Infrastructure-GCP_AI_Foundation_Blueprint-EA4335?style=for-the-badge)](https://github.com/cloud-gtm/gcp-ai-foundation-blueprint)

Citizen Artificial Intelligence & public decision-support platform on Google Cloud. **CivicLens** analyzes certified local public accounts (M14 / M57) across **100% of all 35,000 French municipalities (DGFiP & OFGL 2000-2025)**, ingests municipal council acts (PDF), and executes natural language decision-support queries using **Vertex AI Gemini**.

---

## 🌟 Key Application Features

- **Exhaustive Municipal Observatory:** 100% coverage of all 35,000 French cities, tracking debt evolution, operational rigidity, and gross savings capacity.
- **M57 PDF Executive Audit Generator:** On-the-fly, high-fidelity vector PDF generation ready for municipal commissions and financial committees.
- **Territorial Duel & Benchmark:** Side-by-side comparison with impartial strategic arbitration powered by **Gemini 2.5 Flash / Pro**.
- **BigQuery AI Lakehouse & Text-to-SQL:** Natural language queries compiled to GoogleSQL with zero-spill safeguards (100 MB max scan limit).
- **Hybrid Semantic Search & RAG:** Vector database with PostgreSQL (`pgvector` HNSW indexing) and Google Cloud embeddings (`text-embedding-005`).

---

## 🏗️ Repository Layout

```text
app-civiclens/
├── src/                           # 🧠 Application Source Code
│   ├── backend/                   # FastAPI service (RAG, Gemini, BigQuery Lakehouse, pgvector)
│   ├── frontend/                  # Web UI & citizen explorer
│   ├── ingestion/                 # Open Data ingestion pipeline & PDF vision analysis
│   └── Dockerfile                 # Multi-stage optimized Docker build (Python 3.11-slim)
│
├── deploy/                        # 📦 Deployment Manifests
│   └── k8s/                       # GKE Autopilot manifests (Workload Identity, IAP, Ingress)
│
├── scripts/                       # ⚡ Automation Scripts
│   ├── deploy-to-blueprint.sh     # One-click deployment script targeting the GCP Blueprint
│   └── sync-gtm.sh                # Git synchronization script for cloud-gtm repository
│
└── docs/                          # 📚 Documentation
    └── DEPLOYMENT_GUIDE.md        # Comprehensive deployment and integration guide
```

---

## 🚀 Quick Deployment to Blueprint

If you already have provisioned the [GCP AI Foundation Blueprint](https://github.com/cloud-gtm/gcp-ai-foundation-blueprint):

```bash
# 1. Clone this application repository
git clone https://github.com/cloud-gtm/app-civiclens.git
cd app-civiclens

# 2. Deploy with a single command (Container build + manifest injection + kubectl apply via IAP Bastion)
./scripts/deploy-to-blueprint.sh --blueprint-dir=/path/to/gcp-ai-foundation-blueprint
```

For step-by-step manual deployment instructions, refer to the **[Deployment Guide](docs/DEPLOYMENT_GUIDE.md)**.

---

## 🔒 Security & Google Cloud Integration

- **Zero Static Credentials:** Fully authenticated via **Workload Identity** (no JSON service account keys).
- **Identity-Aware Proxy (IAP) Protection:** User authentication delegated to Google Cloud Edge, eliminating custom authentication code vulnerabilities.
- **WAF Security:** Shielded by **Google Cloud Armor** with OWASP Top 10 mitigation rules.

---

## 🤖 Dual-Layer Agentic Architecture (Google ADK 2.0 Swarm & M1L1 Skills)

This repository implements a two-tier Agentic AI architecture for municipal public finance auditing (French M57 accounting standard):

### 1. Layer 2 (Production Runtime) — Google ADK 2.0 Multi-Agent Swarm (`civic_swarm_adk.py`)
Exposed via FastAPI endpoints **`GET /api/agents/catalog`** and **`POST /api/agents/swarm-audit`**:
1. **`SupervisorAgent` (Lead Orchestrator)**: Analyzes citizen or auditor intent and dynamically routes tasks across specialized subagents.
2. **`BudgetSQLAgent` (M57 Accounting & BigQuery Analyst)**: Generates and executes read-only SQL queries (`SELECT`/`WITH`) against the BigQuery Lakehouse (`civic_budget_lakehouse.m57_budget_lines`) and OFGL datasets, strictly separating Operating (`011`, `012`, `65`) vs Investment (`20`, `21`, `23`) budget chapters.
3. **`DeliberationAuditorAgent` (`pgvector` & Bercy Open Data Auditor)**: Retrieves municipal council deliberations and legal decrees via semantic vector search (`text-embedding-004`).
4. **`CrossCheckAuditAgent` (Cross-Examination Compliance Auditor)**: Cross-examines voted council resolutions (PDF) against actual executed budget lines (SQL) and computes a **Budget Compliance Score (`/100`)**.

### 2. Layer 1 (AI-Assisted Engineering) — Repo Subagents & M1L1 Skill (`.agents/`)
Automatically discovered by **Jetski**, **Antigravity**, and **Gemini CLI** (see [`AGENTS.md`](AGENTS.md)):
- **Specialized Subagents (`.agents/agents/`)**:
  - **[`data-governance-steward`](.agents/agents/data-governance-steward.md)**: BigQuery Lakehouse schema governance, French M57 municipal accounting rules, `pgvector` indexing, and GDPR compliance.
  - **[`fastapi-adk-architect`](.agents/agents/fastapi-adk-architect.md)**: Google ADK 2.0 multi-agent orchestration, FastAPI SSE routes, and GKE Workload Identity bindings.
- **M1L1 Procedural Skill (`civiclens-verification`)**:
  - **Reference**: [`.agents/skills/civiclens-verification/SKILL.md`](.agents/skills/civiclens-verification/SKILL.md)
  - **Automated Gatekeeper Script (`verify.sh`)**:
    ```bash
    ./.agents/skills/civiclens-verification/scripts/verify.sh
    ```
    Validates Python syntax compilation (`py_compile`), verifies the 4-agent ADK 2.0 Swarm, checks GKE Autopilot manifest alignment (`deploy/gke/civiclens-manifest.yaml`), and cleans up `__pycache__` artifacts before git commits.

---

## 📄 License
Apache License 2.0. See [LICENSE](LICENSE) for more details.

