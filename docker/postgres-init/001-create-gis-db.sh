#!/bin/bash
# Runs once, on first container start, via Postgres's own
# /docker-entrypoint-initdb.d convention. Creates a second database
# (separate from Airflow's own metadata database) for application data,
# with PostGIS enabled -- this is where the `snapshots` table lives.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER "${GIS_DB_USER}" WITH PASSWORD '${GIS_DB_PASSWORD}';
    CREATE DATABASE "${GIS_DB_NAME}" OWNER "${GIS_DB_USER}";
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "${GIS_DB_NAME}" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS postgis;
EOSQL
