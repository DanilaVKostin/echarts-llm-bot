"""
index_indicators.py — Проиндексировать все имена индикаторов d_hcode_v в ChromaDB.

Эмбеддинги кэшируются в data/embeddings/, чтобы при смене модели не нужно было
пересоздавать всё с нуля. Используйте --force-reembed для игнорирования кэша
и перегенерации через Ollama.

Использование (запускать из директории backend/):
    python -m scripts.index_indicators
    python -m scripts.index_indicators --embedding-model bge-m3
    python -m scripts.index_indicators --force-reembed

Параметры:
    --chroma-dir        Путь для хранения ChromaDB        (по умолчанию: ./data/chroma_db)
    --cache-dir         Директория кэша эмбеддингов       (по умолчанию: ./data/embeddings)
    --embedding-url     Эндпоинт Ollama embed             (по умолчанию из настроек)
    --embedding-model   Имя модели Ollama                 (по умолчанию из настроек)
    --collection        Имя коллекции                     (по умолчанию из настроек)
    --force-reembed     Игнорировать кэш, пересоздать все эмбеддинги
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pickle
import re
import sys
import time
from pathlib import Path

import chromadb
import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.services.embeddings import build_indicator_embedder  # noqa: E402

_MAX_EMBED_CHARS = 500


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Index d_hcode_v indicators into ChromaDB")
    p.add_argument("--chroma-dir",      default=settings.RAG_CHROMA_PATH)
    p.add_argument("--cache-dir",   default="./data/embeddings")
    p.add_argument("--collection",  default=settings.INDICATOR_CHROMA_COLLECTION)
    p.add_argument("--force-reembed",   action="store_true", help="Ignore cache and regenerate embeddings")
    return p.parse_args()


def _normalize(text: str) -> str:
    text = re.sub(r'([.,])([^\s])', r'\1 \2', text)
    return text[:_MAX_EMBED_CHARS]


def _cache_path(cache_dir: Path, model: str) -> Path:
    safe_model = re.sub(r'[^\w.-]', '_', model)
    return cache_dir / f"indicators_{safe_model}.pkl"


def load_cache(cache_dir: Path, model: str, ids: list[str]) -> list[list[float] | None] | None:
    """
    Загрузить кэшированные эмбеддинги, если они существуют для данной модели и совпадают с текущим списком id.
    Возвращает None, если кэш отсутствует, устарел или не совпадает.
    """
    path = _cache_path(cache_dir, model)
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            data = pickle.load(f)
        if data.get("model") != model:
            return None
        if data.get("ids") != ids:
            print("  Cache exists but indicator list changed — will regenerate missing items.")
        cached_map: dict[str, list[float]] = dict(zip(data["ids"], data["embeddings"]))
        return [cached_map.get(rid) for rid in ids]
    except Exception as exc:
        print(f"  [WARN] Could not load cache: {exc}", file=sys.stderr)
        return None


def save_cache(cache_dir: Path, model: str, ids: list[str], embeddings: list[list[float] | None]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, model)
    valid_ids = [ids[i] for i in range(len(ids)) if embeddings[i] is not None]
    valid_embs = [embeddings[i] for i in range(len(embeddings)) if embeddings[i] is not None]
    with open(path, "wb") as f:
        pickle.dump({"model": model, "ids": valid_ids, "embeddings": valid_embs}, f)
    print(f"  Embeddings cached → {path}  ({len(valid_ids)} items)")


async def fetch_indicators(database_url: str) -> list[tuple[int, str]]:
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2, command_timeout=30)
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name FROM dm_rep.d_hcode_v ORDER BY id")
    await pool.close()
    return [(int(r["id"]), r["name"]) for r in rows if r["name"]]


def main() -> None:
    args = parse_args()
    cache_dir = Path(args.cache_dir)

    if not settings.DATABASE_URL.strip():
        print("[ERROR] DATABASE_URL is not configured in .env", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'='*60}")
    print("  Indicator Index Builder")
    print(f"{'='*60}")
    print(f"  ChromaDB    : {args.chroma_dir}")
    print(f"  Collection  : {args.collection}")
    print(f"  Embed model : {settings.INDICATOR_EMBEDDING_MODEL}  ({settings.INDICATOR_EMBEDDING_PROVIDER})")
    print(f"  Cache dir   : {cache_dir}")
    print(f"  Force embed : {args.force_reembed}")
    print()

    # 1. Получить данные из БД
    print("── Fetching indicators from PostgreSQL ──")
    try:
        rows = asyncio.run(fetch_indicators(settings.DATABASE_URL))
    except Exception as exc:
        print(f"[ERROR] DB fetch failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  Fetched {len(rows)} indicators")

    if not rows:
        print("[ERROR] No indicators found in d_hcode_v", file=sys.stderr)
        sys.exit(1)

    ids = [str(r[0]) for r in rows]
    names = [r[1] for r in rows]
    embed_texts = [_normalize(n) for n in names]

    embedder = build_indicator_embedder()
    print(f"  Provider    : {settings.INDICATOR_EMBEDDING_PROVIDER}  ({settings.INDICATOR_EMBEDDING_MODEL})")

    # 2. Загрузить кэш или сгенерировать эмбеддинги
    all_embeddings: list[list[float] | None]

    if not args.force_reembed:
        cached = load_cache(cache_dir, settings.INDICATOR_EMBEDDING_MODEL, ids)
    else:
        cached = None

    needs_embed = [i for i in range(len(ids)) if cached is None or cached[i] is None]

    if cached is not None and not needs_embed:
        print(f"\n── Embeddings loaded from cache ({len(ids)} items) ──")
        all_embeddings = cached
    else:
        if cached is not None and needs_embed:
            print(f"\n── Generating embeddings for {len(needs_embed)} new/missing items ──")
        else:
            print(f"\n── Generating embeddings ({len(ids)} items) ──")

        all_embeddings = list(cached) if cached is not None else [None] * len(ids)
        skipped: list[int] = []
        t0 = time.perf_counter()

        for idx, i in enumerate(needs_embed):
            if idx % 50 == 0 or idx == 0:
                print(f"  Item {idx + 1}/{len(needs_embed)}  (indicator {i + 1}/{len(ids)})…")
            try:
                all_embeddings[i] = embedder.embed_sync(embed_texts[i])
            except Exception as exc:
                print(f"  [SKIP] Item {i + 1} id={ids[i]}: {names[i]!r}\n         reason: {exc}", file=sys.stderr)
                skipped.append(i)

        elapsed = time.perf_counter() - t0
        ok_count = sum(1 for e in all_embeddings if e is not None)
        print(f"  Done in {elapsed:.1f}s  ({ok_count} ok, {len(skipped)} skipped)")

        # Сохранить в кэш (включая ранее кэшированные и вновь сгенерированные)
        print("\n── Saving embeddings to cache ──")
        save_cache(cache_dir, settings.INDICATOR_EMBEDDING_MODEL, ids, all_embeddings)

    # 3. Отфильтровать и записать в ChromaDB
    valid_ids = [ids[i] for i in range(len(ids)) if all_embeddings[i] is not None]
    valid_names = [names[i] for i in range(len(names)) if all_embeddings[i] is not None]
    valid_embeddings = [e for e in all_embeddings if e is not None]

    print(f"\n── Writing {len(valid_ids)} indicators to ChromaDB ──")
    chroma_dir = Path(args.chroma_dir)
    chroma_dir.mkdir(parents=True, exist_ok=True)
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))

    existing = [c.name for c in chroma_client.list_collections()]
    if args.collection in existing:
        chroma_client.delete_collection(args.collection)
        print(f"  Deleted existing '{args.collection}' collection")

    collection = chroma_client.create_collection(args.collection)

    insert_batch = 256
    for start in range(0, len(valid_ids), insert_batch):
        sl = slice(start, start + insert_batch)
        collection.add(
            ids=valid_ids[sl],
            documents=valid_names[sl],
            embeddings=valid_embeddings[sl],
        )

    print(f"  Inserted {collection.count()} indicators into '{args.collection}'")
    print(f"\n{'='*60}")
    print("  Done! Restart the backend server to apply the new index.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
