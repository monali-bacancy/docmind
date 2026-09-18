"""
Document parsing (Section 9). Returns page-structured text so citations can
reference real page numbers.

  parse(path, ext) -> List[ParsedPage]
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ParsedPage:
    page_number: int
    text: str
    metadata: Dict = field(default_factory=dict)


def parse(path: str, ext: str) -> List[ParsedPage]:
    if ext == ".pdf":
        return _parse_pdf(path)
    if ext == ".docx":
        return _parse_docx(path)
    return _parse_text(path)


def _parse_pdf(path: str) -> List[ParsedPage]:
    import pymupdf  # PyMuPDF

    pages: List[ParsedPage] = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if text:
                pages.append(ParsedPage(page_number=i, text=text, metadata={"kind": "pdf"}))
    return pages


def _parse_docx(path: str) -> List[ParsedPage]:
    import docx

    document = docx.Document(path)
    lines: List[str] = []
    current_section = ""
    for para in document.paragraphs:
        txt = para.text.strip()
        if not txt:
            continue
        # Treat Word headings as section markers (helps citation context).
        if para.style and para.style.name and para.style.name.lower().startswith("heading"):
            current_section = txt
        lines.append(txt)
    text = "\n".join(lines)
    # DOCX has no fixed pages; treat as a single logical page.
    return [ParsedPage(page_number=1, text=text, metadata={"kind": "docx", "section": current_section})] if text else []


def _parse_text(path: str) -> List[ParsedPage]:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read().strip()
    return [ParsedPage(page_number=1, text=text, metadata={"kind": "text"})] if text else []
