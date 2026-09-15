.PHONY: help install dev web-dev web-build api-install api-dev canonical scenario \
	features train-preflight train alerts retrieval rca-preflight rca actions \
	db-seed test lint security-check check

help:
	@echo "CALIBER development commands"
	@echo "  make install      Install web dependencies"
	@echo "  make dev          Start the API and web app together"
	@echo "  make web-dev      Start the Vite UI"
	@echo "  make web-build    Build the UI"
	@echo "  make api-install  Create API virtualenv and install dependencies"
	@echo "  make api-dev      Start the FastAPI development server"
	@echo "  make canonical    Rebuild and validate KO-3201 canonical data"
	@echo "  make scenario     Build the six-month KO-3201 hourly scenario"
	@echo "  make features     Build the KO-3201 model-independent features"
	@echo "  make train-preflight  Validate model inputs without training"
	@echo "  make train        Train and evaluate the KO-3201 anomaly model"
	@echo "  make alerts       Build prioritized alerts from existing model scores"
	@echo "  make retrieval    Retrieve historical analogues for the KO-3201 alert"
	@echo "  make rca-preflight  Validate RCA inputs and request without an API call"
	@echo "  make rca          Generate a grounded RCA draft with OpenAI"
	@echo "  make actions      Build a CA/PA proposal from the RCA draft"
	@echo "  make db-seed      Rebuild canonical data and seed SQLite"
	@echo "  make test         Run backend/data tests"
	@echo "  make lint         Run Python static analysis"
	@echo "  make security-check  Scan Python source for security issues"
	@echo "  make check        Run all local quality gates"

install:
	npm install

dev:
	bash scripts/start-dev.sh

web-dev:
	npm run dev

web-build:
	npm run build

api-install:
	python3 -m venv .venv
	.venv/bin/pip install -r services/api/requirements.lock

api-dev:
	.venv/bin/uvicorn services.api.app.main:app --reload --host 127.0.0.1 --port 8000

canonical:
	.venv/bin/python scripts/ingest_ko_3201.py

scenario: canonical
	.venv/bin/python scripts/generate_ko_3201_scenario.py

features: scenario
	.venv/bin/python scripts/build_ko_3201_features.py

train-preflight: features
	.venv/bin/python scripts/train_ko_3201_anomaly.py --preflight

train: features
	.venv/bin/python scripts/train_ko_3201_anomaly.py

alerts:
	.venv/bin/python scripts/build_ko_3201_alerts.py

retrieval:
	.venv/bin/python scripts/build_ko_3201_retrieval.py

rca-preflight:
	.venv/bin/python scripts/generate_ko_3201_rca.py --preflight

rca:
	.venv/bin/python scripts/generate_ko_3201_rca.py

actions:
	.venv/bin/python scripts/build_ko_3201_actions.py

db-seed: canonical
	.venv/bin/python scripts/seed_database.py

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check services/api/app services/api/tests scripts

security-check:
	.venv/bin/bandit -q -r services/api/app scripts -x services/api/tests --severity-level medium --confidence-level medium

check: lint security-check
	npm run check
	python3 -m compileall -q services/api/app scripts
	.venv/bin/pytest
