"""Knowledge base endpoints (Section 38)."""

from fastapi import APIRouter, HTTPException

from app.api.schemas import KBCreate
from app.db import database as db

router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["knowledge-bases"])


@router.get("")
def list_kbs():
    return {"knowledge_bases": db.list_kbs()}


@router.post("")
def create_kb(body: KBCreate):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    return db.create_kb(name, body.description.strip())


@router.get("/{kb_id}")
def get_kb(kb_id: str):
    kb = db.get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    kb["documents"] = db.list_documents(kb_id)
    return kb


@router.delete("/{kb_id}")
def delete_kb(kb_id: str):
    # Remove vectors for each document in the KB first.
    from app.services.vector_store import get_vector_store

    store = get_vector_store()
    for doc in db.list_documents(kb_id):
        store.delete_document(doc["id"])
    if not db.delete_kb(kb_id):
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    return {"deleted": kb_id}
