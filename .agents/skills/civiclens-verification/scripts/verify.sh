#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$REPO_ROOT"

BACKEND_DIR="src/backend"
if [ ! -d "$BACKEND_DIR" ] && [ -d "app/backend" ]; then
  BACKEND_DIR="app/backend"
fi

echo "🔍 [1/2] Bytecode-free Python compilation check ($BACKEND_DIR)..."
PYTHONDONTWRITEBYTECODE=1 python3 -B -m py_compile "$BACKEND_DIR"/*.py
echo "✅ Python syntax check passed."

echo "🔍 [2/2] Verifying ADK 2.0 Swarm Catalog (4 specialized agents)..."
PYTHONDONTWRITEBYTECODE=1 python3 -B -c "
import sys
sys.path.insert(0, '$BACKEND_DIR')
from civic_swarm_adk import get_swarm_catalog
cat = get_swarm_catalog()
assert len(cat['agents']) == 4, f'Expected 4 agents, got {len(cat[\"agents\"])}'
print('✅ ADK Swarm Catalog verified:', [a['name'] for a in cat['agents']])
"

git checkout -- "**/__pycache__/*" 2>/dev/null || true
rm -f "$BACKEND_DIR"/__pycache__/civic_swarm_adk.*.pyc 2>/dev/null || true
