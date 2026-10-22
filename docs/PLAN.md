# Edukonic_RAG_QP — Plan v2 (for the coding agent)

Supersedes v1 where they differ. Pilot scope: **Class 10, CBSE (NCERT), Science**, 3 chapters first (Ch 1 Chemical Reactions and Equations, Ch 5 Life Processes, Ch 11 Electricity; confirm numbering from the PDFs). Internal use for one school.

## 0. Key decisions (v2)

1. **Backend first.** Books are ingested and verified from a **CLI**. No upload or chunk-inspection UI.
2. **The web UI is for teachers only**, and only to generate question papers (configure, generate, review, export).
3. **Quality gate:** the UI work starts only after the chunk QA report and the retrieval test pass (Section 3).
4. **Portable repo:** a fresh `git clone` plus the setup script gives a running app. Pinned dependencies, lockfiles, `.env.example`, Docker DB, optional seed file so another machine can skip PDFs and embeddings.
5. **UI theme** matches the Edkonic school ERP demo (Section 7).

The setup kit (`Edukonic_RAG_QP_setup_kit.zip`) already contains: `requirements.in/.txt` (pinned), `.env.example`, `docker-compose.yml`, `db/init.sql`, `scripts/setup.sh|ps1`, `Makefile`, `.gitignore`, `.nvmrc`, `README.md`, `data/books/manifest.example.yaml`, and a frontend skeleton (`package.json` + lockfile, Vite config, `index.css` with the theme tokens, a placeholder `App.tsx`). **Unzip it as the repo root, do not regenerate these files.** The frontend skeleton was built successfully with `npm run build`.

## 1. Flow

```
STAGE 1  (backend + CLI only)
  PDFs + manifest.yaml
     └─ cli ingest ──► parse ► clean ► chunk ► embed ► Postgres/pgvector
     └─ cli chunks report / show / list ──► human check of chunks
     └─ cli search "<query>" ──► retrieval check
     └─ cli eval-retrieval ──► hit-rate on a small test set
     └─ cli generate --config configs/unit_test_25.json ──► paper JSON + Markdown
     └─ QUALITY GATE (Section 3)  ── must pass before Stage 2

STAGE 2  (teacher UI, generate only)
  Login ► Configure ► Generate (progress) ► Review/Edit/Accept ► Export (DOCX, print-PDF)
                                       └─ accepted questions → question bank (used for dedupe)
```

## 2. Stack and repo layout

Backend: Python 3.11+, FastAPI, SQLAlchemy 2, Pydantic v2, Postgres 16 + pgvector (Docker), `sentence-transformers` (local embeddings with `BAAI/bge-base-en-v1.5`), `google-genai` (Gemini for generation/validation), `pymupdf` + `pymupdf4llm`, `python-docx`, `typer` + `rich` (CLI), `tenacity` (retries), `pytest`.
Frontend: React 19 + Vite + TypeScript + Tailwind 4 + TanStack Query + React Router + framer-motion + lucide-react.

```
Edukonic_RAG_QP/
├─ README.md  Makefile  docker-compose.yml  .env.example  .gitignore  .nvmrc
├─ db/init.sql                       # CREATE EXTENSION vector
├─ scripts/setup.sh  setup.ps1
├─ docs/PLAN.md                      # this file
├─ configs/                          # paper configs + blueprints (JSON)
│  ├─ cbse10_science_80.json
│  └─ unit_test_25.json
├─ data/
│  ├─ books/ (PDFs not committed)  manifest.yaml  manifest.example.yaml
│  ├─ seed/chunks.jsonl.gz           # exported chunks + embeddings (commit only if repo is PRIVATE)
│  └─ eval/retrieval_queries.yaml    # ~20 test queries with expected chapter/page
├─ reports/                          # generated QA reports (gitignored)
├─ backend/
│  ├─ requirements.in  requirements.txt
│  ├─ app/
│  │  ├─ main.py  config.py  db.py  models.py  schemas.py
│  │  ├─ cli.py                      # typer app (Section 4)
│  │  ├─ api/ chapters.py papers.py bank.py auth.py
│  │  ├─ services/ llm.py ingest.py chunker.py qa.py retrieval.py planner.py generator.py validator.py dedupe.py exporter.py seed.py
│  │  └─ prompts/ generate_system.md generate_<type>.md validate.md
│  └─ tests/
└─ frontend/ (skeleton from the kit)
   └─ src/ api/ pages/ components/ index.css
```

