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
    expose_headers=["Content-Disposition"],
)

# Include API Routers under /api
from app.api.auth import router as auth_router
from app.api.chapters import router as chapters_router
from app.api.blueprints import router as blueprints_router
from app.api.papers import router as papers_router
from app.api.bank import router as bank_router

app.include_router(auth_router, prefix="/api")
app.include_router(chapters_router, prefix="/api")
app.include_router(blueprints_router, prefix="/api")
app.include_router(papers_router, prefix="/api")
app.include_router(bank_router, prefix="/api")

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
