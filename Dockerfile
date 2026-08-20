# Extends the official Airflow image with this project's business-logic
# dependencies (geopandas/shapely/pyproj/requests/psycopg). The stock image
# only has Airflow core + providers -- DAG/task code that imports
# src.ingestion.* needs these too. Per Airflow's own docs, extending the
# image like this (rather than `_PIP_ADDITIONAL_REQUIREMENTS`, which
# reinstalls on every container start and is documented as "ONLY for quick
# checks") is the supported approach for anything beyond a one-off try-out.
FROM apache/airflow:3.3.1

# Matches the Python version actually shipped in this Airflow image
# (verified via `docker compose exec airflow-apiserver python --version`)
# -- NOT the 3.12 used for the local host venv in Makefile/pyproject.toml.
# Airflow's constraints files are per-Python-version, so this must track
# whatever the base image ships, independently of the host tooling version.
ARG AIRFLOW_VERSION=3.3.1
ARG CONTAINER_PYTHON_VERSION=3.13

USER airflow

RUN pip install --no-cache-dir \
    geopandas==1.1.4 \
    shapely==2.1.2 \
    pyproj==3.7.2 \
    requests==2.34.2 \
    "psycopg[binary]==3.3.4" \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${CONTAINER_PYTHON_VERSION}.txt"
