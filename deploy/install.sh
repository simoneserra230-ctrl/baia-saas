#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════
# BA.IA — Installer automatico per VPS Ubuntu/Debian
# ══════════════════════════════════════════════════════════
# Su un VPS appena creato (Hetzner, DigitalOcean, Aruba, ecc.):
#
#   curl -fsSL https://baia.app/install.sh | sudo bash
#
# OPPURE manualmente:
#
#   wget https://baia.app/install.sh
#   chmod +x install.sh
#   sudo ./install.sh
#
# Il script:
#   1. Installa Docker e Docker Compose
#   2. Scarica il pacchetto BA.IA
#   3. Chiede dominio e chiave API
#   4. Avvia tutto con HTTPS automatico
# ══════════════════════════════════════════════════════════

set -e
GRN='\033[0;32m'; YLW='\033[1;33m'; RED='\033[0;31m'; BLU='\033[0;34m'; NC='\033[0m'

if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Esegui come root: sudo $0${NC}"
   exit 1
fi

clear
cat << "BANNER"

  ╔═══════════════════════════════════════════════════╗
  ║                                                   ║
  ║              BA.IA  —  Installer                  ║
  ║      Piattaforma AI per Finanza Agevolata         ║
  ║                                                   ║
  ╚═══════════════════════════════════════════════════╝

BANNER
echo ""
echo -e "${YLW}Questo script installerà BA.IA in modalità produzione${NC}"
echo -e "${YLW}con HTTPS automatico via Let's Encrypt.${NC}"
echo ""

# ── Input utente ─────────────────────────────────────────
read -p "  Dominio (es. baia.miostudio.it): " DOMAIN
[ -z "$DOMAIN" ] && { echo -e "${RED}Dominio obbligatorio${NC}"; exit 1; }

read -p "  Chiave API Groq (gsk_...): " GROQ_KEY
[ -z "$GROQ_KEY" ] && { echo -e "${RED}Chiave API obbligatoria${NC}"; exit 1; }

echo ""
echo -e "${BLU}[1/5]${NC} Aggiornamento sistema..."
apt-get update -qq
apt-get install -y -qq curl wget git unzip ufw

echo -e "${BLU}[2/5]${NC} Installazione Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh > /dev/null 2>&1
    systemctl enable docker
    systemctl start docker
fi

echo -e "${BLU}[3/5]${NC} Configurazione firewall..."
ufw --force enable > /dev/null 2>&1
ufw allow 22/tcp > /dev/null 2>&1
ufw allow 80/tcp > /dev/null 2>&1
ufw allow 443/tcp > /dev/null 2>&1

echo -e "${BLU}[4/5]${NC} Download BA.IA..."
INSTALL_DIR="/opt/baia"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Se il pacchetto è già qui (uploaded manualmente), usa quello
if [ -f "/tmp/baia.zip" ]; then
    unzip -o /tmp/baia.zip -d "$INSTALL_DIR" > /dev/null
    if [ -d "$INSTALL_DIR/AI-Bandi-LOCALE" ]; then
        mv "$INSTALL_DIR/AI-Bandi-LOCALE"/* "$INSTALL_DIR/"
        rmdir "$INSTALL_DIR/AI-Bandi-LOCALE"
    fi
fi

# Crea .env produzione
cat > "$INSTALL_DIR/deploy/.env" << EOF
DOMAIN=$DOMAIN
GROQ_API_KEY=$GROQ_KEY
APP_NAME=BA.IA
LICENSE_KEY=TEST-MODE
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
AI_PROVIDER=groq
AI_API_KEY=$GROQ_KEY
EOF

echo -e "${BLU}[5/5]${NC} Avvio container BA.IA..."
cd "$INSTALL_DIR/deploy"
docker compose -f docker-compose.prod.yml up -d --build 2>&1 | tail -3

# Setup auto-restart
cat > /etc/systemd/system/baia.service << EOF
[Unit]
Description=BA.IA Stack
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$INSTALL_DIR/deploy
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml down

[Install]
WantedBy=multi-user.target
EOF
systemctl enable baia.service > /dev/null 2>&1

echo ""
echo -e "${GRN}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${GRN}║   ✓ Installazione completata                      ║${NC}"
echo -e "${GRN}╚═══════════════════════════════════════════════════╝${NC}"
echo ""
echo "  🌐 URL:        https://$DOMAIN"
echo "  📁 Install:    $INSTALL_DIR"
echo "  ⚙  Configura:  $INSTALL_DIR/deploy/.env"
echo ""
echo -e "${YLW}  Caddy sta ottenendo il certificato HTTPS...${NC}"
echo "  Attendi 30-60 secondi, poi apri: https://$DOMAIN"
echo ""
echo "  Comandi utili:"
echo "    docker logs baia-app       # Log applicazione"
echo "    docker logs baia-caddy     # Log proxy/HTTPS"
echo "    systemctl restart baia     # Riavvia tutto"
echo ""
