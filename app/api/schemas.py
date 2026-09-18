"""Pydantic request/response schemas."""

from typing import List, Optional

from pydantic import BaseModel


class KBCreate(BaseModel):
    name: str
    description: str = ""


class ConversationCreate(BaseModel):
    kb_id: str
    title: Optional[str] = "New conversation"


class ChatRequest(BaseModel):
    kb_id: str
    conversation_id: str
    message: str


class FeedbackRequest(BaseModel):
    message_id: str
    rating: str  # "up" | "down"
    reason: str = ""


class SuggestRequest(BaseModel):
    document_id: str
