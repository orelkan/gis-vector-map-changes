.PHONY: install up down logs migrate test test-integration test-db lint fmt dag-list \
        api-logs web web-install test-web

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
AIRFLOW_VERSION := 3.3.1
PYTHON_VERSION := 3.12

-include .env
export

# Keeps pytest's `from airflow.models import DagBag` (used for DAG
# import/structure tests) from defaulting to -- and polluting -- ~/airflow.
export AIRFLOW_HOME := $(CURDIR)/.airflow_home

# Both installs use the same Airflow constraints file. Without it on the
# second call too, `pip install -e ".[dev]"` would re-resolve
# apache-airflow's (and its providers') transitive deps with no pin,
# undoing the reproducible install from the first line.
install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install "apache-airflow[amazon,postgres]==$(AIRFLOW_VERSION)" \
		--constraint "https://raw.githubusercontent.com/apache/airflow/constraints-$(AIRFLOW_VERSION)/constraints-$(PYTHON_VERSION).txt"
	$(PIP) install -e ".[dev]" \
		--constraint "https://raw.githubusercontent.com/apache/airflow/constraints-$(AIRFLOW_VERSION)/constraints-$(PYTHON_VERSION).txt"

up:
	docker compose up -d
	@echo "Airflow UI:    http://localhost:8080"
	@echo "MinIO console: http://localhost:9001"

down:
	docker compose down

logs:
	docker compose logs -f

# Applies sql/*.sql (in filename order) to the `gis` application database.
# Idempotent: migration files use IF NOT EXISTS, so re-running is a no-op.
migrate:
	@for f in sql/*.sql; do \
		echo "Applying $$f"; \
		docker compose exec -T postgres psql -U "$(GIS_DB_USER)" -d "$(GIS_DB_NAME)" < $$f; \
	done

test:
	$(PYTHON) -m pytest

test-integration:
	$(PYTHON) -m pytest -m integration

# Requires `make up` to be running (real local Postgres on localhost:5432).
test-db:
	$(PYTHON) -m pytest -m db

lint:
	$(VENV)/bin/ruff check .

fmt:
	$(VENV)/bin/ruff format .

dag-list:
	docker compose exec airflow-apiserver airflow dags list-import-errors

api-logs:
	docker compose logs -f api

# The web UI runs on the host via Vite (fast HMR); the API it talks to runs
# in the stack. `make up` must be running first.
web-install:
	cd web && npm install

web:
	cd web && npm run dev

test-web:
	cd web && npm run test -- --run
