# The API service. Deliberately a slim Python image rather than extending
# the Airflow image: this process serves HTTP and needs none of Airflow's
# dependencies, and keeping them apart stops a web-layer change from
# forcing an Airflow image rebuild.
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi==0.136.3 \
    "uvicorn[standard]==0.52.1" \
    "psycopg[binary]==3.3.4" \
    psycopg-pool==3.3.2

COPY api/ /app/api/

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
