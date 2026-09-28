# Specialized AI Agents & Skills — `app-civiclens` / `civiclens`

This repository implements the **Google Cloud Elevate 2026 & EMEA SPARK** AI-Native Software Engineering architecture. It embeds specialized subagents (`.agents/agents/`) and procedural skills (`.agents/skills/`) discovered automatically by **Jetski**, **Antigravity**, and **Gemini CLI**.

---

## 🤖 Specialized Repository Subagents (`.agents/agents/`)

| Subagent Name | Role & Specialization | When to Invoke (`invoke_subagent`) |
| :--- | :--- | :--- |
| **[`data-governance-steward`](.agents/agents/data-governance-steward.md)** | **Municipal Public Finance Data Steward** | When designing or auditing BigQuery Lakehouse schemas, French M57 municipal accounting SQL queries, `pgvector` deliberations indexing, or GDPR compliance. |
| **[`fastapi-adk-architect`](.agents/agents/fastapi-adk-architect.md)** | **FastAPI, Google ADK 2.0 & Multimodal AI Architect** | When orchestrating multi-agent workflows (`SupervisorAgent`, `BudgetSQLAgent`, `DeliberationAuditorAgent`, `CrossCheckAuditAgent`) or configuring GKE Workload Identity. |

---

## 🛠️ Repository Skills (`.agents/skills/`)

| Skill Name | Path | Description |
| :--- | :--- | :--- |
| **`civiclens-verification`** | [`.agents/skills/civiclens-verification/SKILL.md`](.agents/skills/civiclens-verification/SKILL.md) | Quality assurance runbook (Python compilation, ADK 2.0 4-agent verification, GKE Autopilot manifest alignment, and `__pycache__` cleanup). |

---

## 🎬 Quick Demo Prompts (How to Trigger Each Agent Live)

- **Trigger Runtime 4-Agent Google ADK 2.0 Swarm (REST API / Swagger `/docs`)**:
  ```bash
  curl -s -X POST http://localhost:8000/api/agents/swarm-audit \
    -H "Content-Type: application/json" \
    -d '{"query": "Audit M57 chapter 65 subsidies vs voted council deliberations", "commune": "Bordeaux", "exercice": 2024}' | jq .
  ```
- **Trigger `data-governance-steward` (IDE / CLI)**:
  > `"Invoke data-governance-steward to audit M57 operating (011/012/65) vs investment (20/21/23) chapter separation and read-only SQL guardrails in civic_swarm_adk.py."`
- **Trigger `fastapi-adk-architect` (IDE / CLI)**:
  > `"Invoke fastapi-adk-architect to review the 4-agent orchestration in civic_swarm_adk.py and verify GKE Workload Identity bindings."`
- **Run the M1L1 Gatekeeper Script**:
  ```bash
  ./.agents/skills/civiclens-verification/scripts/verify.sh
  ```

