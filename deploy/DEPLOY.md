# BA.IA — Guida Deploy Online

Tre strade per metterlo online, in ordine di semplicità.

---

## Opzione 1 — Railway (più semplice, gratis fino a 5$/mese)

**Tempo: 5 minuti · Costo: $0-5/mese**

1. Vai su [railway.com](https://railway.com) e registrati con GitHub
2. Crea un nuovo repository GitHub e carica i file BA.IA
3. Su Railway: **New Project** → **Deploy from GitHub repo** → seleziona il tuo
4. Aggiungi le variabili d'ambiente:
   - `GROQ_API_KEY` = la tua chiave Groq
   - `APP_NAME` = `BA.IA` (o nome studio)
   - `LICENSE_KEY` = `TEST-MODE`
5. Railway rileva automaticamente il Dockerfile e fa il deploy
6. Su **Settings** → **Generate Domain** ottieni un URL tipo `baia-production.up.railway.app`
7. Per un dominio custom: **Settings** → **Custom Domain** → aggiungi `baia.tuodominio.it`

**Persistenza dati**: aggiungi un Volume sul path `/app/data`.

---

## Opzione 2 — Render.com (gratis con limitazioni)

**Tempo: 7 minuti · Costo: $0-7/mese**

1. [render.com](https://render.com) → registrati
2. **New** → **Blueprint** → collega il tuo repo GitHub
3. Render trova il `deploy/render.yaml` e configura tutto
4. Inserisci `GROQ_API_KEY` quando richiesto
5. **Apply** → attendi il build (3-5 min)
6. Render dà un URL `*.onrender.com`, oppure aggiungi dominio custom da Settings

**Nota**: il piano free va in sleep dopo 15 min di inattività. Per uso professionale serve il piano Starter ($7/mese).

---

## Opzione 3 — VPS proprio (più controllo, più potente)

**Tempo: 10 minuti · Costo: 4-6€/mese · Consigliato**

### Provider consigliati

| Provider | Piano | Prezzo | Note |
|----------|-------|--------|------|
| **Hetzner** | CX22 | €3.95/mese | 2 vCPU, 4GB RAM — qualità top |
| **Aruba** | Cloud Smart Small | €4/mese | Italiano, datacenter in IT |
| **DigitalOcean** | Basic | $6/mese | Esperienza utente migliore |
| **Contabo** | VPS S | €4.50/mese | RAM/storage abbondante |

### Passi

**1. Crea il VPS**
   - Sistema operativo: **Ubuntu 22.04 LTS**
   - Annota l'IP pubblico

**2. Compra/configura il dominio**
   - Vai dal tuo registrar (Aruba, Register.it, Namecheap, ecc.)
   - Crea un record **A** che punta `baia.tuodominio.it` → IP del VPS

**3. Collegati al VPS**
   ```bash
   ssh root@IP-DEL-VPS
   ```

**4. Carica il pacchetto**
   ```bash
   # Carica BA.IA-v3.0.zip su /tmp/baia.zip via SCP da locale:
   #   scp BA.IA-v3.0.zip root@IP-DEL-VPS:/tmp/baia.zip
   ```

**5. Esegui l'installer**
   ```bash
   cd /tmp && unzip baia.zip && cd AI-Bandi-LOCALE
   chmod +x deploy/install.sh
   sudo ./deploy/install.sh
   ```

   L'installer chiederà:
   - Dominio (es. `baia.tuodominio.it`)
   - Chiave Groq

**6. Attendi 30-60 secondi** — Caddy ottiene il certificato HTTPS Let's Encrypt automaticamente.

**7. Apri `https://baia.tuodominio.it`** — pronto!

### Manutenzione VPS

```bash
# Log applicazione
docker logs baia-app -f

# Log HTTPS/proxy
docker logs baia-caddy -f

# Riavvia tutto
systemctl restart baia

# Aggiornamento
cd /opt/baia/deploy
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --build

# Backup database
docker exec baia-app sqlite3 /app/data/ai-bandi.db ".backup '/app/data/backup-$(date +%F).db'"
```

---

## Sicurezza in produzione

### Cose da fare subito

1. **Cambia `LICENSE_KEY=TEST-MODE`** con una chiave reale prima del go-live commerciale
2. **Backup automatici**: aggiungi a crontab del VPS:
   ```bash
   0 3 * * * docker exec baia-app sqlite3 /app/data/ai-bandi.db ".backup '/app/data/backup-$(date +\%F).db'"
   ```
3. **Configura SMTP** nel `.env` per le notifiche email
4. **Aggiorna regolarmente** il sistema:
   ```bash
   apt update && apt upgrade -y
   ```

### Cosa NON fare

- ❌ Non esporre la porta 8000 direttamente — solo 80/443 via Caddy
- ❌ Non usare HTTP in produzione — Caddy gestisce HTTPS automatico, usalo
- ❌ Non condividere la `GROQ_API_KEY` — è personale e fatturabile

---

## Costi totali stimati

| Setup | Mensile | Annuale |
|-------|---------|---------|
| Railway hobby | $5 | $60 |
| Render Starter | $7 | $84 |
| Hetzner CX22 + dominio | €4 + €10 | €58 |
| Aruba VPS + dominio .it | €4 + €15 | €63 |

**Più chiave Groq**: gratis fino a ~14400 richieste/giorno (sufficiente per uno studio piccolo-medio).

---

## Multi-tenant: un'installazione per cliente

Se vendi BA.IA a più studi consulenza, ognuno con il proprio dominio:

1. Su un singolo VPS (anche piccolo) puoi ospitarne 10-20
2. Per ogni cliente: clona la cartella `/opt/baia` in `/opt/baia-studio-X/`
3. Cambia `DOMAIN` e porte nel `.env` di ciascuno
4. Caddy gestisce tutti i certificati HTTPS automaticamente

Oppure, struttura migliore: **single deploy multi-tenant** con database condiviso e schema separato per studio. Richiede modifiche al codice (filtra per `studio_id` su ogni query). Disponibile su richiesta.

---

*Per supporto tecnico: vedi README.md principale.*
