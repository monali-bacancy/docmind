"""
Chat orchestrator (Section 62 ChatService): retrieval -> context -> generation
-> citations -> logging. Yields streaming events for the API layer.

Also provides suggested-question generation (Section 55 Feature D).
"""

import json
import time
from typing import Dict, Iterator, List

from app.core.config import settings
from app.core.logging import log_event, request_id_var
from app.db import database as db
from app.providers import get_llm_provider
from app.services.context_builder import build_context, system_prompt
from app.services.retrieval import has_confident_context, retrieve

GROUNDED_FALLBACK = "I couldn't find this information in the selected knowledge base."


def answer_stream(kb_id: str, conversation_id: str, question: str) -> Iterator[Dict]:
    """
    Yields events:
      {"type": "sources", "sources": [...], "message_id": "..."}
      {"type": "token", "text": "..."}
      {"type": "done", "message_id": "..."}
      {"type": "error", "message": "..."}
    """
    t0 = time.time()
    request_id = request_id_var.get()

    # Persist the user's message.
    db.add_message(conversation_id, "user", question)

    # 1) Retrieve -----------------------------------------------------------
    results = retrieve(question, kb_id)
    retrieval_ms = int((time.time() - t0) * 1000)
    context, sources = build_context(results)
    top_score = results[0].score if results else 0.0

    # Pre-create the assistant message so feedback can target it.
    assistant_msg = db.add_message(conversation_id, "assistant", "", json.dumps(sources))
    message_id = assistant_msg["id"]

    yield {"type": "sources", "sources": sources, "message_id": message_id}

    # 2) Confidence gate (hallucination guard) ------------------------------
    if not has_confident_context(results):
        for word in GROUNDED_FALLBACK.split(" "):
            yield {"type": "token", "text": word + " "}
        db.update_message(message_id, content=GROUNDED_FALLBACK)
        _log(request_id, message_id, kb_id, question, results, retrieval_ms, 0, t0, "no_context")
        yield {"type": "done", "message_id": message_id}
        return

    # 3) Generate (streamed) ------------------------------------------------
    history = _recent_history(conversation_id)
    messages = [{"role": "system", "content": system_prompt(context)}] + history
    messages.append({"role": "user", "content": question})

    gen_start = time.time()
    answer_parts: List[str] = []
    try:
        llm = get_llm_provider(temperature=0.2)
        for token in llm.stream(messages):
            answer_parts.append(token)
            yield {"type": "token", "text": token}
    except Exception as exc:  # noqa: BLE001
        log_event("chat.error", error=str(exc))
        yield {"type": "error", "message": str(exc)}
        db.update_message(message_id, content=f"[error] {exc}")
        return

    generation_ms = int((time.time() - gen_start) * 1000)
    answer = "".join(answer_parts).strip()
    db.update_message(message_id, content=answer)
    db.log_ai_usage(message_id, llm.name, llm.model, "generation", len(answer.split()))
    _log(request_id, message_id, kb_id, question, results, retrieval_ms, generation_ms, t0, "success")

    yield {"type": "done", "message_id": message_id}


def _recent_history(conversation_id: str, max_turns: int = 6) -> List[Dict]:
    msgs = db.list_messages(conversation_id)
    # Exclude the two we just added (the current user + empty assistant).
    prior = [m for m in msgs if m["content"]][-max_turns:]
    return [{"role": m["role"], "content": m["content"]} for m in prior]


def _log(request_id, message_id, kb_id, query, results, retrieval_ms, generation_ms, t0, status):
    total_ms = int((time.time() - t0) * 1000)
    db.log_retrieval(
        request_id=request_id,
        message_id=message_id,
        kb_id=kb_id,
        query=query,
        retrieval_count=len(results),
        top_score=round(results[0].score, 3) if results else 0.0,
        retrieval_latency_ms=retrieval_ms,
        generation_latency_ms=generation_ms,
        total_latency_ms=total_ms,
        status=status,
    )
    log_event(
        "rag_query",
        message_id=message_id,
        kb_id=kb_id,
        retrieval_count=len(results),
        retrieval_latency_ms=retrieval_ms,
        generation_latency_ms=generation_ms,
        total_latency_ms=total_ms,
        status=status,
        prompt_version=settings.PROMPT_VERSION,
    )


def suggest_questions(kb_id: str, document_name: str, sample_text: str) -> List[str]:
    """Generate 3 starter questions after an upload (best-effort)."""
    prompt = (
        "Based on the following document excerpt, suggest exactly 3 short, specific "
        "questions a user might ask about it. Return one question per line, no numbering.\n\n"
        f"Document: {document_name}\n\nExcerpt:\n{sample_text[:1500]}"
    )
    try:
        llm = get_llm_provider(temperature=0.4)
        text = llm.complete([{"role": "user", "content": prompt}])
        lines = [l.strip(" -•\t") for l in text.splitlines() if l.strip()]
        return lines[:3]
    except Exception:  # noqa: BLE001
        return []
