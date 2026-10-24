from pathlib import Path
from typing import Optional
import json
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from app.db import SessionLocal, init_db, reset_db, engine
from app.models import Chunk, Document
from app.services.ingest import ingest_manifest
from app.services.qa import generate_qa_report
from app.services.retrieval import search_chunks

console = Console()
app = typer.Typer(help="Edukonic RAG Question Paper Generator CLI")
db_app = typer.Typer(help="Database operations")
chunks_app = typer.Typer(help="Inspect and report on chunks")
papers_app = typer.Typer(help="Manage and export papers")

app.add_typer(db_app, name="db")
app.add_typer(chunks_app, name="chunks")
app.add_typer(papers_app, name="papers")

# ----------------- DB COMMANDS -----------------
@db_app.command("init")
def cli_db_init():
    """Create all database tables and enable vector extension."""
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
    init_db()
    console.print("[bold green][OK] Database tables and pgvector extension initialized successfully![/bold green]")

@db_app.command("reset")
def cli_db_reset():
    """Drop and recreate all database tables."""
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
    reset_db()
    console.print("[bold yellow][OK] Database tables reset and recreated successfully![/bold yellow]")

@db_app.command("export-seed")
def cli_db_export_seed(
    out: str = typer.Option("../data/seed/chunks.jsonl.gz", "--out", "-o", help="Path to seed archive output (.jsonl.gz)"),
):
    """Export chunks and embeddings to compressed seed file."""
    from app.services.seed import export_seed
    out_file = Path(out).resolve()
    with SessionLocal() as db:
        count = export_seed(db, out_file)
        console.print(f"[bold green][OK] Exported {count} chunks to seed file:[/bold green] {out_file}")

@db_app.command("import-seed")
def cli_db_import_seed(
    seed_file: str = typer.Argument(..., help="Path to seed file (.jsonl.gz)"),
):
    """Import chunks and embeddings from seed file (validates embedding model and dim)."""
    from app.services.seed import import_seed
    s_path = Path(seed_file).resolve()
    with SessionLocal() as db:
        try:
            docs, chunks = import_seed(db, s_path)
            console.print(f"[bold green][OK] Imported {docs} documents and {chunks} chunks from seed file:[/bold green] {s_path}")
        except Exception as e:
            console.print(f"[bold red]Seed import failed:[/bold red] {e}")
            raise typer.Exit(1)

# ----------------- INGEST COMMAND -----------------
@app.command("ingest")
def cli_ingest(
    manifest: str = typer.Option("../data/books/manifest.yaml", "--manifest", "-m", help="Path to manifest.yaml"),
    chapter: Optional[int] = typer.Option(None, "--chapter", "-c", help="Specific chapter number to ingest"),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-ingestion if already ingested"),
):
    """Ingest textbook chapters from manifest.yaml: parse, chunk, embed, and store in pgvector."""
    console.print(f"[bold blue]Starting ingestion from:[/bold blue] {manifest}")
    try:
        results = ingest_manifest(manifest, chapter_filter=chapter, force=force)
        for r in results:
            if r["status"] == "ready":
                console.print(
                    f"[green][OK] Chapter {r['chapter_no']}: {r['title']}[/green] "
                    f"({r['page_count']} pages -> [bold]{r['chunks_count']} chunks[/bold] embedded)"
                )
            else:
                console.print(f"[yellow]! Chapter {r['chapter_no']}: {r['title']}[/yellow] - {r['message']}")
    except Exception as e:
        console.print(f"[bold red]Ingestion failed:[/bold red] {e}")
        raise typer.Exit(1)

# ----------------- CHUNKS COMMANDS -----------------
@chunks_app.command("list")
def cli_chunks_list(
    chapter: int = typer.Option(..., "--chapter", "-c", help="Chapter number"),
    content_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by content_type"),
    limit: int = typer.Option(50, "--limit", "-l", help="Max chunks to display"),
):
    """List chunks in a table: id, pages, type, tokens, heading, snippet."""
    with SessionLocal() as db:
        query = db.query(Chunk).filter(Chunk.chapter_no == chapter)
        if content_type:
            query = query.filter(Chunk.content_type == content_type)
        chunks = query.order_by(Chunk.id).limit(limit).all()

        if not chunks:
            console.print(f"[yellow]No chunks found for chapter {chapter}.[/yellow]")
            return

        table = Table(title=f"Chunks for Chapter {chapter}")
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Pages", style="magenta", width=10)
        table.add_column("Type", style="green", width=12)
        table.add_column("Tokens", justify="right", width=8)
        table.add_column("Section Heading", style="yellow", width=25)
        table.add_column("Snippet (First 80 chars)", style="white")

        for c in chunks:
            snippet = c.text[:80].replace("\n", " ").strip() + "..."
            table.add_row(
                str(c.id),
                f"p.{c.page_start}-{c.page_end}",
                c.content_type,
                str(c.token_count),
                (c.section_heading or "")[:25],
                snippet,
            )
        console.print(table)

