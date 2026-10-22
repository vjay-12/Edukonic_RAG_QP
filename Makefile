# macOS / Linux / WSL.  Windows users: see the PowerShell commands in README.md
PY=backend/.venv/bin/python
.PHONY: setup db api ui ingest chunks-report test reset-db

setup:        ; bash scripts/setup.sh
db:           ; docker compose up -d db
api:          ; cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000
ui:           ; cd frontend && npm run dev
ingest:       ; cd backend && .venv/bin/python -m app.cli ingest --manifest ../data/books/manifest.yaml
chunks-report:; cd backend && .venv/bin/python -m app.cli chunks report
test:         ; cd backend && .venv/bin/python -m pytest -q
reset-db:     ; docker compose down -v && docker compose up -d db
