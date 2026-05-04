from __future__ import annotations

import httpx
import chromadb

from app.config import settings
from app.logger import get_app_logger

log = get_app_logger()


class RAGService:
    def __init__(self) -> None:
        self._collection: chromadb.Collection | None = None

    def _get_collection(self) -> chromadb.Collection:
        if self._collection is None:
            client = chromadb.PersistentClient(path=settings.RAG_CHROMA_PATH)
            self._collection = client.get_collection(settings.RAG_CHROMA_COLLECTION)
        return self._collection

    async def _get_embedding(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                settings.RAG_EMBEDDING_URL,
                json={"model": settings.RAG_EMBEDDING_MODEL, "input": text},
            )
            resp.raise_for_status()
            return resp.json()["embeddings"][0]

    async def retrieve(self, query: str) -> list[str]:
        if not settings.RAG_ENABLED:
            return []

        try:
            embedding = await self._get_embedding(query)
            collection = self._get_collection()
            results = collection.query(
                query_embeddings=[embedding],
                n_results=settings.RAG_TOP_K,
            )
            docs: list[str] = results.get("documents", [[]])[0]
            log.info(
                "RAG retrieved chunks",
                extra={"event": "rag_retrieve", "query": query, "chunks": len(docs)},
            )
            return docs
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "RAG retrieval failed — skipping",
                extra={"event": "rag_error", "error": str(exc)},
            )
            return []

    async def check_status(self) -> dict:
        status: dict = {"ok": False, "collection_count": None, "error": None}

        if not settings.RAG_ENABLED:
            status["error"] = "RAG is disabled (RAG_ENABLED=false)"
            return status

        try:
            await self._get_embedding("ping")
        except Exception as exc:  # noqa: BLE001
            status["error"] = f"Embedding endpoint unreachable: {exc}"
            return status

        try:
            collection = self._get_collection()
            status["collection_count"] = collection.count()
            status["ok"] = True
        except Exception as exc:  # noqa: BLE001
            status["error"] = f"ChromaDB collection error: {exc}"

        return status


rag_service = RAGService()