@chunks_app.command("show")
def cli_chunks_show(chunk_id: int):
    """Show full chunk text and metadata by chunk ID."""
    with SessionLocal() as db:
        chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
        if not chunk:
            console.print(f"[bold red]Chunk #{chunk_id} not found.[/bold red]")
            raise typer.Exit(1)

        meta = f"[bold cyan]Chunk #{chunk.id}[/bold cyan] | Chapter {chunk.chapter_no} | Pages {chunk.page_start}-{chunk.page_end} | Type: {chunk.content_type} | Tokens: {chunk.token_count}\nHeading: [yellow]{chunk.section_heading}[/yellow]"
        console.print(Panel(chunk.text, title=meta, expand=False))

@chunks_app.command("report")
def cli_chunks_report(
    chapter: Optional[int] = typer.Option(None, "--chapter", "-c", help="Specific chapter number, or all if omitted"),
    reports_dir: str = typer.Option("../reports", "--out-dir", "-o", help="Output directory for markdown reports"),
):
    """Generate chunk QA report and verify quality gate criteria."""
    out_path = Path(reports_dir).resolve()
    with SessionLocal() as db:
        if chapter is not None:
            chapters = [chapter]
        else:
            docs = db.query(Document).order_by(Document.chapter_no).all()
            chapters = [d.chapter_no for d in docs]

        if not chapters:
            console.print("[yellow]No documents found in database. Ingest first using 'ingest' command.[/yellow]")
            return

        for ch_no in chapters:
            try:
                rep = generate_qa_report(ch_no, db, out_dir=out_path)
                gate = rep["gate"]
                status_color = "green" if gate["passed"] else "red"
                status_txt = "PASSED" if gate["passed"] else "FAILED"

                console.print(f"\n[bold {status_color}]=== QA Report: Chapter {ch_no} ({rep['chapter_title']}) — Gate: {status_txt} ===[/bold {status_color}]")
                console.print(f"- Chunks: {rep['total_chunks']} | Pages: {rep['total_pages']} | Coverage: {rep['page_coverage_pct']}%")
                console.print(f"- Tokens: Min {rep['token_stats']['min']}, Max {rep['token_stats']['max']}, Avg {rep['token_stats']['avg']}")
                console.print(f"- Histogram: {rep['token_stats']['histogram']}")
                console.print(f"- Content Types: {rep['content_types']}")
                console.print(f"- Anomalies: <40 tokens: {rep['anomalies']['under_40_count']} ({rep['anomalies']['under_40_pct']}%), >480 tokens: {rep['anomalies']['over_max_count']}, Garbled: {rep['anomalies']['garbled_count']}")
                if rep["near_duplicates"]:
                    console.print(f"[yellow]- Near Duplicates (>0.97): {len(rep['near_duplicates'])} pairs found[/yellow]")
                console.print(f"[dim]Written detailed report to {out_path / f'chunks_ch{ch_no:02d}.md'}[/dim]")
            except Exception as e:
                console.print(f"[red]Error generating report for chapter {ch_no}:[/red] {e}")

@chunks_app.command("export")
def cli_chunks_export(
    out: str = typer.Option("chunks_dump.jsonl", "--out", "-o", help="Output JSONL file"),
    chapter: Optional[int] = typer.Option(None, "--chapter", "-c", help="Optional chapter filter"),
):
    """Dump chunks to a JSONL file for manual inspection."""
    out_path = Path(out).resolve()
    with SessionLocal() as db:
        query = db.query(Chunk)
        if chapter is not None:
            query = query.filter(Chunk.chapter_no == chapter)
        chunks = query.order_by(Chunk.id).all()

        with open(out_path, "w", encoding="utf-8") as f:
            for c in chunks:
                row = {
                    "id": c.id,
                    "chapter_no": c.chapter_no,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "section_heading": c.section_heading,
                    "content_type": c.content_type,
                    "token_count": c.token_count,
                    "text": c.text,
                }
                f.write(json.dumps(row) + "\n")
        console.print(f"[green][OK] Exported {len(chunks)} chunks to {out_path}[/green]")

