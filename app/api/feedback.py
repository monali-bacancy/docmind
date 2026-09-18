"""Feedback + admin/observability endpoints (Sections 29, 32, 33)."""

from fastapi import APIRouter, HTTPException

from app.api.schemas import FeedbackRequest
from app.db import database as db

router = APIRouter(prefix="/api/v1", tags=["feedback-admin"])


@router.post("/feedback")
def submit_feedback(body: FeedbackRequest):
    if body.rating not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'.")
    return db.add_feedback(body.message_id, body.rating, body.reason)


@router.get("/admin/metrics")
def metrics():
    return db.admin_metrics()


@router.get("/admin/logs")
def logs():
    return {"logs": db.recent_retrieval_logs()}
