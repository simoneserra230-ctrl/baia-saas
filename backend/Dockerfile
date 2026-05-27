FROM python:3.11-slim

WORKDIR /app

# Dipendenze sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Codice applicazione
COPY main.py .

# Porta esposta
EXPOSE 8000

# Avvio
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
