from __future__ import annotations

import argparse
import asyncio
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

_TABLE_CONFIGS: list[tuple[str, str, str, str]] = [
    # (table_key, full_table_name, id_column, name_column)
    ("hcode",       "dm_rep.d_hcode_v",       "id",      "name"),
    ("org",         "dm_rep.d_org_v",          "base_id", "name"),
    ("metric_type", "dm_rep.d_metric_type_v",  "base_id", "name"),
    ("val_type",    "dm_rep.d_val_type_v",     "base_id", "name"),
    ("date_type",   "dm_rep.d_date_type_v",    "base_id", "name"),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Index reference table indicators into ChromaDB")
    p.add_argument("--chroma-dir",    default=settings.RAG_CHROMA_PATH)
    p.add_argument("--cache-dir",     default="./data/embeddings")
    p.add_argument("--collection",    default=settings.INDICATOR_CHROMA_COLLECTION)
    p.add_argument("--force-reembed", action="store_true", help="Ignore cache and regenerate embeddings")
    return p.parse_args()


def _normalize(text: str) -> str:
    text = re.sub(r'([.,])([^\s])', r'\1 \2', text)
    return text[:_MAX_EMBED_CHARS]


def _cache_path(cache_dir: Path, model: str) -> Path:
    safe_model = re.sub(r'[^\w.-]', '_', model)
    return cache_dir / f"indicators_all_{safe_model}.pkl"


def load_cache(cache_dir: Path, model: str, ids: list[str]) -> list[list[float] | None] | None:
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


async def fetch_all_indicators(database_url: str) -> list[tuple[str, str, str]]:
    """Returns list of (prefixed_id, name, table_key) from all reference tables."""
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2, command_timeout=30)
    all_rows: list[tuple[str, str, str]] = []
    async with pool.acquire() as conn:
        for table_key, table_name, id_col, name_col in _TABLE_CONFIGS:
            try:
                rows = await conn.fetch(
                    f"SELECT {id_col}, {name_col} FROM {table_name} ORDER BY {id_col}"
                )
                count = 0
                for r in rows:
                    if r[name_col]:
                        all_rows.append((f"{table_key}__{r[id_col]}", r[name_col], table_key))
                        count += 1
                print(f"  {table_key} ({table_name}): {count} rows")
            except Exception as exc:
                print(f"  [WARN] {table_name}: {exc}", file=sys.stderr)
    await pool.close()
    return all_rows


def _generate_missing(
    embedder: object,
    ids: list[str],
    names: list[str],
    embed_texts: list[str],
    base: list[list[float] | None],
    needs: list[int],
) -> list[list[float] | None]:
    result = list(base)
    t0 = time.perf_counter()
    skipped = 0
    for idx, i in enumerate(needs):
        if idx % 50 == 0:
            print(f"  Item {idx + 1}/{len(needs)}  (indicator {i + 1}/{len(ids)})…")
        try:
            result[i] = embedder.embed_sync(embed_texts[i])  # type: ignore[attr-defined]
        except Exception as exc:
            print(f"  [SKIP] id={ids[i]}: {names[i]!r}\n         reason: {exc}", file=sys.stderr)
            skipped += 1
    elapsed = time.perf_counter() - t0
    ok = sum(1 for e in result if e is not None)
    print(f"  Done in {elapsed:.1f}s  ({ok} ok, {skipped} skipped)")
    return result


def _build_embeddings(
    embedder: object,
    ids: list[str],
    names: list[str],
    embed_texts: list[str],
    cache_dir: Path,
    model: str,
    force: bool,
) -> list[list[float] | None]:
    cached = None if force else load_cache(cache_dir, model, ids)
    needs = [i for i in range(len(ids)) if cached is None or cached[i] is None]

    if cached is not None and not needs:
        print(f"\n── Embeddings loaded from cache ({len(ids)} items) ──")
        return cached

    label = f"{len(needs)} new/missing items" if cached is not None else f"{len(ids)} items"
    print(f"\n── Generating embeddings ({label}) ──")

    base: list[list[float] | None] = list(cached) if cached is not None else [None] * len(ids)
    result = _generate_missing(embedder, ids, names, embed_texts, base, needs)

    print("\n── Saving embeddings to cache ──")
    save_cache(cache_dir, model, ids, result)
    return result


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
    print(f"  Tables      : {', '.join(cfg[0] for cfg in _TABLE_CONFIGS)}")
    print()

    print("── Fetching indicators from PostgreSQL ──")
    try:
        rows = asyncio.run(fetch_all_indicators(settings.DATABASE_URL))
    except Exception as exc:
        print(f"[ERROR] DB fetch failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  Total fetched: {len(rows)} indicators")

    if not rows:
        print("[ERROR] No indicators found in any reference table", file=sys.stderr)
        sys.exit(1)

    ids = [r[0] for r in rows]
    names = [r[1] for r in rows]
    table_keys = [r[2] for r in rows]
    embed_texts = [_normalize(n) for n in names]

    embedder = build_indicator_embedder()
    print(f"  Provider    : {settings.INDICATOR_EMBEDDING_PROVIDER}  ({settings.INDICATOR_EMBEDDING_MODEL})")

    all_embeddings = _build_embeddings(
        embedder, ids, names, embed_texts, cache_dir,
        settings.INDICATOR_EMBEDDING_MODEL, args.force_reembed,
    )

    valid_indices = [i for i in range(len(ids)) if all_embeddings[i] is not None]
    valid_ids = [ids[i] for i in valid_indices]
    valid_names = [names[i] for i in valid_indices]
    valid_tables = [table_keys[i] for i in valid_indices]
    valid_embeddings = [all_embeddings[i] for i in valid_indices]
    valid_metadatas = [{"table": t} for t in valid_tables]

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
            metadatas=valid_metadatas[sl],
        )

    print(f"  Inserted {collection.count()} indicators into '{args.collection}'")
    print(f"\n{'='*60}")
    print("  Done! Restart the backend server to apply the new index.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
