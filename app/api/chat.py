"""Chat + conversation endpoints, including the streaming SSE answer (Sections 26, 28, 39)."""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatRequest, ConversationCreate
from app.core.logging import new_request_id
from app.db import database as db
from app.services import chat as chat_service

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/conversations")
def create_conversation(body: ConversationCreate):
    if not db.get_kb(body.kb_id):
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    return db.create_conversation(body.kb_id, body.title or "New conversation")


@router.get("/knowledge-bases/{kb_id}/conversations")
def list_conversations(kb_id: str):
    return {"conversations": db.list_conversations(kb_id)}


@router.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: str):
    msgs = db.list_messages(conversation_id)
    for m in msgs:
        m["sources"] = json.loads(m.get("sources") or "[]")
    return {"messages": msgs}


@router.post("/chat")
def chat(body: ChatRequest):
    if not db.get_kb(body.kb_id):
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message is required.")

    new_request_id()

    def event_stream():
        for event in chat_service.answer_stream(
            body.kb_id, body.conversation_id, body.message.strip()
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
