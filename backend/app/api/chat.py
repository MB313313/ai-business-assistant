from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from ..services import rag

router = APIRouter(tags=["chat"])

_MAX_IMAGES = 6
_MAX_IMAGE_BYTES = 4 * 1024 * 1024
_ALLOWED_MEDIA = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})


class ChatImagePart(BaseModel):
    media_type: str = Field(..., description="MIME type, e.g. image/png")
    base64_data: str = Field(..., description="Raw base64 without data: URL prefix")


class ChatRequest(BaseModel):
    message: str = Field("", max_length=32000)
    images: list[ChatImagePart] = Field(default_factory=list, max_length=_MAX_IMAGES)

    @model_validator(mode="after")
    def need_text_or_image(self) -> ChatRequest:
        if not self.message.strip() and not self.images:
            raise ValueError("Provide a non-empty message and/or at least one image.")
        return self


class ChatResponse(BaseModel):
    reply: str


def _decode_images(parts: list[ChatImagePart]) -> list[tuple[bytes, str]]:
    out: list[tuple[bytes, str]] = []
    for p in parts:
        mt = (p.media_type or "").strip().lower()
        if mt not in _ALLOWED_MEDIA:
            raise ValueError(f"Unsupported image type {mt!r}. Use JPEG, PNG, WebP, or GIF.")
        try:
            # ``standard_b64decode`` has no ``validate`` on all Python versions; ``b64decode`` does.
            raw = base64.b64decode(p.base64_data.strip(), validate=True)
        except (binascii.Error, ValueError) as e:
            raise ValueError("Invalid image encoding.") from e
        if len(raw) > _MAX_IMAGE_BYTES:
            raise ValueError(f"Each image must be at most {_MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
        out.append((raw, mt))
    return out


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    try:
        imgs = _decode_images(body.images) if body.images else []
        reply = await rag.answer_with_rag(body.message, images=imgs or None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        if "OPENAI_API_KEY" in str(e):
            raise HTTPException(status_code=503, detail=str(e)) from e
        raise HTTPException(status_code=502, detail=str(e)) from e
    return ChatResponse(reply=reply)
