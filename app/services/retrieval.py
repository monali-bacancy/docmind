"""Retrieval (Sections 16-18, 23): vector search filtered by KB, with a confidence gate."""

from dataclasses import dataclass
from typing import Dict, List

from app.core.config import settings
from app.services.vector_store import get_vector_store


@dataclass
class Retrieved:
    chunk_id: str
    document_id: str
    document_name: str
    page_number: int
    section: str
    content: str
    score: float


def retrieve(query: str, kb_id: str) -> List[Retrieved]:
    store = get_vector_store()
    raw = store.search(query, kb_id, k=settings.VECTOR_TOP_K)

    results: List[Retrieved] = []
    for meta, score in raw:
        results.append(
            Retrieved(
                chunk_id=meta.get("chunk_id", ""),
                document_id=meta.get("document_id", ""),
                document_name=meta.get("document_name", "unknown"),
                page_number=int(meta.get("page_number", 1)),
                section=meta.get("section", ""),
                content=meta.get("content", ""),
                score=score,
            )
        )

    # Keep only chunks above the confidence threshold, then take the top-N.
    confident = [r for r in results if r.score >= settings.MIN_SIMILARITY]
    confident.sort(key=lambda r: r.score, reverse=True)
    return confident[: settings.CONTEXT_TOP_K]


def has_confident_context(results: List[Retrieved]) -> bool:
    """Hallucination guard (Section 23): require at least one strong match."""
    return bool(results) and results[0].score >= settings.MIN_SIMILARITY
