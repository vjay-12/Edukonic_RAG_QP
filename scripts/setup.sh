#!/usr/bin/env bash
# One-shot setup for macOS / Linux / WSL / Git Bash.  Usage: bash scripts/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

command -v docker >/dev/null || { echo "Docker is required (Docker Desktop)."; exit 1; }
command -v python3 >/dev/null || { echo "Python 3.11+ is required."; exit 1; }
command -v node >/dev/null || { echo "Node 20.19+ or 22.12+ is required."; exit 1; }

[ -f .env ] || { cp .env.example .env; echo "Created .env  -> add your GEMINI_API_KEY"; }

echo "==> Starting database (pgvector)"
docker compose up -d db

echo "==> Backend virtualenv + dependencies"
python3 -m venv backend/.venv
# shellcheck disable=SC1091
source backend/.venv/bin/activate 2>/dev/null || source backend/.venv/Scripts/activate
pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r backend/requirements.txt

echo "==> Frontend dependencies"
(cd frontend && npm ci || npm install)

echo
echo "Setup done. Next:"
echo "  1) put your key in .env (GEMINI_API_KEY)"
echo "  2) put chapter PDFs in data/books/ and fill data/books/manifest.yaml"
echo "  3) see README.md -> 'Ingest the books'"
