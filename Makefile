# Makefile — developer shortcuts for detecktiv.io
# Usage:
#   make help
#   make install
#   make dev
#   make test
#   make migrate
#   make revision msg="add new table"
#   make seed_admin email=admin@example.com password='Str0ngP@ss!'
#   make docker-up

SHELL := /bin/bash

# --- Defaults (can be overridden: make dev PORT=9000) ---
PORT ?= 8000
ENV_FILE ?= .env
MODULE ?= app.main:app

# --- Helper: run a command if present, else no-op ---
define run_if_available
	@if command -v $(1) >/dev/null 2>&1; then \
		echo "→ Running $(1) $(2)"; \
		$(1) $(2); \
	else \
		echo "↷ Skipping: $(1) not installed"; \
	fi
endef

.PHONY: help
help:
	@echo ""
	@echo "detecktiv.io — Make targets"
	@echo "────────────────────────────"
	@echo " install           Install Python dependencies"
	@echo " dev               Run dev server (uvicorn --reload)        [PORT=$(PORT)]"
	@echo " run               Run prod server (gunicorn+uvicorn worker) [PORT=$(PORT)]"
	@echo " migrate           Run alembic upgrade head"
	@echo " revision          Create alembic revision (msg=\"...\")"
	@echo " downgrade         Roll back one migration"
	@echo " seed_admin        Create/ensure an admin (email=, password=, name=)"
	@echo " test              Run pytest"
	@echo " lint              Run ruff/flake8 if available"
	@echo " fmt               Run ruff format / black if available"
	@echo " docker-up         Start Postgres + API (docker-compose)"
	@echo " docker-down       Stop stack (docker-compose)"
	@echo " docker-rebuild    Rebuild API image"
	@echo " health            Ping /health and /health/db"
	@echo " env               Print key env values"
	@echo ""

.PHONY: install
install:
	python -m pip install --upgrade pip setuptools wheel
	pip install -r requirements.txt

.PHONY: dev
dev:
	ENV_FILE=$(ENV_FILE) uvicorn $(MODULE) --reload --port $(PORT) --host 0.0.0.0

.PHONY: run
run:
	gunicorn $(MODULE) --bind 0.0.0.0:$(PORT) --workers $${WEB_CONCURRENCY:-2} --worker-class uvicorn.workers.UvicornWorker --timeout $${WEB_TIMEOUT:-60}

.PHONY: migrate
migrate:
	alembic upgrade head

.PHONY: revision
revision:
ifndef msg
	$(error Please provide a migration message: make revision msg="your message")
endif
	alembic revision -m "$(msg)"

.PHONY: downgrade
downgrade:
	alembic downgrade -1

# Admin bootstrap — override with: make seed_admin email=you@example.com password='P@ss!'
email ?= admin@example.com
password ?= Str0ngP@ss!
name ?= Site Admin
.PHONY: seed_admin
seed_admin:
	ADMIN_EMAIL="$(email)" ADMIN_PASSWORD="$(password)" ADMIN_NAME="$(name)" python -m scripts.admin_bootstrap -v

.PHONY: test
test:
	pytest -q

.PHONY: lint
lint:
	$(call run_if_available,ruff,"check .")
	$(call run_if_available,flake8,".")

.PHONY: fmt
fmt:
	$(call run_if_available,ruff,"format .")
	$(call run_if_available,black,".")

# Docker helpers --------------------------------------------------------------

.PHONY: docker-up
docker-up:
	docker compose up -d --build

.PHONY: docker-down
docker-down:
	docker compose down

.PHONY: docker-rebuild
docker-rebuild:
	docker compose build --no-cache api

# Quick ops -------------------------------------------------------------------

.PHONY: health
health:
	@set -e; \
	URL="http://localhost:$(PORT)"; \
	echo "GET $$URL/health"; curl -fsS "$$URL/health" || true; echo; \
	echo "GET $$URL/health/db"; curl -fsS "$$URL/health/db" || true; echo;

.PHONY: env
env:
	@echo "DATABASE_URL     = $${DATABASE_URL:-($(ENV_FILE) or environment)}"
	@echo "POSTGRES_SCHEMA  = $${POSTGRES_SCHEMA:-app}"
	@echo "SECRET_KEY       = $${SECRET_KEY:-(not shown)}"
	@echo "CORS_ORIGINS     = $${CORS_ORIGINS:-*}"
	@echo "ACCESS_TOKEN_TTL = $${ACCESS_TOKEN_EXPIRES_SECONDS:-900}s"
	@echo "REFRESH_TOKEN_TTL= $${REFRESH_TOKEN_EXPIRES_SECONDS:-1209600}s"
