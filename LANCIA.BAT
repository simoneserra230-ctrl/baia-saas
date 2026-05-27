@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title BA.IA — Finanza Agevolata AI v3.0
cd /d "%~dp0"
color 0A
cls
echo.
echo   ╔══════════════════════════════════════════════╗
echo   ║         BA.IA  v3.0                          ║
echo   ║   Piattaforma AI Finanza Agevolata           ║
echo   ╚══════════════════════════════════════════════╝
echo.

set PYTHON=
where python >nul 2>&1 && set PYTHON=python
if "!PYTHON!"=="" (
  where python3 >nul 2>&1 && set PYTHON=python3
)
if "!PYTHON!"=="" (
  color 0C
  echo.
  echo   [ERRORE] Python non trovato.
  echo.
  echo   Installa Python 3.10 o superiore da:
  echo   https://www.python.org/downloads/
  echo.
  echo   IMPORTANTE: spunta "Add Python to PATH" durante l'installazione
  echo.
  set /p APRI="   Aprire python.org adesso? [s/N] "
  if /i "!APRI!"=="s" start "" "https://www.python.org/downloads/"
  pause
  exit /b 1
)
for /f "tokens=*" %%v in ('!PYTHON! --version 2^>^&1') do set PYVER=%%v
echo   [OK] !PYVER!

if not exist ".venv\Scripts\uvicorn.exe" (
  echo.
  echo   Prima installazione (solo questa volta, 2-3 minuti)...
  echo.
  !PYTHON! -m venv .venv >nul 2>&1
  if %errorlevel% neq 0 (
    color 0C
    echo   [ERRORE] Impossibile creare ambiente Python.
    pause
    exit /b 1
  )
  echo   [1/3] Ambiente Python creato
  .venv\Scripts\pip install --quiet --upgrade pip >nul 2>&1
  echo   [2/3] Pip aggiornato
  .venv\Scripts\pip install --quiet -r backend\requirements.txt
  if %errorlevel% neq 0 (
    color 0C
    echo   [ERRORE] Installazione dipendenze fallita.
    pause
    exit /b 1
  )
  echo   [3/3] Dipendenze installate
  echo.
  echo   Installazione completata!
)

if not exist ".env" (
  echo GROQ_API_KEY=gsk_INSERISCI_LA_TUA_CHIAVE_QUI> ".env"
  echo LICENSE_KEY=TEST-MODE>> ".env"
  echo GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct>> ".env"
  echo APP_NAME=BA.IA>> ".env"
  echo DB_PATH=./data/ai-bandi.db>> ".env"
  echo PORT=8000>> ".env"
  echo SMTP_HOST=>> ".env"
  echo SMTP_PORT=587>> ".env"
  echo SMTP_USER=>> ".env"
  echo SMTP_PASS=>> ".env"
  echo SMTP_FROM=noreply@baia.it>> ".env"
)

if not exist "data" mkdir data

set PORT=8000
for /f "tokens=2 delims==" %%a in ('findstr /b "PORT=" .env 2^>nul') do set PORT=%%a
set PORT=!PORT: =!
if "!PORT!"=="" set PORT=8000

for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":!PORT! " ^| findstr "LISTENING"') do (
  taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

cls
color 0A
echo.
echo   ╔══════════════════════════════════════════════╗
echo   ║         BA.IA  v3.0                          ║
echo   ╚══════════════════════════════════════════════╝
echo.
echo   Avvio in corso...
echo.
echo   L'app si aprira' automaticamente nel browser.
echo   URL: http://localhost:!PORT!
echo.
echo   Per chiudere l'app, chiudi questa finestra.
echo   ─────────────────────────────────────────────
echo.

start "" cmd /c "timeout /t 3 /nobreak >nul && start \"\" \"%~dp0frontend\index.html\""

set PYTHONPATH=%~dp0
.venv\Scripts\uvicorn backend.app_locale:app ^
  --host 0.0.0.0 ^
  --port !PORT! ^
  --log-level warning ^
  --no-access-log

echo.
echo   App chiusa.
pause
