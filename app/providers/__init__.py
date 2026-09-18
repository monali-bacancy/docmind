"""Provider factory — swap vendors here without touching the rest of the app."""

from functools import lru_cache

from app.core.config import settings
from app.providers.base import EmbeddingProvider, LLMProvider


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    if settings.AI_PROVIDER == "gemini":
        from app.providers.gemini import GeminiEmbeddings

        return GeminiEmbeddings()
    raise ValueError(f"Unknown AI_PROVIDER: {settings.AI_PROVIDER}")


def get_llm_provider(temperature: float = 0.2) -> LLMProvider:
    if settings.AI_PROVIDER == "gemini":
        from app.providers.gemini import GeminiLLM

        return GeminiLLM(temperature=temperature)
    raise ValueError(f"Unknown AI_PROVIDER: {settings.AI_PROVIDER}")
