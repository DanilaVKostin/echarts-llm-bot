"""
build_rag.py — Построить векторный индекс ChromaDB из локальной документации ECharts.

Использование (запускать из директории backend/):
    python -m scripts.build_rag
    python -m scripts.build_rag --source-dir ../data/rag_sources --chroma-dir ./data/chroma_db

Параметры:
    --source-dir        Директория с исходными файлами (по умолчанию: ../data/rag_sources)
    --chroma-dir        Путь для хранения ChromaDB     (по умолчанию: ./data/chroma_db)
    --collection        Имя коллекции                  (по умолчанию: echarts)
    --embedding-url     Эндпоинт Ollama embed          (по умолчанию: http://localhost:11434/api/embed)
    --embedding-model   Имя модели Ollama              (по умолчанию: nomic-embed-text)
    --chunk-size        Макс. символов в чанке         (по умолчанию: 1200)
    --overlap           Перекрытие между чанками       (по умолчанию: 200)
    --batch-size        Размер батча эмбеддингов       (по умолчанию: 16)
    --backup-existing   Скопировать chroma_db перед пересборкой
    --echarts-version   Тег версии для манифеста       (по умолчанию: 5.x)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import chromadb

# ── Аргументы командной строки ───────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build ChromaDB RAG index for ECharts docs")
    p.add_argument("--source-dir",      default="../data/rag_sources", help="Source files directory")
    p.add_argument("--chroma-dir",      default="./data/chroma_db",    help="ChromaDB persistence path")
    p.add_argument("--collection",      default="echarts",             help="ChromaDB collection name")
    p.add_argument("--embedding-url",   default="http://localhost:11434/api/embed")
    p.add_argument("--embedding-model", default="nomic-embed-text")
    p.add_argument("--chunk-size",      type=int, default=1200)
    p.add_argument("--overlap",         type=int, default=200)
    p.add_argument("--batch-size",      type=int, default=16)
    p.add_argument("--backup-existing", action="store_true", help="Backup existing chroma_db before rebuilding")
    p.add_argument("--echarts-version", default="5.x")
    return p.parse_args()

# ── Разворачивание JSON ──────────────────────────────────────────────────────

def flatten_json(obj: Any, prefix: str = "") -> list[str]:
    """Рекурсивно преобразовать JSON-объект в строки вида 'ключ: значение'."""
    lines: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            full_key = f"{prefix}.{k}" if prefix else k
            lines.extend(flatten_json(v, full_key))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            lines.extend(flatten_json(item, f"{prefix}[{i}]"))
    else:
        lines.append(f"{prefix}: {obj}")
    return lines

# ── Загрузка документов ──────────────────────────────────────────────────────

def load_document(path: Path) -> str:
    """Загрузить файл и вернуть его текстовое содержимое."""
    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8")

    if suffix == ".json":
        try:
            data = json.loads(raw)
            lines = flatten_json(data)
            return "\n".join(lines)
        except json.JSONDecodeError as exc:
            print(f"  [WARN] Could not parse {path.name} as JSON: {exc}", file=sys.stderr)
            return raw  # fall back to raw text
    else:
        return raw  # .md, .txt — use as-is

# ── Разбивка на чанки ────────────────────────────────────────────────────────

# Совпадает со строками, начинающимися с одного или двух символов # (заголовки H1/H2 markdown)
_HEADING_RE = re.compile(r"^#{1,2}\s+.+", re.MULTILINE)


def split_on_headings(text: str) -> list[str]:
    """
    Разделить *text* на секции по каждому заголовку H1/H2.
    Каждая секция включает свою строку заголовка.
    """
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [text]

    sections: list[str] = []
    # Текст до первого заголовка
    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.append(preamble)

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append(text[start:end].strip())

    return [s for s in sections if s]


def sliding_window(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Разбить *text* на перекрывающиеся чанки не более *chunk_size* символов каждый."""
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += chunk_size - overlap
    return chunks


