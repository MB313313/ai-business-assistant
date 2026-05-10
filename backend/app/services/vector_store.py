"""FAISS index + local disk persistence; metadata aligned row-wise with vectors."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Final, TypedDict

import faiss
import numpy as np

from ..config import _PROJECT_ROOT
from . import embedding_service

_DATA_DIR: Final = _PROJECT_ROOT / "data" / "vector_store"
_INDEX_PATH: Final = _DATA_DIR / "faiss.index"
_META_PATH: Final = _DATA_DIR / "meta.jsonl"

_lock = threading.Lock()
_index: faiss.Index | None = None
_meta: list[dict[str, str]] = []


class RetrievedChunk(TypedDict):
    document_id: str
    text: str
    score: float


def _ensure_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_from_disk_locked() -> None:
    global _index, _meta
    if not _INDEX_PATH.exists() or not _META_PATH.exists():
        return
    loaded = faiss.read_index(str(_INDEX_PATH))
    rows: list[dict[str, str]] = []
    with open(_META_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    if loaded.ntotal != len(rows):
        raise RuntimeError(
            f"Vector store mismatch: FAISS has {loaded.ntotal} vectors but {len(rows)} metadata rows."
        )
    _index = loaded
    _meta = rows


def try_load_from_disk() -> None:
    """Load index + metadata from disk if present (call on startup)."""
    with _lock:
        global _index, _meta
        if _index is not None:
            return
        if _INDEX_PATH.exists() and _META_PATH.exists():
            _load_from_disk_locked()


def _save_locked() -> None:
    if _index is None:
        return
    _ensure_dir()
    faiss.write_index(_index, str(_INDEX_PATH))
    with open(_META_PATH, "w", encoding="utf-8") as f:
        for row in _meta:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def total_vectors() -> int:
    with _lock:
        if _index is None:
            return 0
        return int(_index.ntotal)


async def index_document_chunks(document_id: str, chunks: list[str]) -> tuple[int, int]:
    """
    Embed ``chunks``, append to the FAISS index (cosine via normalized inner product),
    extend metadata, and persist to disk.

    Returns ``(indexed_chunk_count, total_vectors_after)``.
    """
    chunks = [c.strip() for c in chunks if c.strip()]
    if not chunks:
        return 0, total_vectors()

    vectors = await embedding_service.embed_texts(chunks)
    dim = int(vectors.shape[1])

    with _lock:
        global _index, _meta
        if _index is None and _INDEX_PATH.exists() and _META_PATH.exists():
            _load_from_disk_locked()

        if _index is None:
            _index = faiss.IndexFlatIP(dim)
            _meta = []
        elif int(_index.d) != dim:
            raise RuntimeError(
                f"Embedding dimension {dim} does not match existing index dimension {_index.d}."
            )

        _index.add(vectors)
        for text in chunks:
            _meta.append({"document_id": document_id, "text": text})

        _save_locked()
        total = int(_index.ntotal)

    return len(chunks), total


async def retrieve_relevant_chunks(query: str, top_k: int = 5) -> list[RetrievedChunk]:
    """
    Embed ``query`` and return the top ``top_k`` chunks by inner product score
    (higher is more similar, for L2-normalized embeddings).
    """
    if top_k < 1:
        return []

    q = await embedding_service.embed_query(query)

    with _lock:
        if _index is None and _INDEX_PATH.exists() and _META_PATH.exists():
            _load_from_disk_locked()
        if _index is None or _index.ntotal == 0:
            return []

        k = min(top_k, int(_index.ntotal))
        scores, indices = _index.search(q, k)

    hits: list[RetrievedChunk] = []
    for score, idx in zip(scores[0].tolist(), indices[0].tolist()):
        if idx < 0 or idx >= len(_meta):
            continue
        row = _meta[idx]
        hits.append(
            RetrievedChunk(
                document_id=row["document_id"],
                text=row["text"],
                score=float(score),
            )
        )
    return hits


async def retrieve_relevant_chunks_scoped(
    query: str,
    top_k: int,
    allowed_document_ids: frozenset[str],
) -> list[RetrievedChunk]:
    """
    Like ``retrieve_relevant_chunks``, but only considers vectors whose ``document_id``
    is in ``allowed_document_ids``. Use this so each user only retrieves **their**
    indexed uploads, not every vector in the shared FAISS index.
    """
    if top_k < 1 or not allowed_document_ids:
        return []

    allowed = frozenset((d or "").strip() for d in allowed_document_ids if (d or "").strip())
    if not allowed:
        return []

    q = await embedding_service.embed_query(query)
    qv = np.asarray(q[0], dtype=np.float32)

    with _lock:
        if _index is None and _INDEX_PATH.exists() and _META_PATH.exists():
            _load_from_disk_locked()
        if _index is None or _index.ntotal == 0:
            return []

        idxs = [
            i
            for i, row in enumerate(_meta)
            if (row.get("document_id") or "").strip() in allowed
        ]
        if not idxs:
            return []

        scores: list[tuple[float, int]] = []
        for i in idxs:
            v = np.asarray(_index.reconstruct(int(i)), dtype=np.float32)
            s = float(np.dot(qv, v))
            scores.append((s, i))

        scores.sort(key=lambda t: t[0], reverse=True)
        take = scores[: min(top_k, len(scores))]

    hits: list[RetrievedChunk] = []
    for score, idx in take:
        if idx < 0 or idx >= len(_meta):
            continue
        row = _meta[idx]
        hits.append(
            RetrievedChunk(
                document_id=row["document_id"],
                text=row["text"],
                score=float(score),
            )
        )
    return hits


async def retrieve_relevant_chunks_for_document(
    query: str, document_id: str, top_k: int = 6
) -> list[RetrievedChunk]:
    """
    Like ``retrieve_relevant_chunks``, but only considers vectors whose metadata
    ``document_id`` matches. Used to surface the user's **latest** indexed upload
    even when global top-k retrieval ranks older documents higher.
    """
    doc_id = (document_id or "").strip()
    if top_k < 1 or not doc_id:
        return []

    q = await embedding_service.embed_query(query)
    qv = np.asarray(q[0], dtype=np.float32)

    with _lock:
        if _index is None and _INDEX_PATH.exists() and _META_PATH.exists():
            _load_from_disk_locked()
        if _index is None or _index.ntotal == 0:
            return []

        idxs = [i for i, row in enumerate(_meta) if (row.get("document_id") or "").strip() == doc_id]
        if not idxs:
            return []

        scores: list[tuple[float, int]] = []
        for i in idxs:
            v = np.asarray(_index.reconstruct(int(i)), dtype=np.float32)
            s = float(np.dot(qv, v))
            scores.append((s, i))

        scores.sort(key=lambda t: t[0], reverse=True)
        take = scores[: min(top_k, len(scores))]

    hits: list[RetrievedChunk] = []
    for score, idx in take:
        if idx < 0 or idx >= len(_meta):
            continue
        row = _meta[idx]
        hits.append(
            RetrievedChunk(
                document_id=row["document_id"],
                text=row["text"],
                score=float(score),
            )
        )
    return hits
