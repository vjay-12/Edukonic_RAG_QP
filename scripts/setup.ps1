# One-shot setup for Windows PowerShell.  Usage: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

foreach ($c in "docker","python","node") {
  if (-not (Get-Command $c -ErrorAction SilentlyContinue)) { Write-Error "$c is required. See README (Prerequisites)."; exit 1 }
}

if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "Created .env  -> add your GEMINI_API_KEY" }

Write-Host "==> Starting database (pgvector)"
docker compose up -d db

Write-Host "==> Backend virtualenv + dependencies"
python -m venv backend\.venv
& backend\.venv\Scripts\python.exe -m pip install --upgrade pip
& backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

Write-Host "==> Frontend dependencies"
Push-Location frontend
if (Test-Path package-lock.json) { npm ci } else { npm install }
Pop-Location

Write-Host ""
Write-Host "Setup done. Next:"
Write-Host "  1) put your key in .env (GEMINI_API_KEY)"
Write-Host "  2) put chapter PDFs in data\books\ and fill data\books\manifest.yaml"
Write-Host "  3) see README.md -> 'Ingest the books'"