# ----------------- SEARCH COMMAND -----------------
@app.command("search")
def cli_search(
    query: str = typer.Argument(..., help="Query string to search"),
    chapter: Optional[int] = typer.Option(None, "--chapter", "-c", help="Optional chapter filter"),
    k: int = typer.Option(5, "-k", help="Number of results to return"),
):
    """Search textbook chunks by cosine similarity using local BGE embeddings and pgvector."""
    console.print(f"[bold blue]Searching for:[/bold blue] '{query}' (top {k})")
    with SessionLocal() as db:
        hits = search_chunks(query, db, chapter_no=chapter, k=k)
        if not hits:
            console.print("[yellow]No matching chunks found.[/yellow]")
            return

        table = Table(title=f"Search Results for '{query}'")
        table.add_column("Score", style="bold green", width=8)
        table.add_column("Ch", justify="center", width=4)
        table.add_column("Pages", style="cyan", width=10)
        table.add_column("Type", style="magenta", width=10)
        table.add_column("Heading", style="yellow", width=25)
        table.add_column("Snippet", style="white")

        for h in hits:
            table.add_row(
                f"{h['score']:.4f}",
                str(h["chapter_no"]),
                h["pages"],
                h["content_type"],
                (h["section_heading"] or "")[:25],
                h["snippet"],
            )
        console.print(table)