`config.py` reads everything from `.env` (names in `.env.example`). No secrets in code.

## 3. Stage 1: backend and CLI

### 3.1 Database (create_all on startup or `cli db init`)

```
documents        id, class, subject, chapter_no, chapter_title, edition_year, source_file, page_count, status, created_at
chunks           id, document_id, chapter_no, page_start, page_end, section_heading,
                 content_type(concept|example|exercise|activity|summary), text, token_count, embedding vector(EMBED_DIM)
papers           id, title, config JSON, status(queued|planning|generating|validating|ready|failed), progress, error, created_at
paper_questions  id, paper_id, slot_no, section, type, marks, chapter_no, topic, difficulty, competency, bloom,
                 content JSON, source_chunk_ids int[], validation JSON, status(draft|accepted|rejected), embedding vector(EMBED_DIM)
question_bank    id, content JSON, class, subject, chapter_no, type, marks, difficulty, competency, source JSON, embedding, approved_at
reference_questions  id, source, year, marks, type, chapter_no, text, competency, embedding   (style exemplars, optional)
```
HNSW index on `chunks.embedding`; btree on `chunks.chapter_no`.

### 3.2 CLI commands (`python -m app.cli ...`, run from `backend/`)

| Command | What it does |
|---|---|
| `db init` / `db reset` | Create tables and extension / drop and recreate |
| `ingest --manifest ../data/books/manifest.yaml [--chapter N] [--force]` | Parse, clean, chunk, embed, store. Idempotent per (class, subject, chapter, edition) |
| `chunks list --chapter N [--type concept]` | Table: id, pages, type, tokens, heading, first 80 chars |
| `chunks show <id>` | Full chunk text and metadata |
| `chunks report [--chapter N]` | QA report (3.3), printed and written to `reports/chunks_<chapter>.md` |
| `chunks export --out file.jsonl` | Dump chunks (for manual review) |
| `search "<query>" [--chapter N] [-k 5]` | Top-k chunks with cosine score, pages, snippet |
| `eval-retrieval` | Run `data/eval/retrieval_queries.yaml`, print hit-rate@3 and misses |
| `generate --config configs/unit_test_25.json [--out reports/paper.md]` | Run the full generation pipeline from the CLI and print or save the paper JSON and a Markdown rendering |
| `db export-seed --out ../data/seed/chunks.jsonl.gz` | Export chunks with embeddings, plus a header with `EMBED_MODEL` and `EMBED_DIM` |
| `db import-seed <file>` | Import and refuse if model or dimension differ from `.env` |

### 3.3 Ingestion rules (`ingest.py`, `chunker.py`)

1. Parse with `pymupdf4llm` to Markdown, keeping the page number for each block. OCR (Tesseract) only for pages with almost no text, and only if installed.
2. Clean: drop running headers, footers, and page numbers; re-join hyphenated words; normalize whitespace and Unicode.
3. Split on headings and section numbers (for example "5.1", "Activity 1.1", "Questions", "Exercises"). Never cross a section boundary.
4. `content_type` rules: contains "Activity" → `activity`; "Questions" or "Exercises" → `exercise`; "Example" → `example`; "What you have learnt" or "Summary" → `summary`; else `concept`.
5. Re-chunk long sections to about `CHUNK_TARGET_TOKENS` (350 tokens, max `CHUNK_MAX_TOKENS` 480 tokens) with `CHUNK_OVERLAP_TOKENS` overlap, counted with the model tokenizer. Merge tiny fragments into neighbors.
6. Embed with normalized embeddings (`llm.py`, GPU if available else CPU; BGE query prefix for search queries only, not for chunks), in batches of `EMBED_BATCH_SIZE` (32), then insert. Set document status `ready` only if all chunks are embedded.

### 3.4 Chunk QA report (`qa.py`) and quality gate

The report lists, per chapter:
- total chunks, average and max tokens, token histogram
- **page coverage** = pages that have at least one chunk / total pages (ignore blank and cover pages)
- chunks under 40 tokens, over the max, empty, or without a page number
- suspicious text: mojibake, long runs of symbols, broken words, repeated lines
- near-duplicate chunks (embedding cosine above 0.97)
- `content_type` distribution
- 10 random chunks printed in full for manual spot check

