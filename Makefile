.PHONY: help verify run demo-catalog demo-swarm demo-bigquery sync-gtm

PORT     ?= 8000
BASE_URL ?= https://civiclens.hoffmannw.demo.altostrat.com

help: ## Affiche l'aide interactive des commandes de démo CivicLens & Google ADK 2.0
	@echo "================================================================================"
	@echo " 🏛️  CivicLens — Observatoire Comptes Publics M57 & Swarm ADK 2.0"
	@echo "================================================================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

verify: ## Exécute le Gatekeeper M1L1 (compilation Python sans bytecode + vérification des 4 agents ADK 2.0)
	@./.agents/skills/civiclens-verification/scripts/verify.sh

run: ## Démarre le backend FastAPI CivicLens localement sur http://localhost:8000
	@PYTHONDONTWRITEBYTECODE=1 uvicorn main:app --app-dir src/backend --host 0.0.0.0 --port $(PORT) --reload

demo-catalog: ## Interroge le catalogue des 4 sous-agents Google ADK 2.0 (/api/agents/catalog)
	@curl -s "$(BASE_URL)/api/agents/catalog" | jq .

demo-swarm: ## Lance un audit croisé M57 complet via le Swarm ADK 2.0 (Bordeaux Chapitre 65)
	@curl -s -X POST "$(BASE_URL)/api/agents/swarm-audit" \
		-H "Content-Type: application/json" \
		-d '{"question": "Audit de conformité M57 chapitre 65 (subventions aux associations) vs délibérations votées en conseil municipal en 2024", "city": "Bordeaux", "model": "gemini-3.5-flash"}' | jq .

demo-bigquery: ## Lance une requête Text-to-SQL BigQuery M57 en lecture seule (/api/analytics/bigquery)
	@curl -s -X POST "$(BASE_URL)/api/analytics/bigquery" \
		-H "Content-Type: application/json" \
		-d '{"query": "Top 5 des communes avec la meilleure épargne brute par habitant en 2024", "limit": 5}' | jq .
