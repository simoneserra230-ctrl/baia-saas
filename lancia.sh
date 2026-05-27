#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
GRN='\033[0;32m'; YLW='\033[1;33m'; RED='\033[0;31m'; BLU='\033[0;34m'; NC='\033[0m'

clear
echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║         BA.IA  v3.0                          ║"
echo "  ║   Piattaforma AI Finanza Agevolata           ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

PYTHON=""
for cmd in python3 python3.12 python3.11 python3.10 python; do
  if command -v "$cmd" &>/dev/null; then
    VER=$($cmd --version 2>&1 | grep -o '[0-9]\+\.[0-9]\+' | head -1)
    MAJOR=$(echo "$VER" | cut -d. -f1)
    MINOR=$(echo "$VER" | cut -d. -f2)
    if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ] 2>/dev/null; then
      PYTHON="$cmd"; break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo -e "${RED}  [ERRORE] Python 3.10+ non trovato.${NC}"
  echo "  Installa Python da https://python.org"
  if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "  Su Mac: brew install python@3.11"
    read -p "  Aprire python.org? [s/N] " -n1 -r; echo
    [[ $REPLY =~ ^[Ss]$ ]] && open "https://python.org"
  fi
  exit 1
fi
echo -e "  ${GRN}[OK]${NC} $($PYTHON --version)"

if [ ! -f ".venv/bin/uvicorn" ]; then
  echo ""
  echo -e "  ${YLW}Prima installazione (solo questa volta, 2-3 minuti)...${NC}"
  echo ""
  $PYTHON -m venv .venv
  echo -e "  ${GRN}[1/3]${NC} Ambiente Python creato"
  .venv/bin/pip install --quiet --upgrade pip
  echo -e "  ${GRN}[2/3]${NC} Pip aggiornato"
  .venv/bin/pip install --quiet -r backend/requirements.txt
  echo -e "  ${GRN}[3/3]${NC} Dipendenze installate"
  echo ""
  echo -e "  ${GRN}Installazione completata!${NC}"
fi

if [ ! -f ".env" ]; then
  cat > .env << 'ENVEOF'
GROQ_API_KEY=gsk_INSERISCI_LA_TUA_CHIAVE_QUI
LICENSE_KEY=TEST-MODE
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
APP_NAME=BA.IA
DB_PATH=./data/ai-bandi.db
PORT=8000
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
SMTP_FROM=noreply@baia.it
ENVEOF
fi

mkdir -p data

PORT=$(grep "^PORT=" .env 2>/dev/null | cut -d= -f2 | tr -d ' ')
PORT=${PORT:-8000}

if command -v lsof &>/dev/null && lsof -ti:$PORT &>/dev/null; then
  lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
  sleep 0.5
fi

(sleep 3 && (
  if [[ "$OSTYPE" == "darwin"* ]]; then
    open "$DIR/frontend/index.html"
  else
    xdg-open "$DIR/frontend/index.html" 2>/dev/null || \
    xdg-open "http://localhost:$PORT" 2>/dev/null || true
  fi
)) &

clear
echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║         BA.IA  v3.0                          ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""
echo -e "  ${GRN}Avvio in corso...${NC}"
echo ""
echo "  L'app si aprirà automaticamente nel browser."
echo "  URL: http://localhost:$PORT"
echo ""
echo "  Per chiudere: premi Ctrl+C"
echo "  ─────────────────────────────────────────────"
echo ""

PYTHONPATH="$DIR" .venv/bin/uvicorn backend.app_locale:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --log-level warning \
  --no-access-log