**Gate (all must hold before Stage 2):**
- page coverage ≥ 98%
- no empty chunks; fewer than 3% chunks under 40 tokens
- fewer than 1% chunks flagged as garbled text
- `eval-retrieval`: hit-rate@3 ≥ 90% on the test set (expected chapter and page range appear in the top 3)
- you sign off the 10 random chunks per chapter

If it fails, fix parsing or chunking and re-run `ingest --force` before building anything else.

### 3.5 Generation pipeline (shared by CLI and API)

```
config → plan slots → for each batch of same-type slots:
   choose anchor chunks → retrieve context → generate (JSON) → deterministic checks → LLM validate
   → dedupe → store draft → blueprint report
```

- **Plan:** expand config into slots `(slot_no, section, type, marks, chapter_no, difficulty, competency, bloom_hint)`. Allocate slots to chapters by weight using largest-remainder rounding so counts match exactly. Assign difficulty and competency flags to match the mix.
- **Anchors and context:** per slot, pick an anchor chunk (prefer `concept` and `example`, spread evenly, avoid reuse). Context = anchor + top `RETRIEVAL_NEIGHBORS` similar chunks in the same chapter. Add 2 or 3 style exemplars from `reference_questions` when available.
- **Generate:** one LLM call per batch of same-type slots, structured JSON output, concurrency `LLM_CONCURRENCY`, exponential backoff on 429 and 5xx.
- **Question JSON**

```json
{
  "slot_no": 3,
  "type": "mcq | assertion_reason | vsa | sa | la | case",
  "marks": 1,
  "stem": "question text (for case: the case passage)",
  "options": ["...", "...", "...", "..."],
  "correct_option": "B",
  "sub_questions": [{"stem": "...", "marks": 1, "options": null, "answer": "..."}],
  "answer": "model answer",
  "marking_scheme": [{"step": "Formula", "marks": 1}, {"step": "Calculation", "marks": 2}],
  "difficulty": "easy | medium | hard",
  "competency": true,
  "bloom": "remember | understand | apply | analyze | evaluate",
  "chapter_no": 11,
  "topic": "Ohm's law",
  "source": {"chunk_ids": [412, 415], "pages": [178, 179]},
  "insufficient_context": false
}
```

- **Prompt rules (`generate_system.md`):** use only the CONTEXT, return `insufficient_context: true` if it cannot support the question; CBSE style and command words; MCQ has exactly 4 options and exactly 1 correct with plausible distractors and no "all of the above"; assertion-reason uses the standard four options; case-based has a short case plus sub-questions whose marks sum to the case marks; depth matches marks; `marking_scheme` marks sum exactly to `marks`; numericals show formula, substitution, and unit.
- **Deterministic checks (no LLM):** JSON valid against the schema, marking scheme sums to marks, MCQ has 4 options and a valid `correct_option`, source chunk IDs exist, case sub-marks sum correctly.
- **LLM validator** (same context, batched): returns `{grounded, answer_correct, marks_fit, single_correct_option, issues[], verdict}`. On `fail`, regenerate once with the issues appended; if it still fails, keep as `draft` flagged.
- **Dedupe:** embed each stem; compare with the same paper, `question_bank`, and `reference_questions`; similarity above `DEDUPE_THRESHOLD` triggers regeneration with an instruction to use a different angle.
- **Blueprint report:** marks per chapter, count per type, difficulty split, competency %, mark total check, number of flagged questions.
- **LLM and embedding wrapper (`llm.py`)** encapsulates all AI models: `embed(texts, is_query=False)` (supports local `sentence-transformers` with normalized vectors, BGE query prefix for search queries, and fallback to `gemini`), and `generate_json(prompt, schema, model)` via Gemini SDK. Models, provider, and dimensions come from `.env`.

### 3.6 Blueprint presets (`configs/`)

`cbse10_science_80.json` (verify against the current CBSE curriculum document and sample paper before the demo):

| Section | Type | Count | Marks each | Total |
|---|---|---|---|---|
| A | MCQ (16) + Assertion-Reason (4) | 20 | 1 | 20 |
| B | Very short answer | 6 | 2 | 12 |
| C | Short answer | 7 | 3 | 21 |
| D | Long answer | 3 | 5 | 15 |
| E | Case-based | 3 | 4 | 12 |

`unit_test_25.json`: A 5×1, B 2×2, C 2×3, D 1×5, E 1×4 = 25. Paper config shape:

