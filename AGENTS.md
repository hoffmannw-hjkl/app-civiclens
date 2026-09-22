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
| **`civiclens-verification`** | [`.agents/skills/civiclens-verification/SKILL.md`](.agents/skills/civiclens-verification/SKILL.md) | Quality assurance runbook (Python compilation, `pytest`, and GKE Autopilot / Cloud Armor manifest alignment). |
