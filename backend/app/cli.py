import typer
from rich.console import Console
from rich.table import Table

console = Console()
app = typer.Typer(help="Edukonic RAG Question Paper Generator CLI")
db_app = typer.Typer(help="Database operations")
app.add_typer(db_app, name="db")

@db_app.command("init")
def db_init():
    """Create all database tables and enable vector extension."""
    from app.db import init_db, engine
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
    init_db()
    console.print("[bold green]Database tables and pgvector extension initialized successfully![/bold green]")

@db_app.command("reset")
def db_reset():
    """Drop and recreate all database tables."""
    from app.db import reset_db, engine
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
    reset_db()
    console.print("[bold yellow]Database tables reset and recreated successfully![/bold yellow]")

if __name__ == "__main__":
    app()
