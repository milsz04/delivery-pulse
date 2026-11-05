.DEFAULT_GOAL := help
COMPOSE := docker compose

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Build and start everything (Postgres, worker, AI service, Superset)
	$(COMPOSE) up -d --build

down: ## Stop everything (data is kept)
	$(COMPOSE) down

ps: ## Show container status
	$(COMPOSE) ps

logs: ## Follow logs of all services (Ctrl+C to stop)
	$(COMPOSE) logs -f --tail=100

open: ## Open the dashboard and the AI service in the browser (macOS)
	open http://localhost:8088/superset/dashboard/delivery-pulse/
	open http://localhost:8000

etl: ## Run the ETL now (incremental)
	$(COMPOSE) exec worker python -m pulse.etl

etl-full: ## Run a full ETL load (last DAYS_BACK days + all open items)
	$(COMPOSE) exec worker python -m pulse.etl --full

report: ## Generate the weekly AI report now and send it to configured channels
	$(COMPOSE) exec worker python -m pulse.report

report-dry: ## Show the report prompt and numbers without calling the LLM
	$(COMPOSE) exec worker python -m pulse.report --dry-run

ask: ## Ask a question from the terminal: make ask q="Who has the most open PRs?"
	$(COMPOSE) exec ai python -m pulse.ask "$(q)"

test: ## Run unit tests inside the app container
	$(COMPOSE) run --rm --no-deps ai pytest -v -m "not integration"

test-all: ## Unit + integration tests against a separate pulse_test database
	$(COMPOSE) exec db psql -U pulse -d pulse -q -c "DROP DATABASE IF EXISTS pulse_test" -c "CREATE DATABASE pulse_test"
	$(COMPOSE) exec db psql -U pulse -d pulse_test -q -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/01_init.sql
	$(COMPOSE) exec -e TEST_DATABASE_URL=postgresql://pulse:pulse@db:5432/pulse_test ai pytest -v

export-dashboards: ## Save dashboards edited in the Superset UI back to superset/dashboards
	$(COMPOSE) exec superset /app/export_dashboards.sh

psql: ## Open a SQL shell on the database
	$(COMPOSE) exec db psql -U pulse -d pulse

reset: ## Stop and DELETE all data (database + Superset metadata)
	$(COMPOSE) down -v

.PHONY: help up down ps logs open etl etl-full report report-dry ask test test-all export-dashboards psql reset
