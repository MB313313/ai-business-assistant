"""OpenAI text embeddings for vector search."""

from __future__ import annotations

import os
from typing import Final

import faiss
import numpy as np
from openai import APIError, AuthenticationError, OpenAIError

from .llm import get_async_openai_client

_DEFAULT_MODEL: Final = "text-embedding-3-small"
_BATCH: Final = 64


def embedding_model() -> str:
    return os.environ.get("OPENAI_EMBED_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL


async def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Embed many strings. Returns ``(n, dim)`` float32, L2-normalized for inner-product
    (cosine) search in FAISS.
    """
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)

    client = get_async_openai_client()
    model = embedding_model()
    vectors: list[list[float]] = []

    for start in range(0, len(texts), _BATCH):
        batch = texts[start : start + _BATCH]
        try:
            resp = await client.embeddings.create(model=model, input=batch)
        except AuthenticationError as e:
            raise RuntimeError("OpenAI authentication failed. Check OPENAI_API_KEY.") from e
        except APIError as e:
            raise RuntimeError(f"OpenAI embeddings error: {e}") from e
        except OpenAIError as e:
            raise RuntimeError(f"OpenAI embeddings failed: {e}") from e

        ordered = sorted(resp.data, key=lambda d: d.index)
        vectors.extend(d.embedding for d in ordered)

    arr = np.asarray(vectors, dtype=np.float32)
    if arr.ndim != 2 or arr.shape[0] != len(texts):
        raise RuntimeError("Unexpected embedding response shape from OpenAI.")

    faiss.normalize_L2(arr)
    return arr


async def embed_query(text: str) -> np.ndarray:
    """Single query embedding, shape ``(1, dim)``, L2-normalized."""
    arr = await embed_texts([text])
    return arr
