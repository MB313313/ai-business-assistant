"""LLM calls: OpenAI first; optional Gemini fallback on quota / rate limits."""

import asyncio
import base64
import os
from io import BytesIO
from collections.abc import Awaitable, Callable
from typing import Any, Final

from openai import APIError, AsyncOpenAI, AuthenticationError, OpenAIError

_SYSTEM: Final = (
    "You are a concise, professional AI business assistant. "
    "Answer clearly; if you lack information, say so."
)

_SYSTEM_RAG: Final = (
    "You are a business assistant. You must base factual answers ONLY on the DOCUMENT "
    "EXCERPTS inside the user message. Do not invent policies, numbers, or document "
    "content that are not supported by those excerpts. If the excerpts do not contain "
    "the answer, say clearly that the provided documents do not contain enough information."
)

_SYSTEM_RAG_MULTI_TURN: Final = (
    " Earlier turns in this conversation may clarify pronouns (e.g. he/she/it/they) or very short follow-ups; "
    "use them to interpret what the user means. Still ground claims about company documents only in the excerpts "
    "in the latest user message."
)

_SYSTEM_HYBRID: Final = (
    "You are a capable general assistant (similar to ChatGPT). "
    "Answer helpfully and accurately. "
    "When the user message includes KNOWLEDGE-BASE EXCERPTS from their uploaded documents, use them for "
    "organization-specific or document-grounded facts when they clearly apply. "
    "Excerpts introduced as “most recently indexed knowledge” are the user's latest upload—prefer them when "
    "the user asks about something new, a design they just added, or their last knowledge-base update. "
    "Do not invent content that appears to come from those documents if it is not supported by the excerpts. "
    "For general questions, answer from broad knowledge even when excerpts are missing or irrelevant."
)

_SYSTEM_HYBRID_MULTI_TURN: Final = (
    " Earlier turns may clarify pronouns or short follow-ups; use them for interpretation. "
    "Still do not attribute document details unless the excerpts support them."
)

_DEFAULT_OPENAI_MODEL: Final = "gpt-4o-mini"
_DEFAULT_GEMINI_MODEL: Final = "gemini-2.0-flash"

_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            msg = "OPENAI_API_KEY is missing or empty. Set it in `.env` at the project root."
            raise RuntimeError(msg)
        _openai_client = AsyncOpenAI(api_key=key)
    return _openai_client


def get_async_openai_client() -> AsyncOpenAI:
    """Shared OpenAI client for chat and embeddings."""
    return _get_openai_client()


def chat_model() -> str:
    return os.environ.get("OPENAI_CHAT_MODEL", _DEFAULT_OPENAI_MODEL).strip() or _DEFAULT_OPENAI_MODEL


def _gemini_key_present() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def _openai_quota_like(exc: BaseException) -> bool:
    if isinstance(exc, APIError):
        if getattr(exc, "status_code", None) == 429:
            return True
        if getattr(exc, "code", None) == "insufficient_quota":
            return True
        low = str(exc).lower()
        if "insufficient_quota" in low or "rate_limit" in low:
            return True
    return False


async def _openai_chat_messages(messages: list[dict[str, Any]]) -> str:
    client = _get_openai_client()
    model = chat_model()
    response = await client.chat.completions.create(model=model, messages=messages)
    choice = response.choices[0].message
    return (choice.content or "").strip()


async def _openai_chat_messages_title(messages: list[dict[str, Any]]) -> str:
    """Short, cheap completion for sidebar thread titles."""
    client = _get_openai_client()
    model = chat_model()
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=48,
        temperature=0.35,
    )
    choice = response.choices[0].message
    return (choice.content or "").strip()


_SYSTEM_CHAT_TITLE: Final = (
    "You label chat threads for a sidebar (like ChatGPT). "
    "Output ONLY a short conversation title: typically 2–6 words, plain text, no quotes, "
    "no trailing punctuation, no emojis. Capture the topic or intent, not the user's exact wording. "
    "Examples: user says 'hello' → Greeting exchange; user asks about PTO policy → PTO policy question"
)


