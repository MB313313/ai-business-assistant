"""Short vision captions for PDF figures (indexing) and helpers."""

from __future__ import annotations

import base64
import os
from typing import Final

import fitz  # PyMuPDF
from openai import APIError, AuthenticationError, OpenAIError

from .llm import get_async_openai_client

_DEFAULT_CAPTION_MODEL: Final = "gpt-4o-mini"
_MAX_PDF_IMAGES: Final = 8


def _caption_model() -> str:
    return os.environ.get("OPENAI_VISION_MODEL", _DEFAULT_CAPTION_MODEL).strip() or _DEFAULT_CAPTION_MODEL


def _max_pdf_images() -> int:
    raw = os.environ.get("PDF_VISION_MAX_IMAGES", str(_MAX_PDF_IMAGES)).strip()
    try:
        return max(0, min(int(raw), 24))
    except ValueError:
        return _MAX_PDF_IMAGES


def _mime_from_ext(ext: str) -> str:
    ext = (ext or "png").lower().lstrip(".")
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(ext, "image/png")


def mime_for_document_suffix(suffix: str) -> str:
    """Map a filename suffix (``'.png'`` or ``'png'``) to an image MIME type."""
    return _mime_from_ext(suffix)


async def describe_image_for_indexing(image_bytes: bytes, media_type: str) -> str:
    """One short description for search / RAG text (not full analysis)."""
    client = get_async_openai_client()
    model = _caption_model()
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    url = f"data:{media_type};base64,{b64}"
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Describe this business image in 1–3 short sentences for search indexing. "
                                "Mention charts, axes labels, KPIs, or diagram types if visible. "
                                "If it is a logo or decoration with no business data, say so briefly."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": url}},
                    ],
                }
            ],
            max_tokens=220,
        )
    except AuthenticationError as e:
        raise RuntimeError("OpenAI authentication failed. Check OPENAI_API_KEY.") from e
    except APIError as e:
        raise RuntimeError(f"OpenAI vision error: {e}") from e
    except OpenAIError as e:
        raise RuntimeError(f"OpenAI vision failed: {e}") from e

    return (resp.choices[0].message.content or "").strip()


async def describe_pdf_embedded_images(pdf_bytes: bytes) -> list[str]:
    """Extract embedded raster images from a PDF and return short captions (bounded count)."""
    max_n = _max_pdf_images()
    if max_n == 0:
        return []

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    captions: list[str] = []
    seen_xrefs: set[int] = set()

    try:
        for page in doc:
            for img in page.get_images(full=True):
                xref = int(img[0])
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                try:
                    info = doc.extract_image(xref)
                except Exception:
                    continue
                w = int(info.get("width") or 0)
                h = int(info.get("height") or 0)
                if w < 48 or h < 48:
                    continue
                raw = info.get("image") or b""
                if not raw:
                    continue
                ext = str(info.get("ext") or "png")
                mime = _mime_from_ext(ext)
                try:
                    cap = await describe_image_for_indexing(raw, mime)
                except RuntimeError:
                    continue
                if cap:
                    captions.append(cap)
                if len(captions) >= max_n:
                    return captions
    finally:
        doc.close()

    return captions
