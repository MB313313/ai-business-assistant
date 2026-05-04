"""LLM calls: OpenAI first; optional Gemini fallback on quota / rate limits."""

import asyncio
import base64
import os
from io import BytesIO
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
) -> str:
    try:
        return await _openai_chat_messages(openai_messages)
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


async def complete_rag_turn(
    context_chunks: list[str],
    question: str,
    images: list[tuple[bytes, str]] | None = None,
) -> str:
    """
    RAG: ``context_chunks`` are injected into the user message; the model must ground
    answers in those excerpts (or state that none apply). Optional ``images`` are
    (bytes, media_type) pairs sent to a vision-capable chat model together with text.
    """
    imgs = images or []
    q = question.strip()
    if not q and imgs:
        q = (
            "The user attached image(s) but no text. Summarize what the image(s) show and relate "
            "them to the document excerpts when possible."
        )

    user_core = _rag_user_content(context_chunks, q)
    vision_system = (
        _SYSTEM_RAG
        + " The user may attach images; use them together with the document excerpts when answering."
    )

    if not imgs:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_RAG},
            {"role": "user", "content": user_core},
        ]
        return await _llm_with_openai_fallback_to_gemini(messages, _SYSTEM_RAG, user_core)

    user_text = user_core + (
        "\n\nThe user also attached one or more images with their question. "
        "Use the images together with the document excerpts when answering."
    )
    parts: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    for raw, mt in imgs:
        b64 = base64.standard_b64encode(raw).decode("ascii")
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mt};base64,{b64}"}})
    messages = [{"role": "system", "content": vision_system}, {"role": "user", "content": parts}]

    try:
        return await _openai_chat_messages(messages)
    except AuthenticationError as e:
        raise RuntimeError("OpenAI authentication failed. Check OPENAI_API_KEY.") from e
    except APIError as e:
        if _openai_quota_like(e) and _gemini_key_present():
            return await _gemini_rag_with_images(vision_system, user_text, imgs)
        raise RuntimeError(f"OpenAI API error: {e}") from e
    except OpenAIError as e:
        if _openai_quota_like(e) and _gemini_key_present():
            return await _gemini_rag_with_images(vision_system, user_text, imgs)
        raise RuntimeError(f"OpenAI request failed: {e}") from e
