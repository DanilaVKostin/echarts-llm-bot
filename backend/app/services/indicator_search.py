from __future__ import annotations

import chromadb

from app.config import settings
from app.logger import get_app_logger
from app.services.embeddings import indicator_embedder

log = get_app_logger()

_TABLE_KEYS = ["hcode", "org", "metric_type", "val_type", "date_type"]


class IndicatorSearchService:
    def __init__(self) -> None:
        self._collection: chromadb.Collection | None = None
        self._table_counts: dict[str, int] | None = None

    def _get_collection(self) -> chromadb.Collection:
        if self._collection is None:
            client = chromadb.PersistentClient(path=settings.RAG_CHROMA_PATH)
            self._collection = client.get_or_create_collection(
                settings.INDICATOR_CHROMA_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def _get_table_counts(self, collection: chromadb.Collection) -> dict[str, int]:
        if self._table_counts is None:
            counts: dict[str, int] = {}
            for key in _TABLE_KEYS:
                result = collection.get(where={"table": key}, include=[])
                counts[key] = len(result["ids"])
            self._table_counts = counts
        return self._table_counts

    async def search(self, query: str, top_k: int = 10) -> list[dict]:
        try:
            collection = self._get_collection()
            if collection.count() == 0:
                return []

            table_counts = self._get_table_counts(collection)
            embedding = await indicator_embedder.embed(query)

            all_items: list[dict] = []
            for table_key in _TABLE_KEYS:
                count = table_counts.get(table_key, 0)
                if count == 0:
                    continue
                results = collection.query(
                    query_embeddings=[embedding],
                    n_results=min(top_k, count),
                    include=["documents", "distances", "metadatas"],
                    where={"table": table_key},
                )
                docs = results.get("documents", [[]])[0]
                distances = results.get("distances", [[]])[0]
                ids = results.get("ids", [[]])[0]
                metadatas = results.get("metadatas", [[]])[0]

                for doc, dist, rid, meta in zip(docs, distances, ids, metadatas):
                    score = round(max(0.0, 1.0 - (dist ** 2) / 2.0), 4)
                    table = (meta or {}).get("table", table_key)
                    raw_id = rid.split("__", 1)[1] if "__" in rid else rid
                    all_items.append({"table": table, "id": raw_id, "name": doc, "score": score})

            return all_items

        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Indicator search failed",
                extra={"event": "indicator_search_error", "error": str(exc)},
            )
            return []

    def _query_table(
        self,
        collection: chromadb.Collection,
        embedding: list[float],
        table_key: str,
        n: int,
    ) -> list[dict]:
        results = collection.query(
            query_embeddings=[embedding],
            n_results=n,
            include=["documents", "distances", "metadatas"],
            where={"table": table_key},
        )
        items = []
        for doc, dist, rid, meta in zip(
            results.get("documents", [[]])[0],
            results.get("distances", [[]])[0],
            results.get("ids", [[]])[0],
            results.get("metadatas", [[]])[0],
        ):
            score = round(max(0.0, 1.0 - (dist ** 2) / 2.0), 4)
            raw_id = rid.split("__", 1)[1] if "__" in rid else rid
            items.append({
                "table": (meta or {}).get("table", table_key),
                "id": raw_id,
                "name": doc,
                "score": score,
            })
        return items

    async def _search_table_by_terms(
        self,
        collection: chromadb.Collection,
        table_key: str,
        terms: list[str],
        top_k: int,
        count: int,
    ) -> list[dict]:
        best_by_id: dict[str, dict] = {}
        for term in terms:
            embedding = await indicator_embedder.embed(term)
            for item in self._query_table(collection, embedding, table_key, min(top_k, count)):
                rid = item["id"]
                if rid not in best_by_id or item["score"] > best_by_id[rid]["score"]:
                    best_by_id[rid] = {**item, "matched_term": term}
        return sorted(best_by_id.values(), key=lambda x: -x["score"])[:top_k]

    async def search_by_terms(
        self,
        terms_by_table: dict[str, list[str]],
        top_k: int = 10,
    ) -> list[dict]:
        try:
            collection = self._get_collection()
            if collection.count() == 0:
                return []

            table_counts = self._get_table_counts(collection)
            all_items: list[dict] = []

            for table_key in _TABLE_KEYS:
                terms = [t for t in terms_by_table.get(table_key, []) if t]
                count = table_counts.get(table_key, 0)
                if not terms or count == 0:
                    continue
                results = await self._search_table_by_terms(collection, table_key, terms, top_k, count)
                all_items.extend(results)

            return all_items

        except Exception as exc:  
            log.warning(
                "Smart indicator search failed",
                extra={"event": "smart_search_error", "error": str(exc)},
            )
            return []

    def get_status(self) -> dict:
        try:
            collection = self._get_collection()
            count = collection.count()
            return {"ok": count > 0, "count": count, "error": None}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "count": 0, "error": str(exc)}


indicator_search_service = IndicatorSearchService()