```json
{
  "title": "Unit Test 1 - Science", "class": 10, "subject": "Science",
  "chapters": [{"chapter_no": 1, "weight": 0.4}, {"chapter_no": 5, "weight": 0.3}, {"chapter_no": 11, "weight": 0.3}],
  "sections": [{"id": "A", "type": "mcq", "count": 5, "marks": 1}],
  "difficulty_mix": {"easy": 0.3, "medium": 0.5, "hard": 0.2},
  "competency_percent": 40,
  "avoid_duplicates_from_bank": true,
  "header": {"school_name": "", "exam_name": "", "date": "", "duration": "1 hour", "instructions": []}
}
```
Validate: section marks equal the total, chapter weights sum to 1, competency 0 to 100.

## 4. Stage 2: API and teacher UI

### 4.1 API (FastAPI, prefix `/api`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/auth/login` | Body `{password}`; checks `APP_PASSWORD`; returns a session token (simple signed token) |
| GET | `/chapters` | Ready chapters with chunk counts (read only; no upload endpoint) |
| GET | `/blueprints` | Presets from `configs/` |
| POST | `/papers` | Validate config, create paper, start generation in a background task |
| GET | `/papers`, `/papers/{id}` | History; paper with questions, status, progress, report |
| PATCH | `/papers/{id}/questions/{qid}` | Edit content or set status accepted or rejected |
| POST | `/papers/{id}/questions/{qid}/regenerate` | Optional body `{instruction}` |
| POST | `/papers/{id}/finalize` | Save accepted questions to the bank |
| GET | `/papers/{id}/export?format=docx&part=paper|key` | Download |
| GET | `/chunks/{id}` | Source text for the citation drawer |
| GET | `/bank` | Filter by chapter, type, marks, difficulty |

### 4.2 Teacher UI pages (React Router)

| Route | Content |
|---|---|
| `/login` | Password form |
| `/generate` | Hero with badge, then the configure form: title, preset, chapter picker with weights (only `ready` chapters), editable sections table with live marks total and warning, difficulty sliders, competency %, dedupe toggle, school header and instructions. Button "Generate paper" |
| `/papers/:id` | While running: gradient progress bar with stage labels. When ready: **Review** with sections A to E, question cards, sticky summary and blueprint report |
| `/papers/:id/preview` | Print-ready layout, "Download paper (DOCX)", "Download answer key (DOCX)", "Print / Save as PDF" |
| `/papers` | History table |
| `/bank` | Filterable question bank |

Question card: stem, options or sub-questions, answer and marking scheme (collapsible), pill badges (type, marks, difficulty, competency, chapter), validation chip (ok, warn, bad), **source chip** "NCERT Science 10 · p.178" opening a drawer with the chunk text. Actions: Edit inline, Regenerate (with optional instruction), Accept, Reject. Paper level: "Accept all passing", "Finalize".

Polling: TanStack Query, every 2 s while status is not `ready` or `failed`. Show friendly toasts on rate-limit retries.

### 4.3 Export (`exporter.py`)

Paper DOCX: school header, exam details, general instructions, section headings ("Section A, 1 mark each"), numbered questions, options on separate lines, case passage in a bordered paragraph, marks right-aligned. Answer key DOCX: correct option or model answer, step-wise marking scheme, source page. PDF: print stylesheet on the preview page.

## 5. Portability rules (the repo must run on a clean machine)

- Commit `backend/requirements.txt` (pinned), `backend/requirements.in`, `frontend/package-lock.json`, `.nvmrc`, `.env.example`, `docker-compose.yml`, `db/init.sql`.
- Never commit `.env`, book PDFs, `node_modules`, `.venv`, `reports/`.
- `data/seed/chunks.jsonl.gz` is created by `db export-seed` and is committed **only if the repo is private** (it contains NCERT text). `db import-seed` refuses to load if `EMBED_MODEL` or `EMBED_DIM` differ.
- Fresh machine, Windows: `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1`, set `GEMINI_API_KEY` in `.env`, then either `ingest` (needs PDFs and the API key) or `db import-seed` (needs neither).
- Run: `uvicorn app.main:app --reload --port 8000` in `backend/` (venv active) and `npm run dev` in `frontend/`.
- Add a pytest smoke test: app imports, `/api/health` returns 200, chunker unit tests on a small text fixture, marking-scheme and blueprint-sum validators.
- README stays accurate: update it whenever commands change.

## 6. Build order for the agent

