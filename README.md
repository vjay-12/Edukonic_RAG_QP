# Edukonic_RAG_QP

RAG-based CBSE question paper generator (Class 10 Science pilot). Backend-first: books are ingested and
verified from the CLI; the web UI is only for teachers to generate papers.

## Prerequisites
- Docker Desktop (for Postgres + pgvector)
- Python 3.11+ (resolved on 3.12)
- Node 20.19+ or 22.12+ (see `.nvmrc`)
- Local embeddings powered by `sentence-transformers` (`BAAI/bge-base-en-v1.5`, 768-dim, CPU/GPU)
- A free Gemini API key (for paper generation & validation): https://aistudio.google.com -> Get API key

## Setup (fresh clone)
macOS / Linux / WSL / Git Bash:
```bash
bash scripts/setup.sh
```
Windows PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```
Then edit `.env` and set `GEMINI_API_KEY`.

## Ingest the books (backend only)
1. Put chapter PDFs under `data/books/` (see `data/books/README.md`) and copy `data/books/manifest.example.yaml` to `data/books/manifest.yaml`.
2. Run (from `backend/`, venv active):
```bash
python -m app.cli ingest --manifest ../data/books/manifest.yaml
python -m app.cli chunks report          # QA report, must pass the gate
python -m app.cli search "Ohm's law" --chapter 11 -k 5
```
3. Skip PDFs and embeddings on another machine by importing the seed file:
```bash
python -m app.cli db import-seed ../data/seed/chunks.jsonl.gz
```

## Run
```bash
# terminal 1 (backend/, venv active)
uvicorn app.main:app --reload --port 8000
# terminal 2
cd frontend && npm run dev      # http://localhost:5173
```

See `docs/PLAN.md` for the full build plan.
