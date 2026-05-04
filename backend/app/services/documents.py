"""Extract text from PDF/TXT, chunk, and hold chunks in process memory (no vector DB)."""

from __future__ import annotations

import os
import uuid
from io import BytesIO
from typing import Final

from pypdf import PdfReader

_DEFAULT_CHUNK: Final = 1000
_DEFAULT_OVERLAP: Final = 150
_MAX_FILE_BYTES: Final = 15 * 1024 * 1024

# document_id -> list of chunk strings (cleared on process restart)
_chunks_by_document: dict[str, list[str]] = {}


def _chunk_max_chars() -> int:
    raw = os.environ.get("DOCUMENT_CHUNK_MAX_CHARS", str(_DEFAULT_CHUNK)).strip()
    try:
        n = int(raw)
        return max(200, min(n, 8000))
    except ValueError:
        return _DEFAULT_CHUNK


def _chunk_overlap() -> int:
    raw = os.environ.get("DOCUMENT_CHUNK_OVERLAP", str(_DEFAULT_OVERLAP)).strip()
    try:
        n = int(raw)
        return max(0, min(n, 2000))
    except ValueError:
        return _DEFAULT_OVERLAP


def extract_text(filename: str, raw: bytes) -> str:
    if len(raw) > _MAX_FILE_BYTES:
        msg = f"File too large (max {_MAX_FILE_BYTES // (1024 * 1024)} MB)."
        raise ValueError(msg)

    name = (filename or "").lower().strip()
    if name.endswith(".txt"):
        return raw.decode("utf-8", errors="replace").strip()

    if name.endswith(".pdf"):
        try:
            reader = PdfReader(BytesIO(raw))
        except Exception as e:
            raise ValueError(f"Could not open PDF (invalid or corrupted file): {e}") from e
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n\n".join(parts).strip()

    raise ValueError("Only .pdf and .txt are supported by this extractor (images are handled in the upload API).")


def chunk_text(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []

    max_chars = _chunk_max_chars()
    overlap = min(_chunk_overlap(), max_chars // 2)
    step = max(1, max_chars - overlap)

    chunks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        piece = text[i : i + max_chars].strip()
        if piece:
            chunks.append(piece)
        if i + max_chars >= n:
            break
        i += step

    return chunks


def store_document_chunks(chunks: list[str]) -> str:
    document_id = str(uuid.uuid4())
    _chunks_by_document[document_id] = chunks
    return document_id


def get_document_chunks(document_id: str) -> list[str] | None:
    """Return a copy of chunks for ``document_id``, or ``None`` if unknown."""
    stored = _chunks_by_document.get(document_id)
    if stored is None:
        return None
    return list(stored)
