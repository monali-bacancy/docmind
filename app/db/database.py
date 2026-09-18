"""
SQLite persistence layer.

Holds all relational metadata: knowledge bases, documents (+ processing state),
chunk records, conversations, messages, feedback, and observability logs
(retrieval + AI usage). Vectors live in Chroma; everything else lives here.

A single module-level connection is shared (WAL mode + a write lock) which is
plenty for a single-process app.
"""

import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from app.core.config import settings

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _connect()
    return _conn


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _execute(sql: str, params: tuple = ()) -> None:
    with _lock:
        conn = get_conn()
        conn.execute(sql, params)
        conn.commit()


def _query(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with _lock:
        conn = get_conn()
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def _query_one(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    rows = _query(sql, params)
    return rows[0] if rows else None


SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    name TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    mime_type TEXT,
    file_size INTEGER,
    pages INTEGER DEFAULT 0,
    chunks INTEGER DEFAULT 0,
    status TEXT NOT NULL,
    error_message TEXT DEFAULT '',
    processing_started_at REAL,
    processing_completed_at REAL,
    processing_duration_ms INTEGER,
    created_at REAL NOT NULL,
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    kb_id TEXT NOT NULL,
    chunk_index INTEGER,
    page_number INTEGER,
    section TEXT,
    token_count INTEGER,
    content TEXT,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    title TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    sources TEXT DEFAULT '[]',
    created_at REAL NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    rating TEXT NOT NULL,
    reason TEXT DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS retrieval_logs (
    id TEXT PRIMARY KEY,
    request_id TEXT,
    message_id TEXT,
    kb_id TEXT,
    query TEXT,
    retrieval_count INTEGER,
    top_score REAL,
    retrieval_latency_ms INTEGER,
    generation_latency_ms INTEGER,
    total_latency_ms INTEGER,
    status TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_usage_logs (
    id TEXT PRIMARY KEY,
    message_id TEXT,
    provider TEXT,
    model TEXT,
    operation TEXT,
    units INTEGER,
    created_at REAL NOT NULL
);
"""


def init_db() -> None:
    with _lock:
        conn = get_conn()
        conn.executescript(SCHEMA)
        conn.commit()


# --------------------------------------------------------------------------
# Knowledge bases
# --------------------------------------------------------------------------
def create_kb(name: str, description: str = "") -> Dict[str, Any]:
    kb_id = new_id("kb")
    _execute(
        "INSERT INTO knowledge_bases (id, name, description, created_at) VALUES (?,?,?,?)",
        (kb_id, name, description, time.time()),
    )
    return get_kb(kb_id)


def get_kb(kb_id: str) -> Optional[Dict[str, Any]]:
    return _query_one("SELECT * FROM knowledge_bases WHERE id=?", (kb_id,))


def list_kbs() -> List[Dict[str, Any]]:
    kbs = _query("SELECT * FROM knowledge_bases ORDER BY created_at DESC")
    for kb in kbs:
        counts = _query_one(
            "SELECT COUNT(*) AS docs, COALESCE(SUM(chunks),0) AS chunks "
            "FROM documents WHERE kb_id=?",
            (kb["id"],),
        )
        kb["doc_count"] = counts["docs"]
        kb["chunk_count"] = counts["chunks"]
    return kbs


def delete_kb(kb_id: str) -> bool:
    if not get_kb(kb_id):
        return False
    _execute("DELETE FROM knowledge_bases WHERE id=?", (kb_id,))
    return True


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------
def create_document(kb_id: str, name: str, storage_path: str, mime_type: str,
                    file_size: int, status: str) -> Dict[str, Any]:
    doc_id = new_id("doc")
    _execute(
        "INSERT INTO documents (id, kb_id, name, storage_path, mime_type, file_size, "
        "status, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (doc_id, kb_id, name, storage_path, mime_type, file_size, status, time.time()),
    )
    return get_document(doc_id)


def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    return _query_one("SELECT * FROM documents WHERE id=?", (doc_id,))


def list_documents(kb_id: str) -> List[Dict[str, Any]]:
    return _query(
        "SELECT * FROM documents WHERE kb_id=? ORDER BY created_at DESC", (kb_id,)
    )


def update_document(doc_id: str, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    _execute(f"UPDATE documents SET {cols} WHERE id=?", (*fields.values(), doc_id))


def delete_document(doc_id: str) -> bool:
    if not get_document(doc_id):
        return False
    _execute("DELETE FROM documents WHERE id=?", (doc_id,))
    return True


# --------------------------------------------------------------------------
# Chunks
# --------------------------------------------------------------------------
def insert_chunk(chunk_id: str, document_id: str, kb_id: str, chunk_index: int,
                 page_number: int, section: str, token_count: int, content: str) -> None:
    _execute(
        "INSERT OR REPLACE INTO chunks (id, document_id, kb_id, chunk_index, "
        "page_number, section, token_count, content) VALUES (?,?,?,?,?,?,?,?)",
        (chunk_id, document_id, kb_id, chunk_index, page_number, section, token_count, content),
    )


def get_chunk(chunk_id: str) -> Optional[Dict[str, Any]]:
    return _query_one("SELECT * FROM chunks WHERE id=?", (chunk_id,))


# --------------------------------------------------------------------------
# Conversations & messages
# --------------------------------------------------------------------------
def create_conversation(kb_id: str, title: str) -> Dict[str, Any]:
    conv_id = new_id("conv")
    _execute(
        "INSERT INTO conversations (id, kb_id, title, created_at) VALUES (?,?,?,?)",
        (conv_id, kb_id, title, time.time()),
    )
    return _query_one("SELECT * FROM conversations WHERE id=?", (conv_id,))


def list_conversations(kb_id: str) -> List[Dict[str, Any]]:
    return _query(
        "SELECT * FROM conversations WHERE kb_id=? ORDER BY created_at DESC", (kb_id,)
    )


def add_message(conversation_id: str, role: str, content: str, sources: str = "[]") -> Dict[str, Any]:
    msg_id = new_id("msg")
    _execute(
        "INSERT INTO messages (id, conversation_id, role, content, sources, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (msg_id, conversation_id, role, content, sources, time.time()),
    )
    return _query_one("SELECT * FROM messages WHERE id=?", (msg_id,))


def list_messages(conversation_id: str) -> List[Dict[str, Any]]:
    return _query(
        "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC",
        (conversation_id,),
    )


def update_message(message_id: str, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    _execute(f"UPDATE messages SET {cols} WHERE id=?", (*fields.values(), message_id))


# --------------------------------------------------------------------------
# Feedback
# --------------------------------------------------------------------------
def add_feedback(message_id: str, rating: str, reason: str = "") -> Dict[str, Any]:
    fb_id = new_id("fb")
    _execute(
        "INSERT INTO feedback (id, message_id, rating, reason, created_at) VALUES (?,?,?,?,?)",
        (fb_id, message_id, rating, reason, time.time()),
    )
    return _query_one("SELECT * FROM feedback WHERE id=?", (fb_id,))


# --------------------------------------------------------------------------
# Observability logs
# --------------------------------------------------------------------------
def log_retrieval(**fields) -> None:
    fields.setdefault("id", new_id("rlog"))
    fields.setdefault("created_at", time.time())
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    _execute(f"INSERT INTO retrieval_logs ({cols}) VALUES ({placeholders})", tuple(fields.values()))


def log_ai_usage(message_id: str, provider: str, model: str, operation: str, units: int) -> None:
    _execute(
        "INSERT INTO ai_usage_logs (id, message_id, provider, model, operation, units, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (new_id("use"), message_id, provider, model, operation, units, time.time()),
    )


# --------------------------------------------------------------------------
# Admin metrics (Section 32)
# --------------------------------------------------------------------------
def admin_metrics() -> Dict[str, Any]:
    kb = _query_one("SELECT COUNT(*) AS n FROM knowledge_bases")["n"]
    docs = _query_one("SELECT COUNT(*) AS n FROM documents")["n"]
    ready = _query_one("SELECT COUNT(*) AS n FROM documents WHERE status='ready'")["n"]
    failed = _query_one("SELECT COUNT(*) AS n FROM documents WHERE status='failed'")["n"]
    chunks = _query_one("SELECT COUNT(*) AS n FROM chunks")["n"]
    queries = _query_one("SELECT COUNT(*) AS n FROM retrieval_logs")["n"]
    latency = _query_one(
        "SELECT AVG(retrieval_latency_ms) AS r, AVG(generation_latency_ms) AS g, "
        "AVG(total_latency_ms) AS t FROM retrieval_logs"
    )
    fb = _query_one(
        "SELECT SUM(rating='up') AS up, SUM(rating='down') AS down FROM feedback"
    )
    return {
        "knowledge_bases": kb,
        "documents": docs,
        "documents_ready": ready,
        "documents_failed": failed,
        "chunks": chunks,
        "queries": queries,
        "avg_retrieval_ms": round(latency["r"] or 0, 1),
        "avg_generation_ms": round(latency["g"] or 0, 1),
        "avg_total_ms": round(latency["t"] or 0, 1),
        "feedback_up": fb["up"] or 0,
        "feedback_down": fb["down"] or 0,
    }


def recent_retrieval_logs(limit: int = 15) -> List[Dict[str, Any]]:
    return _query(
        "SELECT request_id, kb_id, query, retrieval_count, top_score, "
        "retrieval_latency_ms, generation_latency_ms, total_latency_ms, status, created_at "
        "FROM retrieval_logs ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
