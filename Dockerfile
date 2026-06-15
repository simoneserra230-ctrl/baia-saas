FROM python:3.11-slim

WORKDIR /app

# Dipendenze di sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements e installa
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copia codice applicazione
COPY backend /app/backend
COPY frontend /app/frontend

# Crea cartella dati persistente
RUN mkdir -p /app/data && chmod 755 /app/data

# Variabili di ambiente con default sicuri
ENV PORT=8000 \
    DB_PATH=/app/data/ai-bandi.db \
    APP_NAME="BA.IA" \
    LICENSE_KEY=TEST-MODE \
    PYTHONPATH=/app:/app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/ || exit 1

# Forma shell (non exec) per espandere la $PORT iniettata da Render; fallback 8000 in locale
CMD python -m uvicorn backend.app_locale:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