def chunk_document(text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    1. Разделить по заголовкам H1/H2 для сохранения семантических секций.
    2. Применить разбивку скользящим окном внутри каждой секции.
    """
    chunks: list[str] = []
    for section in split_on_headings(text):
        chunks.extend(sliding_window(section, chunk_size, overlap))
    return [c.strip() for c in chunks if c.strip()]


def chunk_id(filepath: Path, chunk_index: int, text: str) -> str:
    """Стабильный SHA-1 идентификатор чанка."""
    raw = f"{filepath.as_posix()}|{chunk_index}|{text}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

# ── Эмбеддинги ───────────────────────────────────────────────────────────────

def embed_batch(texts: list[str], url: str, model: str) -> list[list[float]]:
    """Вызвать эндпоинт Ollama embed для батча текстов и вернуть эмбеддинги."""
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(url, json={"model": model, "input": texts})
        resp.raise_for_status()
        return resp.json()["embeddings"]


def embed_all(
    texts: list[str],
    url: str,
    model: str,
    batch_size: int,
) -> list[list[float]]:
    """Создать эмбеддинги для всех текстов батчами с выводом прогресса."""
    all_embeddings: list[list[float]] = []
    total_batches = (len(texts) + batch_size - 1) // batch_size

    for batch_num, start in enumerate(range(0, len(texts), batch_size), 1):
        batch = texts[start : start + batch_size]
        print(f"  Embedding batch {batch_num}/{total_batches} ({len(batch)} chunks)…")
        embeddings = embed_batch(batch, url, model)
        all_embeddings.extend(embeddings)

    return all_embeddings

# ── Резервная копия ──────────────────────────────────────────────────────────

def backup_chroma(chroma_dir: Path) -> Path | None:
    if not chroma_dir.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = chroma_dir.parent / f"{chroma_dir.name}_backup_{ts}"
    shutil.copytree(chroma_dir, backup_path)
    print(f"  Backed up existing index → {backup_path}")
    return backup_path

# ── Точка входа ──────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    source_dir = Path(args.source_dir)
    chroma_dir = Path(args.chroma_dir)

    if not source_dir.exists():
        print(f"[ERROR] Source directory not found: {source_dir}", file=sys.stderr)
        sys.exit(1)

    # 1. Собрать исходные файлы
    extensions = {".md", ".txt", ".json"}
    source_files = sorted(
        p for p in source_dir.rglob("*") if p.is_file() and p.suffix.lower() in extensions
    )
    if not source_files:
        print(f"[ERROR] No .md/.txt/.json files found in {source_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  ECharts RAG Index Builder")
    print(f"{'='*60}")
    print(f"  Source      : {source_dir.resolve()} ({len(source_files)} files)")
    print(f"  ChromaDB    : {chroma_dir.resolve()}")
    print(f"  Collection  : {args.collection}")
    print(f"  Embed model : {args.embedding_model}")
    print(f"  Chunk size  : {args.chunk_size}  Overlap: {args.overlap}")
    print(f"  Batch size  : {args.batch_size}")
    print()

    # 2. Загрузить и разбить на чанки все документы
    print("── Loading & chunking documents ──")
    all_ids:       list[str] = []
    all_texts:     list[str] = []
    all_metadatas: list[dict] = []

    for path in source_files:
        print(f"  {path.name}")
        text = load_document(path)
        chunks = chunk_document(text, args.chunk_size, args.overlap)
        print(f"    → {len(chunks)} chunk(s)")

        for idx, chunk in enumerate(chunks):
            cid = chunk_id(path, idx, chunk)
            all_ids.append(cid)
            all_texts.append(chunk)
            all_metadatas.append({
                "source": path.name,
                "chunk_index": idx,
                "char_count": len(chunk),
            })

    print(f"\n  Total chunks: {len(all_texts)}")

    # 3. Создать эмбеддинги
    print("\n── Generating embeddings ──")
    t0 = time.perf_counter()
    try:
        all_embeddings = embed_all(all_texts, args.embedding_url, args.embedding_model, args.batch_size)
    except Exception as exc:
        print(f"\n[ERROR] Embedding failed: {exc}", file=sys.stderr)
        print("  Make sure Ollama is running and the model is pulled:", file=sys.stderr)
        print(f"    ollama pull {args.embedding_model}", file=sys.stderr)
        sys.exit(1)
    embed_elapsed = time.perf_counter() - t0
    print(f"  Done in {embed_elapsed:.1f}s")

    # 4. Резервная копия существующей коллекции
    if args.backup_existing:
        print("\n── Backing up existing index ──")
        backup_chroma(chroma_dir)

    # 5. Записать в ChromaDB
    print("\n── Writing to ChromaDB ──")
    chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_dir))

    # Удалить существующую коллекцию, если есть
    existing = [c.name for c in client.list_collections()]
    if args.collection in existing:
        print(f"  Deleting existing collection '{args.collection}'…")
        client.delete_collection(args.collection)

    collection = client.create_collection(args.collection)

    # Вставлять батчами во избежание пиков памяти на больших индексах
    insert_batch = 256
    for start in range(0, len(all_ids), insert_batch):
        sl = slice(start, start + insert_batch)
        collection.add(
            ids=all_ids[sl],
            documents=all_texts[sl],
            embeddings=all_embeddings[sl],
            metadatas=all_metadatas[sl],
        )
    print(f"  Inserted {collection.count()} chunks into '{args.collection}'")

    # 6. Записать манифест
    manifest = {
        "echarts_version": args.echarts_version,
        "collection": args.collection,
        "embedding_model": args.embedding_model,
        "chunk_count": collection.count(),
        "chunk_size": args.chunk_size,
        "overlap": args.overlap,
        "source_files": [p.name for p in source_files],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = chroma_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"  Manifest written → {manifest_path}")

    # 7. Вывести итоги
    print(f"\n{'='*60}")
    print("  Summary")
    print(f"{'='*60}")
    print(json.dumps(manifest, indent=2))
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
