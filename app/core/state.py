"""Document processing states (Section 6 of the spec)."""

from enum import Enum


class DocStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PARSED = "parsed"
    CHUNKED = "chunked"
    EMBEDDING = "embedding"
    INDEXED = "indexed"
    READY = "ready"
    FAILED = "failed"


# Ordered pipeline (used by the UI to render progress steps).
PIPELINE_ORDER = [
    DocStatus.UPLOADED,
    DocStatus.PARSED,
    DocStatus.CHUNKED,
    DocStatus.EMBEDDING,
    DocStatus.INDEXED,
    DocStatus.READY,
]
