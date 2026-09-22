---
name: civiclens-verification
description: >-
  Quality assurance, Python linting, and Kubernetes manifest validation runbook for CivicLens.
  Use this skill before committing changes to app-civiclens or civiclens.
---

# CivicLens Quality & Deployment Verification Runbook

Follow this verification checklist whenever updating backend FastAPI services, ADK agents, or Kubernetes manifests in `app-civiclens`.

## Step 1: Python Syntax & Static Compilation Check

Verify that all Python modules compile cleanly without syntax errors:

```bash
python3 -m py_compile $(find . -name "*.py" -not -path "./.venv/*")
```

## Step 2: Unit & Integration Tests

Run the test suite with `pytest` (if present):

```bash
pytest -q || true
```

## Step 3: GKE Blueprint Alignment Check

Verify that Kubernetes manifests (`k8s/` or `deploy/`) reference the plug-and-play outputs from `gcp-ai-foundation-blueprint`:
- Workload Identity GSA: `$(terraform output -raw gke_app_service_account_email)`
- Cloud Armor WAF Policy: `$(terraform output -raw waf_policy_name)`
- Global External IP Name: `$(terraform output -raw external_ip_name)`
