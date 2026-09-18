"""Application settings, loaded from environment / .env at the project root."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    # --- Secrets / provider ---
    GOOGLE_API_KEY: str = os.environ.get("GOOGLE_API_KEY", "")
    AI_PROVIDER: str = os.environ.get("AI_PROVIDER", "gemini")
    CHAT_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
    EMBED_MODEL: str = os.environ.get("GEMINI_EMBED_MODEL", "")  # auto-detected if empty

    # --- Storage paths ---
    STORAGE_DIR: Path = PROJECT_ROOT / "storage"
    UPLOAD_DIR: Path = STORAGE_DIR / "uploads"
    CHROMA_DIR: Path = STORAGE_DIR / "chroma"
    DB_PATH: Path = STORAGE_DIR / "docmind.sqlite3"
    FRONTEND_DIR: Path = PROJECT_ROOT / "frontend"

    # --- Upload validation ---
    UPLOAD_MAX_SIZE_MB: int = int(os.environ.get("UPLOAD_MAX_SIZE_MB", "25"))
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}

    # --- Chunking ---
    CHUNK_SIZE: int = int(os.environ.get("CHUNK_SIZE", "900"))       # ~chars
    CHUNK_OVERLAP: int = int(os.environ.get("CHUNK_OVERLAP", "150"))

    # --- Retrieval ---
    VECTOR_TOP_K: int = int(os.environ.get("VECTOR_TOP_K", "8"))
    CONTEXT_TOP_K: int = int(os.environ.get("CONTEXT_TOP_K", "4"))
    MIN_SIMILARITY: float = float(os.environ.get("MIN_SIMILARITY", "0.28"))

    # --- Prompt version (for observability) ---
    PROMPT_VERSION: str = "v1"

    def ensure_dirs(self) -> None:
        for d in (self.STORAGE_DIR, self.UPLOAD_DIR, self.CHROMA_DIR):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
