---
name: civiclens-verification
description: >-
  Compiles and verifies Python FastAPI services, Google ADK 2.0 multi-agent workflows, and GKE Autopilot manifests for CivicLens.
  Use when the user asks to "verify civiclens", "test ADK swarm", "check M57 SQL queries",
  "compile Python backend", or "clean pycache before git commit".
---

# CivicLens Quality, ADK 2.0 & Deployment Runbook (`M1L1 Skills Framework` Compliant)

**Skill Patterns Combined**: *Tool Wrapper Skill* (Slide 13) • *Generator / Experience Before Theory* (Slide 14) • *Reviewer Checklist* (Slide 15) • *Workflow Skill* (Slide 16).

---

## 1. Tool Wrapper & Usage Recipes (Slide 13)

Use `python3 -m py_compile` to validate all FastAPI and ADK agent modules without leaving untracked `.pyc` artifacts in `__pycache__`:

```bash
PYTHON_BIN="python3"
```

### Usage
Always pass `-B` (`PYTHONDONTWRITEBYTECODE=1`) when importing or testing modules so `.pyc` files do not dirty the Git working tree:

```bash
PYTHONDONTWRITEBYTECODE=1 $PYTHON_BIN -m py_compile src/backend/*.py
```

---

## 2. Experience Before Theory — Known Gotchas (Slide 14)

The following real-world gotchas were discovered in production and must always be prevented:

1. **Untracked / Modified `__pycache__/*.pyc` Files Dirtying Git Status**:
   - *Gotcha*: Running `python3 -m py_compile` without `PYTHONDONTWRITEBYTECODE=1` modifies tracked `.pyc` files in `src/backend/__pycache__/`, causing `sync-gtm.sh` warnings (`Warning: 1 uncommitted change`).
   - *Rule*: Always run `git checkout -- "**/__pycache__/*"` and `rm -f src/backend/__pycache__/civic_swarm_adk.*.pyc` after compilation checks.
2. **Service Signature Alignment (`comptes_publics_service` & `bercy_service`)**:
   - *Gotcha*: `resolve_commune(city)` returns `code_insee` (not `insee`), and `search_bercy_datasets` expects `page=1, page_size=4` and returns `{"datasets": [...]}`.
   - *Rule*: Always access `commune_info.get("code_insee")` and `bercy_res.get("datasets", [])` inside ADK subagents (`civic_swarm_adk.py`).
3. **Read-Only BigQuery Guardrails for Public Finance Data**:
   - *Rule*: Ensure `BudgetSQLAgent` queries strictly enforce read-only `SELECT` statements (`write_mode="blocked"`).

---

## 3. Multi-Step Verification Workflow (Slide 16)

Run the bundled verification script before every commit:

```bash
./.agents/skills/civiclens-verification/scripts/verify.sh
```

### Step-by-Step Procedure
1. **Bytecode-Free Syntax Compilation**:
   ```bash
   PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile src/backend/*.py
   ```
2. **ADK 2.0 Swarm Catalog Smoke Test**:
   ```bash
   PYTHONDONTWRITEBYTECODE=1 python3 -c "import sys; sys.path.insert(0, 'src/backend'); from civic_swarm_adk import get_swarm_catalog; assert len(get_swarm_catalog()['agents']) == 4"
   ```
3. **Clean Working Tree Restoration**:
   ```bash
   git checkout -- "**/__pycache__/*" 2>/dev/null || true
   ```

---

## 4. Reviewer Assessment Checklist (Slide 15)

Before approving any change to `app-civiclens` or `civiclens`, verify:
- [ ] All 4 ADK Swarm agents (`SupervisorAgent`, `BudgetSQLAgent`, `DeliberationAuditorAgent`, `CrossCheckAuditAgent`) are registered in `SWARM_AGENTS_CATALOG`.
- [ ] Zero JSON service account keys exist in the repository (100% GKE Workload Identity / ADC).
- [ ] `git status -s` is completely empty (no stray `.pyc` files).
