# smoke.ps1 — BA.IA run/smoke-test driver (Windows PowerShell)
# Run from the project root: powershell -File .claude\skills\run-baia-saas\smoke.ps1
# Optional arg: -Port 8000 (default)
param([int]$Port = 8000)

$ErrorActionPreference = "Stop"
$proj = $PSScriptRoot | Split-Path | Split-Path | Split-Path   # up 3: skills/run-baia-saas -> skills -> .claude -> project root
$base = "http://127.0.0.1:$Port"

function Check($label, $status, $body) {
    if ($status -eq 200 -or $status -eq 201) {
        Write-Host "  OK  $label" -ForegroundColor Green
    } else {
        Write-Host "  FAIL $label ($status): $body" -ForegroundColor Red
        exit 1
    }
}

# ── 1. Kill anything on the port ─────────────────────────────
Write-Host "[1] Clearing port $Port..."
Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# ── 2. Start uvicorn ─────────────────────────────────────────
Write-Host "[2] Starting BA.IA backend..."
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# Load .env if present
$envFile = Join-Path $proj ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -match "^[A-Z_]+=.*" -and $_ -notmatch "^#" } | ForEach-Object {
        $k, $v = $_ -split "=", 2
        [System.Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), "Process")
    }
}
# Ensure test-safe overrides
$env:LICENSE_KEY = "TEST-MODE"
if (-not $env:GROQ_API_KEY -or $env:GROQ_API_KEY -match "INSERISCI") { $env:GROQ_API_KEY = "dummy-key-for-smoke-test" }

$uvicorn = Join-Path $proj ".venv\Scripts\uvicorn.exe"
$errFile = [System.IO.Path]::GetTempFileName()
$proc = Start-Process -FilePath $uvicorn `
    -ArgumentList "backend.app_locale:app","--host","127.0.0.1","--port","$Port","--log-level","warning","--no-access-log" `
    -WorkingDirectory $proj -RedirectStandardError $errFile -NoNewWindow -PassThru

# ── 3. Wait for server ───────────────────────────────────────
Write-Host "[3] Waiting for server..."
$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri "$base/" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
}
if (-not $ready) {
    Write-Host "Server did not start in 20s. Stderr:" -ForegroundColor Red
    Get-Content $errFile | Select-Object -Last 20
    $proc | Stop-Process -Force -ErrorAction SilentlyContinue
    exit 1
}
Write-Host "  Server up (PID $($proc.Id))"

# ── 4. Smoke tests ───────────────────────────────────────────
Write-Host "[4] Running smoke tests..."
try {
    # Health
    $r = Invoke-WebRequest -Uri "$base/" -UseBasicParsing -TimeoutSec 5
    Check "GET /" $r.StatusCode $r.Content

    # Model info
    $r = Invoke-WebRequest -Uri "$base/model" -UseBasicParsing -TimeoutSec 5
    Check "GET /model" $r.StatusCode $r.Content

    # Register test user
    $body = '{"email":"smoketest@baia.local","password":"SmokePass123!","name":"Smoke Test"}'
    try {
        $r = Invoke-WebRequest -Uri "$base/auth/register" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing -TimeoutSec 5
    } catch {
        # Already registered — login instead
        $body2 = '{"email":"smoketest@baia.local","password":"SmokePass123!"}'
        $r = Invoke-WebRequest -Uri "$base/auth/login" -Method POST -Body $body2 -ContentType "application/json" -UseBasicParsing -TimeoutSec 5
    }
    Check "POST /auth/register or /auth/login" $r.StatusCode $r.Content
    $TOKEN = ($r.Content | ConvertFrom-Json).token
    $H = @{ "X-Auth-Token" = $TOKEN }

    # Authenticated: /auth/me
    $r = Invoke-WebRequest -Uri "$base/auth/me" -Headers $H -UseBasicParsing -TimeoutSec 5
    Check "GET /auth/me" $r.StatusCode $r.Content

    # DB: bandi list
    $r = Invoke-WebRequest -Uri "$base/db/bandi" -Headers $H -UseBasicParsing -TimeoutSec 5
    Check "GET /db/bandi" $r.StatusCode $r.Content

    # DB: aziende list
    $r = Invoke-WebRequest -Uri "$base/db/aziende" -Headers $H -UseBasicParsing -TimeoutSec 5
    Check "GET /db/aziende" $r.StatusCode $r.Content

    # Scraper status
    $r = Invoke-WebRequest -Uri "$base/scraper/status" -Headers $H -UseBasicParsing -TimeoutSec 5
    Check "GET /scraper/status" $r.StatusCode $r.Content

    Write-Host ""
    Write-Host "All smoke tests PASSED" -ForegroundColor Green
    Write-Host "  Frontend available at: $base/app"
    Write-Host "  API docs at:           $base/api/docs"
    Write-Host "  Token for manual use:  $TOKEN"
    Write-Host "  Header to use:         X-Auth-Token: $TOKEN"
} finally {
    # ── 5. Teardown ──────────────────────────────────────────
    Write-Host ""
    Write-Host "[5] Stopping server (PID $($proc.Id))..."
    $proc | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "  Done."
}
