from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Determine project and env path
BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent
ENV_FILE = REPO_ROOT / ".env" if (REPO_ROOT / ".env").exists() else BASE_DIR / ".env"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Database
    POSTGRES_USER: str = "edukonic"
    POSTGRES_PASSWORD: str = "edukonic"
    POSTGRES_DB: str = "edukonic"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = "postgresql+psycopg://edukonic:edukonic@localhost:5432/edukonic"

    # LLM & Generation
    GEMINI_API_KEY: str = ""
    GEN_MODEL: str = "gemini-2.5-flash"
    VALIDATE_MODEL: str = "gemini-2.5-flash"

    # Embeddings (local sentence-transformers or gemini)
    EMBED_PROVIDER: str = "local"  # "local" | "gemini"
    EMBED_MODEL: str = "BAAI/bge-base-en-v1.5"
    EMBED_DIM: int = 768
    EMBED_BATCH_SIZE: int = 32

    LLM_CONCURRENCY: int = 2
    LLM_MAX_RETRIES: int = 6

    # Chunking
    CHUNK_TARGET_TOKENS: int = 350
    CHUNK_MAX_TOKENS: int = 480
    CHUNK_OVERLAP_TOKENS: int = 40

    # Generation & Retrieval
    DEDUPE_THRESHOLD: float = 0.85
    RETRIEVAL_NEIGHBORS: int = 3

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173"
    APP_PASSWORD: str = "change-me"

settings = Settings()
