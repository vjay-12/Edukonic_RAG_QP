from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

app = FastAPI(
    title="Edukonic RAG QP API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json"
)

# Configure CORS
origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "app": "Edukonic_RAG_QP",
        "embed_provider": settings.EMBED_PROVIDER,
        "embed_model": settings.EMBED_MODEL,
        "embed_dim": settings.EMBED_DIM
    }

@app.get("/")
def root():
    return {"message": "Edukonic RAG QP API is running. See /api/docs"}