# ----------------- EVAL RETRIEVAL COMMAND -----------------
@app.command("eval-retrieval")
def cli_eval_retrieval(
    eval_file: str = typer.Option("../data/eval/retrieval_queries.yaml", "--eval-file", "-f", help="Path to retrieval queries yaml"),
    k: int = typer.Option(3, "-k", help="Top-k chunks to inspect for hit"),
):
    """Run retrieval evaluation dataset against pgvector chunks and calculate hit-rate@k."""
    import yaml
    eval_path = Path(eval_file).resolve()
    if not eval_path.exists():
        console.print(f"[bold red]Evaluation file not found:[/bold red] {eval_path}")
        raise typer.Exit(1)

    with open(eval_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    queries = data.get("queries", [])
    if not queries:
        console.print("[yellow]No queries found in eval file.[/yellow]")
        return

    console.print(f"[bold blue]Evaluating {len(queries)} retrieval queries (hit-rate@{k})...[/bold blue]\n")

    hits_count = 0
    results_table = Table(title=f"Retrieval Evaluation Results (Hit@{k})")
    results_table.add_column("#", justify="right", width=3)
    results_table.add_column("Query", style="white", width=40)
    results_table.add_column("Expected", style="cyan", width=14)
    results_table.add_column("Top Match", style="magenta", width=16)
    results_table.add_column("Hit?", justify="center", width=6)

    misses = []

    with SessionLocal() as db:
        for idx, q_item in enumerate(queries, 1):
            q_text = q_item["query"]
            exp_ch = q_item["expected_chapter"]
            exp_pstart = q_item["page_start"]
            exp_pend = q_item["page_end"]

            retrieved = search_chunks(q_text, db, k=k)

            # Check if any chunk in top-k matches expected chapter and overlapping page range
            is_hit = False
            top_match_str = "None"
            if retrieved:
                top = retrieved[0]
                top_match_str = f"Ch {top['chapter_no']} ({top['pages']})"

            for h in retrieved:
                # h["pages"] format: "p.X-Y"
                if h["chapter_no"] == exp_ch:
                    pages_str = h["pages"].replace("p.", "")
                    try:
                        p_start_ret, p_end_ret = [int(p) for p in pages_str.split("-")]
                        # Check overlap: start <= end2 and end >= start2
                        if p_start_ret <= exp_pend and p_end_ret >= exp_pstart:
                            is_hit = True
                            break
                    except Exception:
                        pass

            if is_hit:
                hits_count += 1
                hit_disp = "[bold green]YES[/bold green]"
            else:
                hit_disp = "[bold red]NO[/bold red]"
                misses.append({
                    "index": idx,
                    "query": q_text,
                    "expected": f"Ch {exp_ch} (p.{exp_pstart}-{exp_pend})",
                    "retrieved": [f"Ch {h['chapter_no']} ({h['pages']}) score={h['score']:.3f}" for h in retrieved]
                })

            results_table.add_row(
                str(idx),
                q_text[:38] + ("..." if len(q_text) > 38 else ""),
                f"Ch {exp_ch} (p.{exp_pstart}-{exp_pend})",
                top_match_str,
                hit_disp
            )

    console.print(results_table)

    hit_rate = (hits_count / len(queries)) * 100
    gate_passed = hit_rate >= 90.0

    console.print(f"\n[bold]Total Queries:[/bold] {len(queries)}")
    console.print(f"[bold]Hits@{k}:[/bold] {hits_count}")
    console.print(f"[bold]Hit Rate@{k}:[/bold] [bold {'green' if gate_passed else 'red'}]{hit_rate:.1f}%[/bold {'green' if gate_passed else 'red'}]")

    if misses:
        console.print("\n[bold yellow]Misses Detail:[/bold yellow]")
        for m in misses:
            console.print(f"- #{m['index']} '{m['query']}'")
            console.print(f"  Expected: {m['expected']}")
            console.print(f"  Retrieved: {', '.join(m['retrieved'])}")

    if gate_passed:
        console.print(f"\n[bold green][OK] QUALITY GATE PASSED: Hit-rate@{k} ({hit_rate:.1f}%) >= 90%[/bold green]")
    else:
        console.print(f"\n[bold red][FAIL] QUALITY GATE FAILED: Hit-rate@{k} ({hit_rate:.1f}%) < 90%[/bold red]")
        raise typer.Exit(1)

# ----------------- GENERATE COMMAND -----------------
def render_paper_markdown(config: Any, questions: List[Dict[str, Any]], report: Dict[str, Any]) -> str:
    """Format generated question paper and answer key as clean Markdown."""
    header = getattr(config, "header", None)
    school = getattr(header, "school_name", "") or "Edukonic Model School"
    exam = getattr(header, "exam_name", "") or config.title
    duration = getattr(header, "duration", "1 Hour")
    total_marks = report.get("total_marks", 25)

    md = []
    md.append(f"# {school}")
    md.append(f"### {exam}")
    md.append(f"**Class:** {config.class_num} | **Subject:** {config.subject} | **Time:** {duration} | **Max Marks:** {total_marks}\n")
    md.append("---\n")
    md.append("### General Instructions:")
    if header and getattr(header, "instructions", None):
        for ins in header.instructions:
            md.append(f"- {ins}")
    else:
        md.append("- All questions are compulsory.")
    md.append("\n---\n")

    # Group questions by section
    sections_seen = []
    sec_map: Dict[str, List[Dict[str, Any]]] = {}
    for q in questions:
        sec = q.get("section", "A")
        if sec not in sec_map:
            sec_map[sec] = []
            sections_seen.append(sec)
        sec_map[sec].append(q)

    for sec in sections_seen:
        sec_qs = sec_map[sec]
        m_each = sec_qs[0].get("marks", 1) if sec_qs else 1
        md.append(f"## Section {sec} ({m_each} Mark{'s' if m_each > 1 else ''} each)\n")

        for q in sec_qs:
            c = q.get("content", {})
            slot = q.get("slot_no", 1)
            stem = c.get("stem", "")
            marks = q.get("marks", 1)
            q_type = q.get("type", "mcq")
            diff = q.get("difficulty", "medium")
            comp = "Competency" if q.get("competency") else "Standard"
            src = c.get("source", {})
            pages = src.get("pages", [])
            page_str = f"p.{min(pages)}-{max(pages)}" if pages else "p.NCERT"

            md.append(f"**Q{slot}.** {stem}  `[{marks} Mark{'s' if marks > 1 else ''}]`")
            md.append(f"*(Chapter {q.get('chapter_no')} · {q_type.upper()} · {diff.capitalize()} · {comp} · Source: {page_str})*\n")

            # MCQ Options
            options = c.get("options")
            if options and isinstance(options, list):
                labels = ["(A)", "(B)", "(C)", "(D)"]
                for i, opt in enumerate(options):
                    lbl = labels[i] if i < len(labels) else f"({i+1})"
                    md.append(f"- **{lbl}** {opt}")
                md.append("")

            # Case sub-questions
            sub_qs = c.get("sub_questions")
            if sub_qs and isinstance(sub_qs, list):
                for i, sq in enumerate(sub_qs, 1):
                    md.append(f"  ({i}) {sq.get('stem', '')} `[{sq.get('marks', 1)} Mark]`")
                md.append("")

            # Answer & Marking Scheme
            ans = c.get("answer", "")
            corr = c.get("correct_option", "")
            corr_str = f"**Correct Option: ({corr})** — " if corr else ""
            md.append(f"> **Model Answer:** {corr_str}{ans}\n>")

            ms = c.get("marking_scheme")
            if ms and isinstance(ms, list):
                md.append("> **Marking Scheme:**")
                for step in ms:
                    md.append(f"> - {step.get('step', '')}: *{step.get('marks', 1)} Mark*")
            md.append("\n---\n")

    # Blueprint Summary
    md.append("## Blueprint Summary Report\n")
    md.append(f"- **Total Marks:** {report.get('total_marks')} / Configured")
    md.append(f"- **Questions Generated:** {report.get('question_count')}")
    md.append(f"- **Marks by Chapter:** {report.get('marks_by_chapter')}")
    md.append(f"- **Questions by Type:** {report.get('count_by_type')}")
    md.append(f"- **Difficulty Breakdown:** {report.get('difficulty_split')}")
    md.append(f"- **Competency Focus:** {report.get('competency_count')} questions ({report.get('competency_percent')}%)")
    md.append(f"- **Flagged for Review:** {report.get('flagged_count')}")

    return "\n".join(md)

@app.command("generate")
def cli_generate(
    config: str = typer.Option("../configs/unit_test_25.json", "--config", "-c", help="Path to paper config JSON"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Optional output path for rendered Markdown paper"),
):
    """Generate a complete CBSE question paper from blueprint config using RAG and Gemini."""
    from app.schemas import PaperConfig
    from app.services.generator import generate_paper_pipeline
    from app.models import Paper, PaperQuestion

    cfg_path = Path(config).resolve()
    if not cfg_path.exists():
        console.print(f"[bold red]Config file not found:[/bold red] {cfg_path}")
        raise typer.Exit(1)

    with open(cfg_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    try:
        paper_cfg = PaperConfig(**data)
    except Exception as e:
        console.print(f"[bold red]Invalid paper configuration:[/bold red] {e}")
        raise typer.Exit(1)

    console.print(f"\n[bold blue]=== Starting Paper Generation: {paper_cfg.title} ===[/bold blue]")
    console.print(f"Total Marks: {paper_cfg.total_marks or 'Auto'} | Sections: {len(paper_cfg.sections)} | Chapters: {[ch.chapter_no for ch in paper_cfg.chapters]}")

    def progress_logger(pct: int, msg: str):
        console.print(f"[{pct}%] {msg}")

    from app.services.llm import GeminiDailyQuotaError

    with SessionLocal() as db:
        try:
            questions, report = generate_paper_pipeline(paper_cfg, db, progress_callback=progress_logger)
        except GeminiDailyQuotaError as e:
            console.print(f"\n[bold red][ERROR] {e}[/bold red]")
            raise typer.Exit(1)

        llm_usage = report.get("llm_usage", {})
        data["llm_usage"] = llm_usage
        data["blueprint_report"] = report

        # Save to database
        db_paper = Paper(
            title=paper_cfg.title,
            config=data,
            status="ready",
            progress=100,
            error=None
        )
        db.add(db_paper)
        db.commit()
        db.refresh(db_paper)

        for q in questions:
            pq = PaperQuestion(
                paper_id=db_paper.id,
                slot_no=q["slot_no"],
                section=q["section"],
                type=q["type"],
                marks=q["marks"],
                chapter_no=q["chapter_no"],
                topic=q["topic"],
                difficulty=q["difficulty"],
                competency=q["competency"],
                bloom=q["bloom"],
                content=q["content"],
                source_chunk_ids=q["source_chunk_ids"],
                validation=q["validation"],
                status=q["status"],
                embedding=q["embedding"]
            )
            db.add(pq)
        db.commit()

        console.print(f"\n[bold green][OK] Paper #{db_paper.id} saved to database![/bold green]")

        # Print prominent Gemini API call and token usage
        calls = llm_usage.get("calls", 0)
        prompt_tok = llm_usage.get("prompt_tokens", 0)
        comp_tok = llm_usage.get("completion_tokens", 0)
        tot_tok = llm_usage.get("total_tokens", 0)
        cache_hits = llm_usage.get("cache_hits", 0)

        console.print(
            f"[bold cyan]Gemini API Usage:[/bold cyan] "
            f"[yellow]{calls}[/yellow] calls ([green]{cache_hits}[/green] cache hits) | "
            f"[yellow]{prompt_tok:,}[/yellow] prompt tokens | "
            f"[yellow]{comp_tok:,}[/yellow] completion tokens | "
            f"[bold green]{tot_tok:,}[/bold green] total tokens"
        )

        # Render Markdown
        md_text = render_paper_markdown(paper_cfg, questions, report)

        if out:
            out_file = Path(out).resolve()
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(md_text)
            console.print(f"[bold green][OK] Rendered Markdown paper written to:[/bold green] {out_file}")

        # Blueprint report table
        rep_table = Table(title="Generated Paper Blueprint Report")
        rep_table.add_column("Metric", style="cyan", width=25)
        rep_table.add_column("Value", style="magenta")

        rep_table.add_row("Paper ID", str(db_paper.id))
        rep_table.add_row("Total Marks", f"{report['total_marks']}")
        rep_table.add_row("Total Questions", f"{report['question_count']}")
        rep_table.add_row("Marks by Chapter", str(report["marks_by_chapter"]))
        rep_table.add_row("Questions by Type", str(report["count_by_type"]))
        rep_table.add_row("Difficulty Split", str(report["difficulty_split"]))
        rep_table.add_row("Competency Count", f"{report['competency_count']} ({report['competency_percent']}%)")
        rep_table.add_row("Flagged Questions", str(report["flagged_count"]))
        rep_table.add_row("Gemini API Calls", f"{calls} calls ({cache_hits} cache hits)")
        rep_table.add_row("Gemini Tokens", f"{tot_tok:,} total ({prompt_tok:,} prompt, {comp_tok:,} comp)")

        console.print(rep_table)

# ----------------- PAPERS COMMANDS -----------------
@papers_app.command("export-key")
def cli_papers_export_key(
    paper_id: int = typer.Argument(..., help="ID of the paper to export answer key for"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Output DOCX file path"),
):
    """Export the Answer Key and Marking Scheme for a paper to a DOCX file."""
    from app.models import Paper
    from app.services.exporter import export_answer_key_docx

    with SessionLocal() as db:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if not paper:
            console.print(f"[bold red]Error: Paper #{paper_id} not found in database.[/bold red]")
            raise typer.Exit(1)

        questions_data = [
            {
                "id": q.id,
                "slot_no": q.slot_no,
                "section": q.section,
                "type": q.type,
                "marks": q.marks,
                "chapter_no": q.chapter_no,
                "content": q.content,
            }
            for q in sorted(paper.questions, key=lambda x: x.slot_no)
        ]

        paper_dict = {
            "id": paper.id,
            "title": paper.title,
            "config": paper.config
        }

        stream = export_answer_key_docx(paper_dict, questions_data)
        out_path = Path(out or f"reports/key_{paper_id}.docx").resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(stream.getvalue())

        console.print(f"[bold green][OK] Answer key for Paper #{paper_id} exported to:[/bold green] {out_path}")

@papers_app.command("export-paper")
def cli_papers_export_paper(
    paper_id: int = typer.Argument(..., help="ID of the paper to export question paper for"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Output DOCX file path"),
):
    """Export the Question Paper to a DOCX file."""
    from app.models import Paper
    from app.services.exporter import export_paper_docx

    with SessionLocal() as db:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if not paper:
            console.print(f"[bold red]Error: Paper #{paper_id} not found in database.[/bold red]")
            raise typer.Exit(1)

        questions_data = [
            {
                "id": q.id,
                "slot_no": q.slot_no,
                "section": q.section,
                "type": q.type,
                "marks": q.marks,
                "chapter_no": q.chapter_no,
                "content": q.content,
            }
            for q in sorted(paper.questions, key=lambda x: x.slot_no)
        ]

        paper_dict = {
            "id": paper.id,
            "title": paper.title,
            "config": paper.config
        }

        stream = export_paper_docx(paper_dict, questions_data)
        out_path = Path(out or f"reports/paper_{paper_id}.docx").resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(stream.getvalue())

        console.print(f"[bold green][OK] Question paper #{paper_id} exported to:[/bold green] {out_path}")

if __name__ == "__main__":
    app()


