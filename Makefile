.DEFAULT_GOAL := help
SHELL := /bin/sh

API_DIR := api
COMPOSE := docker compose

.PHONY: help env up down logs ps reset n8n-sync n8n-export api-install api-dev lint format typecheck test verify validate-workflows email-templates email-preview smoke

help: ## Lista os comandos disponíveis
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

env: ## Cria o .env a partir do .env.example com chaves locais geradas na hora
	@if [ -f .env ]; then echo ".env já existe, mantido como está"; exit 0; fi; \
	sed -e "s/^CLINIC_API_KEY=$$/CLINIC_API_KEY=$$(openssl rand -hex 24)/" \
	    -e "s/^N8N_ENCRYPTION_KEY=$$/N8N_ENCRYPTION_KEY=$$(openssl rand -hex 32)/" \
	    .env.example > .env && echo ".env criado; preencha OPENAI_API_KEY e GOOGLE_OAUTH_* antes de testar"

up: ## Constrói e sobe api, n8n (com bootstrap) e o web chat
	$(COMPOSE) up -d --build
	@echo "Web chat: http://localhost:8080 | n8n: http://localhost:5678 | API docs: http://localhost:8000/docs"

down: ## Para a stack (mantém os volumes)
	$(COMPOSE) down

logs: ## Acompanha os logs de todos os serviços
	$(COMPOSE) logs -f

ps: ## Mostra o status e a saúde dos serviços
	$(COMPOSE) ps

reset: ## Para a stack e APAGA os volumes do banco e do n8n
	$(COMPOSE) down -v

n8n-sync: ## Reimporta e publica os workflows do repositório (o n8n fica parado durante o processo)
	$(COMPOSE) stop n8n
	FORCE_WORKFLOW_SYNC=1 $(COMPOSE) run --rm n8n-import
	$(COMPOSE) start n8n

n8n-export: ## Exporta os workflows editados no n8n de volta para n8n/workflows
	@for pair in clinicChatMain01:clinic-chat-main clinicBookAppt01:clinic-book-appointment \
	             clinicCancelAp01:clinic-cancel-appointment; do \
		id=$${pair%%:*}; name=$${pair##*:}; \
		$(COMPOSE) exec -T n8n n8n export:workflow --id=$$id --pretty --output=/tmp/$$name.json && \
		$(COMPOSE) cp n8n:/tmp/$$name.json n8n/workflows/$$name.json; \
	done

api-install: ## Instala as dependências da API localmente com uv
	cd $(API_DIR) && uv sync

api-dev: ## Roda a API localmente com reload (lê o ../.env)
	cd $(API_DIR) && CLINIC_DATABASE_URL=sqlite:///./data/clinic.db uv run --env-file ../.env \
		sh -c 'alembic upgrade head && python -m clinic_api.seed && uvicorn clinic_api.main:app --reload'

lint: ## Lint e checagem de formatação
	cd $(API_DIR) && uv run ruff check . && uv run ruff format --check .

format: ## Formata o código da API
	cd $(API_DIR) && uv run ruff format . && uv run ruff check --fix .

typecheck: ## Checagem estática de tipos (mypy strict)
	cd $(API_DIR) && uv run mypy

test: ## Roda os testes da API com cobertura
	cd $(API_DIR) && uv run pytest --cov

validate-workflows: ## Checagens estáticas dos exports do n8n e dos templates de e-mail
	uv run --no-project python scripts/validate_workflows.py
	uv run --no-project python scripts/build_email_templates.py --check

email-templates: ## Injeta n8n/email-templates nos nodes do Gmail dos workflows
	uv run --no-project python scripts/build_email_templates.py

email-preview: ## Gera o preview dos e-mails com dados de exemplo em tmp/email-preview
	uv run --no-project python scripts/build_email_templates.py --preview
	@echo "Abra tmp/email-preview/appointment-booked.html e appointment-cancelled.html no navegador"

verify: lint typecheck test validate-workflows ## Gate local completo (o mesmo do CI)

smoke: ## Smoke test ponta a ponta contra a stack no ar
	./scripts/smoke_test.sh
