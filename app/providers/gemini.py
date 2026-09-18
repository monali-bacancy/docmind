"""Gemini implementation of the provider interfaces (via LangChain adapters)."""

from typing import Iterator, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from app.core.config import settings
from app.providers.base import EmbeddingProvider, LLMProvider


def _detect_embedding_model() -> str:
    """Pick the best embedding model the API key can access."""
    import google.generativeai as genai

    genai.configure(api_key=settings.GOOGLE_API_KEY)
    preferred = ["models/gemini-embedding-001", "models/text-embedding-004"]
    available = [
        m.name for m in genai.list_models()
        if "embedContent" in m.supported_generation_methods
    ]
    for name in preferred:
        if name in available:
            return name
    return available[0] if available else "models/text-embedding-004"


def _to_text(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return str(content)


def _to_lc(messages: List[dict]):
    out = []
    for m in messages:
        role, content = m.get("role"), m.get("content", "")
        if role == "system":
            out.append(SystemMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
        else:
            out.append(HumanMessage(content=content))
    return out


class GeminiEmbeddings(EmbeddingProvider):
    def __init__(self):
        self.name = "gemini"
        self.model = settings.EMBED_MODEL or _detect_embedding_model()
        self._impl = GoogleGenerativeAIEmbeddings(model=self.model)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._impl.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._impl.embed_query(text)


class GeminiLLM(LLMProvider):
    def __init__(self, temperature: float = 0.2):
        self.name = "gemini"
        self.model = settings.CHAT_MODEL
        self._impl = ChatGoogleGenerativeAI(model=self.model, temperature=temperature)

    def stream(self, messages: List[dict]) -> Iterator[str]:
        for chunk in self._impl.stream(_to_lc(messages)):
            text = _to_text(chunk)
            if text:
                yield text

    def complete(self, messages: List[dict]) -> str:
        return _to_text(self._impl.invoke(_to_lc(messages)))
