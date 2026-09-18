"""
Chunking (Section 11). Structure-aware: split page-by-page so every chunk keeps
its real page number, then apply an overlapping recursive splitter within a page.

Token counts are approximated as ~chars/4 (avoids a heavy tokenizer dependency
while still giving a useful metadata number).
"""

from dataclasses import dataclass
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.services.cleaner import clean
from app.services.parser import ParsedPage


@dataclass
class Chunk:
    chunk_index: int
    page_number: int
    section: str
    content: str
    token_count: int


def approx_tokens(text: str) -> int:
    return max(1, round(len(text) / 4))


def chunk_pages(pages: List[ParsedPage]) -> List[Chunk]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks: List[Chunk] = []
    index = 0
    for page in pages:
        cleaned = clean(page.text)
        if not cleaned:
            continue
        section = page.metadata.get("section", "")
        for piece in splitter.split_text(cleaned):
            piece = piece.strip()
            if not piece:
                continue
            chunks.append(
                Chunk(
                    chunk_index=index,
                    page_number=page.page_number,
                    section=section,
                    content=piece,
                    token_count=approx_tokens(piece),
                )
            )
            index += 1
    return chunks
