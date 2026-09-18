"""Text cleaning (Section 10): whitespace normalization + artifact/hyphenation cleanup."""

import re

_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_HYPHEN_BREAK = re.compile(r"(\w+)-\n(\w+)")  # word broken across a line with a hyphen


def clean(text: str) -> str:
    # Normalize line endings.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Re-join words hyphenated across line breaks (common in PDFs).
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    # Collapse runs of spaces/tabs.
    text = _MULTI_SPACE.sub(" ", text)
    # Trim trailing spaces on each line.
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    # Collapse excessive blank lines (preserve paragraph breaks).
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()
