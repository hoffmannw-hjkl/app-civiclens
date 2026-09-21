# Multi-stage build pour l'API & Frontend CivicLens
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Création d'un utilisateur et groupe non-privilégiés (SRE & CIS Benchmark)
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -d /app -s /sbin/nologin appuser

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ /app/backend/
COPY ingestion/ /app/ingestion/

RUN chown -R appuser:appgroup /app

USER 10001:10001

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend:/app

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

