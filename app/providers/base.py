"""Provider-agnostic interfaces (Section 61). The app depends on these, not on Gemini directly."""

from abc import ABC, abstractmethod
from typing import Iterator, List


class EmbeddingProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        ...

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        ...


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def stream(self, messages: List[dict]) -> Iterator[str]:
        """Yield answer text chunks. `messages` = [{role, content}, ...]."""

    @abstractmethod
    def complete(self, messages: List[dict]) -> str:
        """Return a full (non-streamed) completion."""
