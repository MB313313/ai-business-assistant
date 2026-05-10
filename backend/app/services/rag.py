"""Retrieve chunks from FAISS, then answer with the LLM using injected context."""

from __future__ import annotations

import os
from typing import Any, Final

from sqlalchemy import select

from ..db import db_session
from ..models import User, UserKnowledgeDocument
from . import llm, vector_store

_DEFAULT_TOP_K: Final = 5
_DEFAULT_LATEST_DOC_TOP_K: Final = 6


def _retrieval_query(question: str, prior_messages: list[dict[str, Any]] | None) -> str:
    """Blend recent user turns into the retrieval query so short follow-ups stay on-topic."""
    q = question.strip()
    if not q or not prior_messages:
        return q
    if len(q) > 160:
        return q
    last_user = ""
    for m in reversed(prior_messages):
        if m.get("role") == "user":
            last_user = (m.get("content") or "").strip()
            break
    if not last_user:
        return q
    if len(last_user) > 700:
        last_user = last_user[:700].rstrip() + "…"
    return f"{last_user}\n\nFollow-up: {q}"


def rag_top_k() -> int:
    raw = os.environ.get("RAG_TOP_K", str(_DEFAULT_TOP_K)).strip()
    try:
        k = int(raw)
        return max(1, min(k, 20))
    except ValueError:
        return _DEFAULT_TOP_K


def _rag_latest_doc_top_k() -> int:
    raw = os.environ.get("RAG_LATEST_DOC_TOP_K", str(_DEFAULT_LATEST_DOC_TOP_K)).strip()
    try:
        k = int(raw)
        return max(1, min(k, 20))
    except ValueError:
        return _DEFAULT_LATEST_DOC_TOP_K


def _last_indexed_document_id_for_user(user_id: str | None) -> str | None:
    uid = (user_id or "").strip()
    if not uid:
        return None
    with db_session() as db:
        u = db.get(User, uid)
        if u is None:
            return None
        did = (u.last_indexed_document_id or "").strip()
        return did or None


def _indexed_document_ids_for_user(user_id: str | None) -> frozenset[str] | None:
    """
    ``None`` → no ``user_id`` (retrieve from the whole shared index, legacy behavior).
    Empty frozenset → user exists but has no rows in ``user_knowledge_documents`` (no KB chunks).
    Non-empty → restrict retrieval to these ``document_id`` values (matches the DB).
    """
    uid = (user_id or "").strip()
    if not uid:
        return None
    with db_session() as db:
        if db.get(User, uid) is None:
            return frozenset()
        rows = db.execute(
            select(UserKnowledgeDocument.document_id).where(UserKnowledgeDocument.user_id == uid)
        ).scalars().all()
        return frozenset((r or "").strip() for r in rows if (r or "").strip())


async def _knowledge_chunks_for_query(
    retrieval_q: str,
    user_id: str | None,
    global_top_k: int,
) -> tuple[list[str], set[str]]:
    """
    When ``user_id`` is set, only chunks whose ``document_id`` is in ``user_knowledge_documents``
    are retrieved (same scope as the DB). Otherwise the shared FAISS index is searched globally.

    Also boosts the user's **last indexed** document so a fresh upload is not drowned out
    among their own older files.
    """
    doc_scope = _indexed_document_ids_for_user(user_id)
    last_doc = _last_indexed_document_id_for_user(user_id)

    prio_hits: list[vector_store.RetrievedChunk] = []
    if last_doc and doc_scope is not None and len(doc_scope) > 0 and last_doc in doc_scope:
        prio_hits = await vector_store.retrieve_relevant_chunks_for_document(
            retrieval_q, last_doc, _rag_latest_doc_top_k()
        )

    if doc_scope is None:
        hits = await vector_store.retrieve_relevant_chunks(retrieval_q, global_top_k)
    elif len(doc_scope) == 0:
        hits = []
    else:
        hits = await vector_store.retrieve_relevant_chunks_scoped(
            retrieval_q, global_top_k, doc_scope
        )

    seen: set[str] = set()
    chunks: list[str] = []

    if prio_hits:
        texts = [(h.get("text") or "").strip() for h in prio_hits if h.get("text")]
        texts = [t for t in texts if t]
        if texts:
            bundle = "\n\n".join(texts)
            chunks.append(
                "[Most recently indexed knowledge — prefer this when the user refers to their latest upload, "
                "a new design, screenshots, or what they just added to the knowledge base:]\n\n" + bundle
            )
            seen.update(texts)

    for h in hits:
        t = (h.get("text") or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        chunks.append(t)

    return chunks, seen


async def answer_with_rag(
    question: str,
    images: list[tuple[bytes, str]] | None = None,
    *,
    conversation_history: list[dict[str, Any]] | None = None,
    user_id: str | None = None,
) -> str:
    """
    1. Retrieve top ``RAG_TOP_K`` chunks (text query; expanded when only images are sent).
    2. Call the LLM with excerpts injected, plus optional user images for multimodal RAG.
    """
    imgs = images or []
    hist = conversation_history or []
    retrieval_q = question.strip()
    if not retrieval_q and imgs:
        retrieval_q = (
            "Policies, KPIs, charts, procedures, or handbook content that may relate to a user-supplied visual."
        )
    elif retrieval_q and hist:
        blended = _retrieval_query(question, hist)
        if blended.strip():
            retrieval_q = blended

    chunks, _seen = await _knowledge_chunks_for_query(retrieval_q, user_id, rag_top_k())

    return await llm.complete_hybrid_rag_turn(
        chunks, question, images=imgs or None, conversation_history=hist or None
    )


async def answer_with_rag_plus(
    question: str,
    *,
    extra_chunks: list[str] | None = None,
    images: list[tuple[bytes, str]] | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
    user_id: str | None = None,
) -> str:
    """
    Like ``answer_with_rag``, but also injects additional excerpt chunks (e.g. from user-supplied files)
    into the LLM context alongside retrieved knowledge-base excerpts.
    """
    extras = [c.strip() for c in (extra_chunks or []) if c and c.strip()]
    imgs = images or []
    hist = conversation_history or []

    retrieval_q = question.strip()
    if not retrieval_q and imgs:
        retrieval_q = (
            "Policies, KPIs, charts, procedures, or handbook content that may relate to a user-supplied visual."
        )
    if not retrieval_q and extras:
        retrieval_q = "Questions related to the user-supplied attached documents."
    if retrieval_q and hist:
        blended = _retrieval_query(question, hist)
        if blended.strip():
            retrieval_q = blended

    chunks, seen = await _knowledge_chunks_for_query(retrieval_q, user_id, rag_top_k())

    for t in extras:
        if t in seen:
            continue
        seen.add(t)
        chunks.append(t)

    # Hard cap to keep prompts bounded.
    if len(chunks) > 20:
        chunks = chunks[:20]

    return await llm.complete_hybrid_rag_turn(
        chunks, question, images=imgs or None, conversation_history=hist or None
    )
