.DEFAULT_GOAL := help
SHELL := /bin/sh

API_DIR := api
COMPOSE := docker compose

.PHONY: help env up down logs ps reset n8n-sync n8n-export api-install api-dev lint format typecheck test verify validate-workflows smoke

help: ## List available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

env: ## Create .env from .env.example with freshly generated local keys
	@if [ -f .env ]; then echo ".env already exists, leaving it untouched"; exit 0; fi; \
	sed -e "s/^CLINIC_API_KEY=$$/CLINIC_API_KEY=$$(openssl rand -hex 24)/" \
	    -e "s/^N8N_ENCRYPTION_KEY=$$/N8N_ENCRYPTION_KEY=$$(openssl rand -hex 32)/" \
	    .env.example > .env && echo ".env created; fill OPENAI_API_KEY and GOOGLE_OAUTH_* before testing"

up: ## Build and start api, n8n (with bootstrap) and the web chat
	$(COMPOSE) up -d --build
	@echo "Web chat: http://localhost:8080 | n8n: http://localhost:5678 | API docs: http://localhost:8000/docs"

down: ## Stop the stack (keeps volumes)
	$(COMPOSE) down

logs: ## Follow logs of every service
	$(COMPOSE) logs -f

ps: ## Show service status and health
	$(COMPOSE) ps

reset: ## Stop the stack and DELETE database and n8n volumes
	$(COMPOSE) down -v

n8n-sync: ## Re-import and re-publish the repository workflows (n8n is stopped meanwhile)
	$(COMPOSE) stop n8n
	FORCE_WORKFLOW_SYNC=1 $(COMPOSE) run --rm n8n-import
	$(COMPOSE) start n8n

n8n-export: ## Export the workflows from n8n back into n8n/workflows
	@for pair in clinicChatMain01:clinic-chat-main clinicBookAppt01:clinic-book-appointment \
	             clinicCancelAp01:clinic-cancel-appointment; do \
		id=$${pair%%:*}; name=$${pair##*:}; \
		$(COMPOSE) exec -T n8n n8n export:workflow --id=$$id --pretty --output=/tmp/$$name.json && \
		$(COMPOSE) cp n8n:/tmp/$$name.json n8n/workflows/$$name.json; \
	done

api-install: ## Install API dependencies locally with uv
	cd $(API_DIR) && uv sync

api-dev: ## Run the API locally with reload (reads ../.env)
	cd $(API_DIR) && CLINIC_DATABASE_URL=sqlite:///./data/clinic.db uv run --env-file ../.env \
		sh -c 'alembic upgrade head && python -m clinic_api.seed && uvicorn clinic_api.main:app --reload'

lint: ## Lint and check formatting
	cd $(API_DIR) && uv run ruff check . && uv run ruff format --check .

format: ## Format the API code
	cd $(API_DIR) && uv run ruff format . && uv run ruff check --fix .

typecheck: ## Static type-check (mypy strict)
	cd $(API_DIR) && uv run mypy

test: ## Run API tests with coverage
	cd $(API_DIR) && uv run pytest --cov

validate-workflows: ## Static consistency checks for the n8n workflow exports
	uv run --no-project python scripts/validate_workflows.py

verify: lint typecheck test validate-workflows ## Full local gate (same as CI)

smoke: ## End-to-end smoke test against the running stack
	./scripts/smoke_test.sh
