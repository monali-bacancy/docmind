"""Document endpoints: upload (queued), status, list, delete, reprocess (Sections 5, 58)."""

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import settings
from app.core.state import PIPELINE_ORDER, DocStatus
from app.db import database as db
from app.services import ingestion
from app.services.chat import suggest_questions
from app.services.validation import ValidationError, validate_upload

router = APIRouter(prefix="/api/v1", tags=["documents"])


@router.post("/knowledge-bases/{kb_id}/documents")
async def upload_document(kb_id: str, file: UploadFile = File(...)):
    kb = db.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")

    data = await file.read()
    try:
        ext = validate_upload(file.filename, data)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Store under a generated path (never trust the original filename).
    doc = db.create_document(
        kb_id=kb_id,
        name=file.filename,
        storage_path="",  # set below once we have the id
        mime_type=file.content_type or "",
        file_size=len(data),
        status=DocStatus.UPLOADED.value,
    )
    dest_dir = settings.UPLOAD_DIR / doc["id"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"original{ext}"
    dest.write_bytes(data)
    db.update_document(doc["id"], storage_path=str(dest))

    # Queue processing; return immediately (Section 5).
    ingestion.enqueue(doc["id"])
    return {"id": doc["id"], "status": DocStatus.UPLOADED.value,
            "message": "Document uploaded and queued for processing."}


@router.get("/documents/{doc_id}")
def get_document(doc_id: str):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    # Attach the pipeline step list so the UI can render progress.
    doc["pipeline"] = [s.value for s in PIPELINE_ORDER]
    return doc


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    from app.services.vector_store import get_vector_store

    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    get_vector_store().delete_document(doc_id)
    db.delete_document(doc_id)
    return {"deleted": doc_id}


@router.post("/documents/{doc_id}/reprocess")
def reprocess_document(doc_id: str):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    db.update_document(doc_id, status=DocStatus.UPLOADED.value, error_message="")
    ingestion.enqueue(doc_id)
    return {"id": doc_id, "status": DocStatus.UPLOADED.value, "message": "Reprocessing queued."}


@router.post("/documents/{doc_id}/suggest")
def suggest_for_document(doc_id: str):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    # Use the first chunk as a sample for question suggestions.
    chunk = db._query_one(  # noqa: SLF001 — internal helper reuse
        "SELECT content FROM chunks WHERE document_id=? ORDER BY chunk_index LIMIT 1",
        (doc_id,),
    )
    sample = chunk["content"] if chunk else doc["name"]
    return {"suggestions": suggest_questions(doc["kb_id"], doc["name"], sample)}


@router.get("/chunks/{chunk_id}")
def get_chunk(chunk_id: str):
    """Source viewer (Section 25): fetch a full chunk by id."""
    chunk = db.get_chunk(chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found.")
    doc = db.get_document(chunk["document_id"])
    chunk["document_name"] = doc["name"] if doc else "unknown"
    return chunk
