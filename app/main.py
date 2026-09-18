"""
DocMind - Smart RAG Chatbot — FastAPI application entrypoint.

Wires the API routers, serves the frontend, exposes health/readiness checks,
and seeds a default knowledge base on first run.

Run:  bash run.sh   (or)   python3 -m uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import chat, documents, feedback, knowledge_bases
from app.core.config import settings
from app.core.logging import setup_logging
from app.db import database as db

setup_logging()

app = FastAPI(title="DocMind - Smart RAG Chatbot", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    db.init_db()
    # Seed a default knowledge base so the app is usable immediately.
    if not db.list_kbs():
        db.create_kb("My First Knowledge Base", "Upload documents and start asking questions.")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    checks = {"database": False, "vector_store": False}
    try:
        db.get_conn().execute("SELECT 1")
        checks["database"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services.vector_store import get_vector_store

        get_vector_store()
        checks["vector_store"] = True
    except Exception:  # noqa: BLE001
        pass
    status = "ok" if all(checks.values()) else "degraded"
    return {"status": status, "checks": checks}


# API routers
app.include_router(knowledge_bases.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(feedback.router)

# Static frontend
app.mount("/static", StaticFiles(directory=str(settings.FRONTEND_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(settings.FRONTEND_DIR / "index.html"))
