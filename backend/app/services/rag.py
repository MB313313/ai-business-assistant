"""Retrieve chunks from FAISS, then answer with the LLM using injected context."""

from __future__ import annotations

import os
from typing import Final

from . import llm, vector_store

_DEFAULT_TOP_K: Final = 5


def rag_top_k() -> int:
    raw = os.environ.get("RAG_TOP_K", str(_DEFAULT_TOP_K)).strip()
    try:
        k = int(raw)
        return max(1, min(k, 20))
    except ValueError:
        return _DEFAULT_TOP_K


async def answer_with_rag(
    question: str,
    images: list[tuple[bytes, str]] | None = None,
) -> str:
    """
    1. Retrieve top ``RAG_TOP_K`` chunks (text query; expanded when only images are sent).
    2. Call the LLM with excerpts injected, plus optional user images for multimodal RAG.
    """
    imgs = images or []
    retrieval_q = question.strip()
    if not retrieval_q and imgs:
        retrieval_q = (
            "Policies, KPIs, charts, procedures, or handbook content that may relate to a user-supplied visual."
        )

    hits = await vector_store.retrieve_relevant_chunks(retrieval_q, rag_top_k())
    texts = [h["text"] for h in hits if h.get("text")]

    seen: set[str] = set()
    chunks: list[str] = []
    for t in texts:
        t = t.strip()
        if not t or t in seen:
            continue
        seen.add(t)
        chunks.append(t)

    return await llm.complete_rag_turn(chunks, question, images=imgs or None)


async def answer_with_rag_plus(
    question: str,
    *,
    extra_chunks: list[str] | None = None,
    images: list[tuple[bytes, str]] | None = None,
) -> str:
    """
    Like ``answer_with_rag``, but also injects additional excerpt chunks (e.g. from user-supplied files)
    into the LLM context alongside retrieved knowledge-base excerpts.
    """
    extras = [c.strip() for c in (extra_chunks or []) if c and c.strip()]
    imgs = images or []

    retrieval_q = question.strip()
    if not retrieval_q and imgs:
        retrieval_q = (
            "Policies, KPIs, charts, procedures, or handbook content that may relate to a user-supplied visual."
        )
    if not retrieval_q and extras:
        retrieval_q = "Questions related to the user-supplied attached documents."

    hits = await vector_store.retrieve_relevant_chunks(retrieval_q, rag_top_k())
    texts = [h["text"] for h in hits if h.get("text")]

    seen: set[str] = set()
    chunks: list[str] = []
    for t in texts:
        t = t.strip()
        if not t or t in seen:
            continue
        seen.add(t)
        chunks.append(t)

    for t in extras:
        if t in seen:
            continue
        seen.add(t)
        chunks.append(t)

    # Hard cap to keep prompts bounded.
    if len(chunks) > 20:
        chunks = chunks[:20]

    return await llm.complete_rag_turn(chunks, question, images=imgs or None)
