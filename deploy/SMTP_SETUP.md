# 📧 Email di reset password — configurazione SMTP

**Stato del codice:** ✅ già pronto e funzionante.
L'endpoint `/auth/forgot-password` genera un token valido 1 ora, lo salva su DB e prova a
inviare l'email con `_send_email()`. Se le variabili SMTP **non** sono impostate, l'invio
fallisce *in silenzio* (per sicurezza anti-enumeration l'utente vede comunque "email inviata").

👉 Quindi "non manda email" = **mancano le variabili SMTP su Render**, non è un bug.

---

## Variabili da aggiungere su Render

Render → servizio **baia-backend** → **Environment** → *Add Environment Variable*:

| Key          | Value (esempio Gmail)            | Note |
|--------------|----------------------------------|------|
| `SMTP_HOST`  | `smtp.gmail.com`                 | server SMTP |
| `SMTP_PORT`  | `587`                            | STARTTLS |
| `SMTP_USER`  | `simoneserra230@gmail.com`       | la tua casella |
| `SMTP_PASS`  | *(App Password 16 cifre)*        | **NON** la password normale |
| `SMTP_FROM`  | `BA.IA <simoneserra230@gmail.com>` | mittente mostrato |
| `APP_URL`    | `https://baia-saas.vercel.app/app.html` | il link nell'email punta qui + `?reset_token=...` |

Dopo il salvataggio Render fa **redeploy** automatico (~3-5 min).

---

## Come ottenere la App Password Gmail (2 minuti)

L'invio SMTP da Gmail **non** accetta la password dell'account: serve una *App Password*.

1. Vai su https://myaccount.google.com/security
2. Attiva la **Verifica in due passaggi** (obbligatoria, se non già attiva).
3. Apri https://myaccount.google.com/apppasswords
4. Nome app: scrivi `BA.IA` → **Crea**.
5. Copia le **16 lettere** generate (senza spazi) → incollale in `SMTP_PASS` su Render.

> Gmail gratuito: limite ~500 email/giorno. Più che sufficiente per i reset password.

---

## Alternativa professionale (consigliata se crescono gli utenti): Brevo

Casella dedicata, deliverability migliore, **300 email/giorno gratis**:

| Key | Value |
|-----|-------|
| `SMTP_HOST` | `smtp-relay.brevo.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | *(la tua login SMTP Brevo, es. xxxx@smtp-brevo.com)* |
| `SMTP_PASS` | *(la SMTP key di Brevo)* |
| `SMTP_FROM` | `BA.IA <noreply@tuodominio.it>` |

Registrazione: https://www.brevo.com → *Transactional* → *SMTP & API*.

---

## Verifica che funzioni

1. Dopo il redeploy, vai su `https://baia-saas.vercel.app/app.html`
2. **Password dimenticata?** → inserisci una email **registrata** → *Invia link di reset*
3. Controlla la casella (anche **Spam** la prima volta).
4. In alternativa, da admin puoi testare l'SMTP con l'endpoint `POST /api/settings/smtp/test`
   (body `{"to":"tua@email.it"}`) — risponde `{"ok":true}` se la configurazione è valida.

Se non arriva: su Render apri **Logs** e cerca `[AUTH] Errore email reset:` — la riga ti dice
l'errore esatto (host errato, credenziali, porta bloccata…).