1. Unzip the setup kit as the repo root; commit. Verify `docker compose up -d db` and the setup script.
2. `config.py`, `db.py`, `models.py`, `llm.py` (local `sentence-transformers` embedding with `BAAI/bge-base-en-v1.5` and Gemini JSON generation working).
3. `chunker.py` (model tokenizer, 350 target/480 max tokens), `ingest.py`, CLI `ingest`, `chunks list|show|report`, `search`. Run on the 3 pilot chapters. **Stop and show me the report.**
4. `eval-retrieval` with `data/eval/retrieval_queries.yaml` (~20 queries with BGE search query prefix). Pass the gate and recalibrate `DEDUPE_THRESHOLD`.
5. `planner`, `retrieval`, `generator`, `validator`, `dedupe`; CLI `generate` for the 25-mark preset. Review output together.
6. API (`chapters`, `papers`, background generation, export) and `db export-seed|import-seed`.
7. Teacher UI pages in the theme (Section 7). Order: `/generate`, progress and review, preview and export, history and bank.
8. Pytest smoke tests, README check on a clean clone, demo rehearsal.

## 7. UI theme (match the Edkonic demo)

Tokens already live in `frontend/src/index.css` (dark default, light via `data-theme="light"` toggle). Reference look:
- Near-black navy background with two soft glows (blue top right, magenta bottom): class `bg-glow`.
- Large serif display headings with tight tracking (class `display`; font variable `--font-display`, currently Instrument Serif); words inside headings highlighted with gradients (`grad-blue`, `grad-pink`).
- Inter for body; muted gray secondary text.
- Fully rounded **pill** buttons: primary is near-white with dark text (`btn btn-primary`), secondary is ghost with a thin border (`btn btn-ghost`); arrow icon on primary actions.
- Pill badges (`chip`, with `chip-ok|warn|bad`) such as "New · AI question paper generator".
- Rounded glass cards with a 1px translucent border (`glass`), generous spacing, top nav with a subtle bottom border, theme toggle button.
- Gradient progress bar (`bar > i`), blue focus rings on fields (`field`).
- Motion: short fade and slide only (framer-motion). No heavy animation.
- Colors and the serif font are approximated from a screenshot. If the Edkonic codebase has its exact tokens and font, copy them into `index.css` so both apps match.

## 8. Acceptance criteria

- Stage 1 gate passed and the QA report committed to the repo notes.
- Every generated question has a source page that opens in the drawer.
- Section and paper marks add up exactly to the configured total.
- A teacher accepts at least 70% of questions with little or no editing (rate 50 to 100 questions).
- Fewer than 5% duplicates; fewer than 10% flagged after one regeneration.
- A 25-mark paper generates in about 2 minutes or less on the free tier.
- Paper and answer key DOCX open cleanly in Word.
- A clean clone runs using only the README steps.

## 9. Risks

Free-tier rate limits (batch per section, concurrency 2, backoff). Bad PDF parsing (gate catches it; OCR fallback). Hallucination (context-only prompt, validator, citations, teacher review). Edition mismatch (store `edition_year`; Class 10 books continue in 2026-27, new ones expected from 2027-28). Free-tier prompts may be human-reviewed (NCERT text only, no student data). Copyright (internal use; private repo; no publisher books without permission). Blueprint numbers (verify against the official curriculum).

## 10. What you need to arrange (get and use)

1. **Gemini API key:** aistudio.google.com → Get API key → paste into `.env` as `GEMINI_API_KEY`. The Google AI Pro subscription does not include API access. Confirm current model names in AI Studio and update `GEN_MODEL`, `VALIDATE_MODEL`, `EMBED_MODEL` if needed. Free tier limits are low; enable billing on the Cloud project if you hit them.
2. **Vector DB:** no extra service. Install Docker Desktop, then `docker compose up -d db` starts Postgres with pgvector (`DATABASE_URL` in `.env.example` already matches). Without Docker, use hosted Postgres with pgvector (for example Supabase free tier), enable the `vector` extension, and set `DATABASE_URL`.
3. **Books:** download the NCERT Class 10 Science chapter PDFs (ncert.nic.in, textbook section) for the edition your school uses into `data/books/class10/science/`, and copy `manifest.example.yaml` to `manifest.yaml`.
4. **CBSE references:** current Class 10 Science curriculum document and sample paper with marking scheme (cbseacademic.nic.in), to verify the blueprint and write about 20 retrieval test queries.
5. **Tools:** Python 3.11+, Node 20.19+ or 22.12+, Docker Desktop. Tesseract only if a PDF is scanned.
