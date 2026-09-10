.PHONY: help install web-dev web-build api-install api-dev canonical scenario features db-seed test check

help:
	@echo "CALIBER development commands"
	@echo "  make install      Install web dependencies"
	@echo "  make web-dev      Start the Vite UI"
	@echo "  make web-build    Build the UI"
	@echo "  make api-install  Create API virtualenv and install dependencies"
	@echo "  make api-dev      Start the FastAPI development server"
	@echo "  make canonical    Rebuild and validate KO-3201 canonical data"
	@echo "  make scenario     Build the six-month KO-3201 hourly scenario"
	@echo "  make features     Build the KO-3201 model-independent features"
	@echo "  make db-seed      Rebuild canonical data and seed SQLite"
	@echo "  make test         Run backend/data tests"
	@echo "  make check        Run currently available checks"

install:
	npm install

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

db-seed: canonical
	.venv/bin/python scripts/seed_database.py

test:
	.venv/bin/pytest

check:
	npm run check
	python3 -m compileall -q services/api/app scripts
	.venv/bin/pytest