async def suggest_chat_title(user_message: str, assistant_reply: str) -> str:
    """
    Return a concise, human-style title for a new conversation from the first exchange.
    Uses OpenAI with optional Gemini fallback on quota-style errors.
    """
    u = (user_message or "").strip() or "(no user text)"
    a = (assistant_reply or "").strip() or "(no assistant reply yet)"
    if len(a) > 900:
        a = a[:900].rstrip() + "…"
    user_payload = (
        f"User message:\n{u}\n\nAssistant reply (may be long — use only to infer topic):\n{a}\n\n"
        "Conversation title (respond with nothing else):"
    )
    openai_messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM_CHAT_TITLE},
        {"role": "user", "content": user_payload},
    ]
    return await _llm_with_openai_fallback_to_gemini(
        openai_messages,
        _SYSTEM_CHAT_TITLE,
        user_payload,
        openai_caller=_openai_chat_messages_title,
    )


async def _openai_complete(user_message: str) -> str:
    return await _openai_chat_messages(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_message},
        ]
    )


def _rag_user_content(context_chunks: list[str], question: str) -> str:
    if context_chunks:
        excerpts = "\n\n".join(
            f"[excerpt {i + 1}]\n{chunk.strip()}" for i, chunk in enumerate(context_chunks)
        )
        return (
            "The following are the ONLY document excerpts you may use.\n\n"
            f"{excerpts}\n\n"
            f"Question:\n{question.strip()}\n\n"
            "Answer using only information supported by the excerpts above."
        )
    return (
        "STATUS: No relevant document excerpts were retrieved from the indexed knowledge base.\n\n"
        f"Question:\n{question.strip()}\n\n"
        "Explain briefly that no matching material was found in the indexed documents, "
        "and that you cannot answer from company documents without relevant excerpts. "
        "Do not fabricate document content."
    )


def _hybrid_user_content(context_chunks: list[str], question: str) -> str:
    q = question.strip()
    if context_chunks:
        excerpts = "\n\n".join(
            f"[excerpt {i + 1}]\n{chunk.strip()}" for i, chunk in enumerate(context_chunks)
        )
        return (
            "KNOWLEDGE-BASE EXCERPTS (optional context — use when relevant; ignore when off-topic):\n\n"
            f"{excerpts}\n\n"
            f"User question:\n{q if q else '(See attached images if any.)'}"
        )
    return f"User question:\n{q if q else '(See attached images if any.)'}"


async def _gemini_rag_with_images(
    system_instruction: str,
    user_text: str,
    images: list[tuple[bytes, str]],
) -> str:
    import google.generativeai as genai
    from PIL import Image

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set; cannot use Gemini fallback with images.")

    genai.configure(api_key=key)
    name = os.environ.get("GEMINI_CHAT_MODEL", _DEFAULT_GEMINI_MODEL).strip() or _DEFAULT_GEMINI_MODEL
    model = genai.GenerativeModel(name, system_instruction=system_instruction)

    parts: list[Any] = [user_text + "\n\n(Attached images follow.)"]
    for raw, _mime in images:
        parts.append(Image.open(BytesIO(raw)).convert("RGB"))

    try:
        gen_async = getattr(model, "generate_content_async", None)
        if gen_async is not None:
            resp = await gen_async(parts)
        else:
            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(None, lambda: model.generate_content(parts))
    except Exception as e:
        raise RuntimeError(f"Gemini multimodal request failed: {e}") from e

    try:
        text = (resp.text or "").strip()
    except ValueError:
        text = ""
    return text


