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
    GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct \
    PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["python", "-m", "uvicorn", "backend.app_locale:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
