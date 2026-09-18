"""Context builder + prompt design (Sections 21, 22). Dedupes, numbers, and formats sources."""

from typing import Dict, List, Tuple

from app.core.config import settings
from app.services.retrieval import Retrieved

SYSTEM_PROMPT = """You are DocMind, a knowledge-base assistant.

Answer the user's question using ONLY the numbered context sources below.
When you state a fact from a source, cite it inline with its number, like [1] or [2].
If the context does not contain enough information to answer, reply exactly:
"I couldn't find this information in the selected knowledge base."
Do not invent facts and do not use outside knowledge.
Keep the answer clear and concise.

CONTEXT SOURCES:
{context}
"""


def build_context(results: List[Retrieved]) -> Tuple[str, List[Dict]]:
    """Return (formatted_context_string, structured_sources)."""
    seen = set()
    context_blocks: List[str] = []
    sources: List[Dict] = []

    idx = 0
    for r in results:
        # De-duplicate identical chunks.
        key = (r.document_id, r.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        idx += 1

        header = f"SOURCE {idx}\nDocument: {r.document_name}\nPage: {r.page_number}"
        if r.section:
            header += f"\nSection: {r.section}"
        context_blocks.append(f"{header}\n\n{r.content}")

        sources.append(
            {
                "index": idx,
                "chunk_id": r.chunk_id,
                "document_id": r.document_id,
                "document_name": r.document_name,
                "page_number": r.page_number,
                "section": r.section,
                "score": round(r.score, 3),
                "snippet": r.content.strip()[:280],
            }
        )

    context = "\n\n---\n\n".join(context_blocks) if context_blocks else "(no relevant sources found)"
    return context, sources


def system_prompt(context: str) -> str:
    return SYSTEM_PROMPT.format(context=context)