async def _gemini_with_system(system_instruction: str, user_message: str) -> str:
    import google.generativeai as genai

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set; cannot use Gemini fallback.")

    genai.configure(api_key=key)
    name = os.environ.get("GEMINI_CHAT_MODEL", _DEFAULT_GEMINI_MODEL).strip() or _DEFAULT_GEMINI_MODEL
    model = genai.GenerativeModel(name, system_instruction=system_instruction)

    try:
        gen_async = getattr(model, "generate_content_async", None)
        if gen_async is not None:
            resp = await gen_async(user_message)
        else:
            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(None, lambda: model.generate_content(user_message))
    except Exception as e:
        raise RuntimeError(f"Gemini request failed: {e}") from e

    try:
        text = (resp.text or "").strip()
    except ValueError:
        text = ""
    return text


async def _gemini_complete(user_message: str) -> str:
    return await _gemini_with_system(_SYSTEM, user_message)


async def _llm_with_openai_fallback_to_gemini(
    openai_messages: list[dict[str, Any]],
    gemini_system: str,
    gemini_user: str,
    *,
    openai_caller: Callable[[list[dict[str, Any]]], Awaitable[str]] | None = None,
) -> str:
    caller = openai_caller or _openai_chat_messages
    try:
        return await caller(openai_messages)
    except AuthenticationError as e:
        raise RuntimeError("OpenAI authentication failed. Check OPENAI_API_KEY.") from e
    except APIError as e:
        if _openai_quota_like(e) and _gemini_key_present():
            return await _gemini_with_system(gemini_system, gemini_user)
        raise RuntimeError(f"OpenAI API error: {e}") from e
    except OpenAIError as e:
        if _openai_quota_like(e) and _gemini_key_present():
            return await _gemini_with_system(gemini_system, gemini_user)
        raise RuntimeError(f"OpenAI request failed: {e}") from e


async def complete_chat(user_message: str) -> str:
    """
    Single-turn chat (no retrieval). Tries OpenAI; on quota / rate-limit style errors,
    uses Gemini if ``GEMINI_API_KEY`` is set.
    """
    return await _llm_with_openai_fallback_to_gemini(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_message},
        ],
        _SYSTEM,
        user_message,
    )


def _normalize_conversation_history(
    raw: list[dict[str, Any]] | None,
    *,
    max_messages: int = 24,
    max_chars: int = 4000,
) -> list[dict[str, str]]:
    if not raw:
        return []
    out: list[dict[str, str]] = []
    for m in raw[-max_messages:]:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        c = (m.get("content") or "").strip()
        if not c:
            continue
        if len(c) > max_chars:
            c = c[:max_chars].rstrip() + "…"
        out.append({"role": str(role), "content": c})
    return out


def _history_preamble_for_gemini(prior: list[dict[str, str]]) -> str:
    if not prior:
        return ""
    lines: list[str] = []
    for m in prior:
        label = "User" if m["role"] == "user" else "Assistant"
        lines.append(f"{label}: {m['content']}")
    return "Prior conversation:\n" + "\n\n".join(lines) + "\n\n---\n\n"


