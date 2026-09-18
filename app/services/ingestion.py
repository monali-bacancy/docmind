"""
Ingestion pipeline + document state machine (Sections 5, 6, 45, 46).

Runs in a background thread so the upload HTTP request returns immediately.
Progresses the document through: UPLOADED -> PARSED -> CHUNKED -> EMBEDDING
-> INDEXED -> READY (or FAILED with an error message). Idempotent per document:
re-processing first clears any existing vectors/chunks for that document.
"""

import time
from concurrent.futures import ThreadPoolExecutor

from app.core.logging import log_event
from app.core.state import DocStatus
from app.db import database as db
from app.services import parser
from app.services.chunker import chunk_pages
from app.services.vector_store import get_vector_store

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ingest")


def enqueue(document_id: str) -> None:
    """Schedule background processing for a document."""
    _executor.submit(_safe_process, document_id)


def _safe_process(document_id: str) -> None:
    try:
        _process(document_id)
    except Exception as exc:  # noqa: BLE001 — record failure, never crash the worker
        log_event("ingest.failed", document_id=document_id, error=str(exc))
        db.update_document(
            document_id,
            status=DocStatus.FAILED.value,
            error_message=str(exc)[:500],
            processing_completed_at=time.time(),
        )


def _process(document_id: str) -> None:
    doc = db.get_document(document_id)
    if not doc:
        return

    started = time.time()
    db.update_document(
        document_id,
        status=DocStatus.PROCESSING.value,
        error_message="",
        processing_started_at=started,
    )
    log_event("ingest.start", document_id=document_id, name=doc["name"])

    # Idempotency: clear any prior vectors for this document before re-indexing.
    store = get_vector_store()
    store.delete_document(document_id)

    ext = "." + doc["name"].rsplit(".", 1)[-1].lower()

    # 1) Parse -------------------------------------------------------------
    pages = parser.parse(doc["storage_path"], ext)
    if not pages:
        raise ValueError("No extractable text found in the document.")
    db.update_document(document_id, status=DocStatus.PARSED.value, pages=len(pages))

    # 2) Clean + chunk -----------------------------------------------------
    chunks = chunk_pages(pages)
    if not chunks:
        raise ValueError("Document produced no chunks after cleaning.")
    db.update_document(document_id, status=DocStatus.CHUNKED.value, chunks=len(chunks))

    # 3) Embed -------------------------------------------------------------
    db.update_document(document_id, status=DocStatus.EMBEDDING.value)
    ids, texts, metas = [], [], []
    for c in chunks:
        chunk_id = f"{document_id}:{c.chunk_index}"
        ids.append(chunk_id)
        texts.append(c.content)
        metas.append(
            {
                "kb_id": doc["kb_id"],
                "document_id": document_id,
                "document_name": doc["name"],
                "chunk_index": c.chunk_index,
                "page_number": c.page_number,
                "section": c.section or "",
            }
        )
        db.insert_chunk(
            chunk_id, document_id, doc["kb_id"], c.chunk_index,
            c.page_number, c.section or "", c.token_count, c.content,
        )

    # 4) Index (store vectors) --------------------------------------------
    store.add(ids, texts, metas)
    db.update_document(document_id, status=DocStatus.INDEXED.value)
    db.log_ai_usage(document_id, store.embedder.name, store.embedder.model, "embedding", len(texts))

    # 5) Ready -------------------------------------------------------------
    duration_ms = int((time.time() - started) * 1000)
    db.update_document(
        document_id,
        status=DocStatus.READY.value,
        processing_completed_at=time.time(),
        processing_duration_ms=duration_ms,
    )
    log_event(
        "ingest.ready",
        document_id=document_id,
        pages=len(pages),
        chunks=len(chunks),
        duration_ms=duration_ms,
    )
