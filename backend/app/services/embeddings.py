from __future__ import annotations

import asyncio
from typing import Protocol

import httpx

from app.config import settings
from app.logger import get_app_logger

log = get_app_logger()


class Embedder(Protocol):
    async def embed(self, text: str) -> list[float]: ...
    def embed_sync(self, text: str) -> list[float]: ...


class OllamaEmbedder:
    def __init__(self, url: str, model: str) -> None:
        self._url = url
        self._model = model

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                self._url,
                json={"model": self._model, "input": [text]},
            )
            resp.raise_for_status()
            return resp.json()["embeddings"][0]

    def embed_sync(self, text: str) -> list[float]:
        with httpx.Client(timeout=300.0) as client:
            resp = client.post(
                self._url,
                json={"model": self._model, "input": [text]},
            )
            resp.raise_for_status()
            return resp.json()["embeddings"][0]


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            log.info(
                "Loading SentenceTransformer model",
                extra={"event": "st_model_load", "model": self._model_name},
            )
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
            self._model = SentenceTransformer(self._model_name)
        return self._model

    async def embed(self, text: str) -> list[float]:
        model = self._get_model()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: model.encode(text, normalize_embeddings=True)
        )
        return result.tolist()

    def embed_sync(self, text: str) -> list[float]:
        return self._get_model().encode(text, normalize_embeddings=True).tolist()


def build_indicator_embedder() -> OllamaEmbedder | SentenceTransformerEmbedder:
    provider = settings.INDICATOR_EMBEDDING_PROVIDER.lower()
    model = settings.INDICATOR_EMBEDDING_MODEL
    if provider == "sentence_transformers":
        return SentenceTransformerEmbedder(model)
    return OllamaEmbedder(settings.RAG_EMBEDDING_URL, model)


indicator_embedder = build_indicator_embedder()
