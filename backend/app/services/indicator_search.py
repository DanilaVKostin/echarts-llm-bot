from __future__ import annotations

import chromadb

from app.config import settings
from app.logger import get_app_logger
from app.services.embeddings import indicator_embedder

log = get_app_logger()


class IndicatorSearchService:
    def __init__(self) -> None:
        self._collection: chromadb.Collection | None = None

    def _get_collection(self) -> chromadb.Collection:
        if self._collection is None:
            client = chromadb.PersistentClient(path=settings.RAG_CHROMA_PATH)
            self._collection = client.get_or_create_collection(
                settings.INDICATOR_CHROMA_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    async def search(self, query: str, top_k: int = 10) -> list[dict]:
        try:
            collection = self._get_collection()
            count = collection.count()
            if count == 0:
                return []

            embedding = await indicator_embedder.embed(query)
            results = collection.query(
                query_embeddings=[embedding],
                n_results=min(top_k, count),
                include=["documents", "distances"],
            )

            docs = results.get("documents", [[]])[0]
            distances = results.get("distances", [[]])[0]
            ids = results.get("ids", [[]])[0]

            items = []
            for doc, dist, rid in zip(docs, distances, ids):
                # L2-расстояние на нормализованных векторах: cos_sim = 1 - dist²/2
                score = round(max(0.0, 1.0 - (dist ** 2) / 2.0), 4)
                items.append({"id": int(rid), "name": doc, "score": score})
            return items

        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Indicator search failed",
                extra={"event": "indicator_search_error", "error": str(exc)},
            )
            return []

    async def get_status(self) -> dict:
        try:
            collection = self._get_collection()
            count = collection.count()
            return {"ok": count > 0, "count": count, "error": None}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "count": 0, "error": str(exc)}


indicator_search_service = IndicatorSearchService()