async def complete_hybrid_rag_turn(
    context_chunks: list[str],
    question: str,
    images: list[tuple[bytes, str]] | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
) -> str:
    """
    Like ``complete_rag_turn`` but allows general knowledge; knowledge-base excerpts are optional context.
    """
    imgs = images or []
    prior = _normalize_conversation_history(conversation_history)
    q = question.strip()
    if not q and imgs:
        q = (
            "The user attached image(s) but no text. Summarize what the image(s) show and relate "
            "them to the knowledge-base excerpts when possible; otherwise describe generally."
        )

    user_core = _hybrid_user_content(context_chunks, q)
    hybrid_system = _SYSTEM_HYBRID + (_SYSTEM_HYBRID_MULTI_TURN if prior else "")
    vision_system = (
        hybrid_system
        + " The user may attach images; use them together with any knowledge-base excerpts when answering."
    )
    gemini_prefix = _history_preamble_for_gemini(prior)

    if not imgs:
        messages: list[dict[str, Any]] = [{"role": "system", "content": hybrid_system}]
        for m in prior:
            messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_core})
        gemini_user = gemini_prefix + user_core if gemini_prefix else user_core
        return await _llm_with_openai_fallback_to_gemini(messages, hybrid_system, gemini_user)

    user_text = user_core + (
        "\n\nThe user also attached one or more images with their question. "
        "Use the images together with any knowledge-base excerpts when answering."
    )
    parts: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    for raw, mt in imgs:
        b64 = base64.standard_b64encode(raw).decode("ascii")
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mt};base64,{b64}"}})
    messages = [{"role": "system", "content": vision_system}]
    for m in prior:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": parts})

    gemini_user_text = gemini_prefix + user_text if gemini_prefix else user_text

    try:
        return await _openai_chat_messages(messages)
    except AuthenticationError as e:
        raise RuntimeError("OpenAI authentication failed. Check OPENAI_API_KEY.") from e
    except APIError as e:
        if _openai_quota_like(e) and _gemini_key_present():
            return await _gemini_rag_with_images(vision_system, gemini_user_text, imgs)
        raise RuntimeError(f"OpenAI API error: {e}") from e
    except OpenAIError as e:
        if _openai_quota_like(e) and _gemini_key_present():
            return await _gemini_rag_with_images(vision_system, gemini_user_text, imgs)
        raise RuntimeError(f"OpenAI request failed: {e}") from e


async def complete_rag_turn(
    context_chunks: list[str],
    question: str,
    images: list[tuple[bytes, str]] | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
) -> str:
    """
    RAG: ``context_chunks`` are injected into the user message; the model must ground
    answers in those excerpts (or state that none apply). Optional ``images`` are
    (bytes, media_type) pairs sent to a vision-capable chat model together with text.
    """
    imgs = images or []
    prior = _normalize_conversation_history(conversation_history)
    q = question.strip()
    if not q and imgs:
        q = (
            "The user attached image(s) but no text. Summarize what the image(s) show and relate "
            "them to the document excerpts when possible."
        )

    user_core = _rag_user_content(context_chunks, q)
    rag_system = _SYSTEM_RAG + (_SYSTEM_RAG_MULTI_TURN if prior else "")
    vision_system = (
        rag_system
        + " The user may attach images; use them together with the document excerpts when answering."
    )
    gemini_prefix = _history_preamble_for_gemini(prior)

    if not imgs:
        messages: list[dict[str, Any]] = [{"role": "system", "content": rag_system}]
        for m in prior:
            messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_core})
        gemini_user = gemini_prefix + user_core if gemini_prefix else user_core
        return await _llm_with_openai_fallback_to_gemini(messages, rag_system, gemini_user)

    user_text = user_core + (
        "\n\nThe user also attached one or more images with their question. "
        "Use the images together with the document excerpts when answering."
    )
    parts: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    for raw, mt in imgs:
        b64 = base64.standard_b64encode(raw).decode("ascii")
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mt};base64,{b64}"}})
    messages = [{"role": "system", "content": vision_system}]
    for m in prior:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": parts})

    gemini_user_text = gemini_prefix + user_text if gemini_prefix else user_text

    try:
        return await _openai_chat_messages(messages)
    except AuthenticationError as e:
        raise RuntimeError("OpenAI authentication failed. Check OPENAI_API_KEY.") from e
    except APIError as e:
        if _openai_quota_like(e) and _gemini_key_present():
            return await _gemini_rag_with_images(vision_system, gemini_user_text, imgs)
        raise RuntimeError(f"OpenAI API error: {e}") from e
    except OpenAIError as e:
        if _openai_quota_like(e) and _gemini_key_present():
            return await _gemini_rag_with_images(vision_system, gemini_user_text, imgs)
        raise RuntimeError(f"OpenAI request failed: {e}") from e
