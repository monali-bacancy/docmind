"""
Vector store wrapper around Chroma (Section 12 & 17).

Stores chunk embeddings with metadata (kb_id, document_id, page_number, section)
so retrieval can filter by knowledge base and map results back to citations.
Persisted to disk so the index survives restarts.
"""

import threading
from typing import Dict, List, Tuple

import chromadb

from app.core.config import settings
from app.providers import get_embedding_provider

_lock = threading.Lock()


class VectorStore:
    def __init__(self):
        self.embedder = get_embedding_provider()
        self._client = chromadb.PersistentClient(path=str(settings.CHROMA_DIR))
        self._collection = self._client.get_or_create_collection(
            name="chunks", metadata={"hnsw:space": "cosine"}
        )

    def add(self, ids: List[str], texts: List[str], metadatas: List[Dict]) -> None:
        vectors = self.embedder.embed_documents(texts)
        with _lock:
            self._collection.add(
                ids=ids, embeddings=vectors, documents=texts, metadatas=metadatas
            )

    def delete_document(self, document_id: str) -> None:
        with _lock:
            self._collection.delete(where={"document_id": document_id})

    def search(self, query: str, kb_id: str, k: int) -> List[Tuple[Dict, float]]:
        """Return [(metadata+content, similarity), ...] filtered to one knowledge base."""
        query_vec = self.embedder.embed_query(query)
        with _lock:
            res = self._collection.query(
                query_embeddings=[query_vec],
                n_results=k,
                where={"kb_id": kb_id},
                include=["documents", "metadatas", "distances"],
            )
        out: List[Tuple[Dict, float]] = []
        if not res.get("ids") or not res["ids"][0]:
            return out
        for cid, doc, meta, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            similarity = max(0.0, min(1.0, 1.0 - float(dist)))
            payload = dict(meta)
            payload["chunk_id"] = cid
            payload["content"] = doc
            out.append((payload, similarity))
        return out


_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
