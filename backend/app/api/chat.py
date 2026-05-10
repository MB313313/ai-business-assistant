from __future__ import annotations

import base64
import binascii
import os
import tempfile
from io import BytesIO

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from ..db import db_session, utc_now
from ..models import ChatMessage, ChatThread, User, UserKnowledgeDocument
from ..services import documents, llm, rag

router = APIRouter(tags=["chat"])

_CHAT_HISTORY_MSG_LIMIT = 24
_MAX_IMAGES = 6
_MAX_IMAGE_BYTES = 4 * 1024 * 1024
_ALLOWED_MEDIA = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
_ALLOWED_VIDEO_SUFFIX = frozenset({".mp4", ".webm", ".mov"})
_ALLOWED_DOC_SUFFIX = frozenset({".pdf", ".txt", ".docx"})

_KB_REMINDER_SEPARATOR = "\n\n────────────────────────────────────────\n"
_KB_REMINDER_TEXT = (
    "Tip: Add your own PDFs, notes, or images to the knowledge base in the sidebar "
    "so answers can draw on your materials—not just general knowledge."
)

# Chat attachment limits (multipart). Keep these modest for reliability; override via env if needed.
_DEFAULT_FILE_MAX_BYTES = 25 * 1024 * 1024
_DEFAULT_TOTAL_MAX_BYTES = 100 * 1024 * 1024


def _conversation_history_for_llm(user_id: str, thread_id: str) -> list[dict[str, str]]:
    """Prior turns in the thread (oldest first), for multi-turn / pronoun resolution."""
    uid = (user_id or "").strip()
    tid = (thread_id or "").strip()
    if not uid or not tid:
        return []
    with db_session() as db:
        th = db.get(ChatThread, tid)
        if th is None or th.user_id != uid:
            return []
        rows = db.execute(
            select(ChatMessage)
            .where(ChatMessage.thread_id == tid)
            .order_by(ChatMessage.created_at.desc())
            .limit(_CHAT_HISTORY_MSG_LIMIT)
        ).scalars().all()
        ordered = list(reversed(rows))
        return [
            {"role": m.role, "content": (m.content or "").strip()}
            for m in ordered
            if m.role in ("user", "assistant") and (m.content or "").strip()
        ]


def _user_has_knowledge_uploads(user_id: str) -> bool:
    uid = (user_id or "").strip()
    if not uid:
        return False
    with db_session() as db:
        if db.get(User, uid) is None:
            return False
        n = db.execute(
            select(func.count())
            .select_from(UserKnowledgeDocument)
            .where(UserKnowledgeDocument.user_id == uid)
        ).scalar_one()
        return int(n or 0) > 0


def _append_kb_reminder_if_needed(reply: str, x_user_id: str | None) -> str:
    uid = (x_user_id or "").strip()
    if not uid or _user_has_knowledge_uploads(uid):
        return (reply or "").strip()
    base = (reply or "").strip()
    reminder = _KB_REMINDER_SEPARATOR + _KB_REMINDER_TEXT
    return base + reminder if base else _KB_REMINDER_TEXT.strip()


def _clean_title_seed(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    t = " ".join(t.split())
    if len(t) > 72:
        t = t[:72].rstrip() + "…"
    return t


def _finalize_chat_title(raw: str, fallback_seed: str) -> str:
    """Normalize LLM title output; fall back to a trimmed first-message seed."""
    t = (raw or "").strip().strip('"').strip("'").strip("\u201c\u201d\u2018\u2019")
    t = t.split("\n")[0].strip(" -•")
    t = " ".join(t.split())
    for prefix in ("Title:", "Conversation title:", "Thread:"):
        if t.lower().startswith(prefix.lower()):
            t = t[len(prefix) :].strip()
    if len(t) > 200:
        t = t[:200].rstrip() + "…"
    generic = frozenset(
        {"chat", "conversation", "new chat", "untitled", "message", "question", "help"}
    )
    if not t or t.lower() in generic:
        return _clean_title_seed(fallback_seed)
    return t


async def _apply_thread_title_first_turn(
    th: ChatThread,
    user_for_title: str,
    assistant_reply: str,
) -> None:
    """First exchange only (caller checks): summary-style title, not a verbatim copy of the user text."""
    if (th.title or "").strip() not in ("Chat", ""):
        return
    seed = (user_for_title or "").strip()
    try:
        raw = await llm.suggest_chat_title(seed, (assistant_reply or "").strip())
        title = _finalize_chat_title(raw, seed)
        if title:
            th.title = title[:200]
    except Exception:
        fb = _clean_title_seed(seed)
        if fb:
            th.title = fb[:200]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _chat_file_max_bytes() -> int:
    return max(1 * 1024 * 1024, min(_env_int("CHAT_FILE_MAX_BYTES", _DEFAULT_FILE_MAX_BYTES), 500 * 1024 * 1024))


def _chat_total_max_bytes() -> int:
    return max(1 * 1024 * 1024, min(_env_int("CHAT_FILES_TOTAL_MAX_BYTES", _DEFAULT_TOTAL_MAX_BYTES), 1024 * 1024 * 1024))


def _suffix(filename: str) -> str:
    name = (filename or "").strip().lower()
    if "." not in name:
        return ""
    return name[name.rfind(".") :]


def _video_first_frame_png(video_bytes: bytes) -> bytes | None:
    """Return PNG bytes for the first video frame, or ``None`` if conversion fails."""
    try:
        import imageio.v3 as iio
        import numpy as np
        from PIL import Image
    except Exception:
        return None

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(video_bytes)
        path = tmp.name
    try:
        frame = iio.imread(path, index=0)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        return None
    try:
        os.unlink(path)
    except OSError:
        pass

    try:
        img = Image.fromarray(np.asarray(frame)).convert("RGB")
        bio = BytesIO()
        img.save(bio, format="PNG")
        return bio.getvalue()
    except Exception:
        return None


def _extract_docx_text(raw: bytes) -> str:
    try:
        from docx import Document  # type: ignore
    except Exception as e:
        raise RuntimeError("DOCX support requires python-docx. Install dependencies and try again.") from e
    doc = Document(BytesIO(raw))
    parts: list[str] = []
    for p in doc.paragraphs:
        t = (p.text or "").strip()
        if t:
            parts.append(t)
    return "\n".join(parts).strip()


class ChatImagePart(BaseModel):
    media_type: str = Field(..., description="MIME type, e.g. image/png")
    base64_data: str = Field(..., description="Raw base64 without data: URL prefix")


class ChatRequest(BaseModel):
    message: str = Field("", max_length=32000)
    images: list[ChatImagePart] = Field(default_factory=list, max_length=_MAX_IMAGES)
    thread_id: str | None = Field(default=None, description="Optional: save this turn into a chat thread")

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
async def chat(
    body: ChatRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> ChatResponse:
    try:
        imgs = _decode_images(body.images) if body.images else []
        hist = _conversation_history_for_llm((x_user_id or "").strip(), (body.thread_id or "").strip())
        reply = await rag.answer_with_rag(
            body.message,
            images=imgs or None,
            conversation_history=hist or None,
            user_id=(x_user_id or "").strip() or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        if "OPENAI_API_KEY" in str(e):
            raise HTTPException(status_code=503, detail=str(e)) from e
        raise HTTPException(status_code=502, detail=str(e)) from e

    reply = _append_kb_reminder_if_needed(reply, x_user_id)

    # Optional persistence: only when both X-User-Id and thread_id are provided
    if (x_user_id or "").strip() and (body.thread_id or "").strip():
        uid = (x_user_id or "").strip()
        tid = (body.thread_id or "").strip()
        with db_session() as db:
            u = db.get(User, uid)
            th = db.get(ChatThread, tid)
            if u is not None and th is not None and th.user_id == uid:
                prev_users = db.execute(
                    select(func.count()).select_from(ChatMessage).where(
                        ChatMessage.thread_id == tid, ChatMessage.role == "user"
                    )
                ).scalar_one()
                now = utc_now()
                user_text = (body.message or "").strip()
                db.add(ChatMessage(thread_id=tid, role="user", content=user_text, created_at=now))
                db.add(ChatMessage(thread_id=tid, role="assistant", content=(reply or "").strip(), created_at=now))
                th.updated_at = now
                if int(prev_users or 0) == 0 and (th.title or "").strip() in ("Chat", ""):
                    await _apply_thread_title_first_turn(th, user_text, reply)
                db.commit()
    return ChatResponse(reply=reply)


@router.post("/chat-with-files", response_model=ChatResponse)
async def chat_with_files(
    message: str = Form(""),
    files: list[UploadFile] = File(default_factory=list),
    thread_id: str = Form(""),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> ChatResponse:
    try:
        if not message.strip() and not files:
            raise ValueError("Provide a non-empty message and/or at least one file.")

        imgs: list[tuple[bytes, str]] = []
        extra_chunks: list[str] = []
        total_bytes = 0
        per_file_max = _chat_file_max_bytes()
        total_max = _chat_total_max_bytes()

        for f in files:
            name = (f.filename or "").strip() or "attachment"
            suf = _suffix(name)
            raw = await f.read()
            if not raw:
                continue
            if len(raw) > per_file_max:
                raise ValueError(
                    f"File {name!r} is too large (max {per_file_max // (1024 * 1024)} MB per file)."
                )
            total_bytes += len(raw)
            if total_bytes > total_max:
                raise ValueError(
                    f"Attachments are too large in total (max {total_max // (1024 * 1024)} MB per message)."
                )

            ct = (f.content_type or "").lower().strip()

            # Images
            if ct in _ALLOWED_MEDIA:
                if len(raw) > _MAX_IMAGE_BYTES:
                    raise ValueError(f"Each image must be at most {_MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
                imgs.append((raw, ct))
                continue

            # Video → first frame
            if ct.startswith("video/") or suf in _ALLOWED_VIDEO_SUFFIX:
                png = _video_first_frame_png(raw)
                if png is None:
                    raise ValueError("Could not read that video. Try a smaller MP4/WebM/MOV or upload a screenshot.")
                if len(png) > _MAX_IMAGE_BYTES:
                    raise ValueError("Video frame is too large after conversion. Try a smaller clip.")
                imgs.append((png, "image/png"))
                continue

            # Documents (text extraction)
            if suf in _ALLOWED_DOC_SUFFIX or ct in (
                "application/pdf",
                "text/plain",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ):
                if suf == ".docx" or ct.endswith("wordprocessingml.document"):
                    text = _extract_docx_text(raw)
                else:
                    text = documents.extract_text(name, raw)
                if text.strip():
                    for chunk in documents.chunk_text(text):
                        extra_chunks.append(f"[User attachment: {name}]\n{chunk}")
                continue

            raise ValueError(
                f"Unsupported attachment type for {name!r}. "
                "Use images (PNG/JPG/WebP/GIF), videos (MP4/WebM/MOV), or documents (PDF/TXT/DOCX)."
            )

        q = message
        if not q.strip() and extra_chunks and not imgs:
            q = "Summarize the attached document(s) and extract the key business-relevant points."

        hist = _conversation_history_for_llm((x_user_id or "").strip(), thread_id.strip())
        reply = await rag.answer_with_rag_plus(
            q,
            extra_chunks=extra_chunks,
            images=imgs or None,
            conversation_history=hist or None,
            user_id=(x_user_id or "").strip() or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        if "OPENAI_API_KEY" in str(e):
            raise HTTPException(status_code=503, detail=str(e)) from e
        raise HTTPException(status_code=502, detail=str(e)) from e

    reply = _append_kb_reminder_if_needed(reply, x_user_id)

    if (x_user_id or "").strip() and thread_id.strip():
        uid = (x_user_id or "").strip()
        tid = thread_id.strip()
        with db_session() as db:
            u = db.get(User, uid)
            th = db.get(ChatThread, tid)
            if u is not None and th is not None and th.user_id == uid:
                prev_users = db.execute(
                    select(func.count()).select_from(ChatMessage).where(
                        ChatMessage.thread_id == tid, ChatMessage.role == "user"
                    )
                ).scalar_one()
                now = utc_now()
                # Store the visible user message (not the extracted chunks)
                display = (message or "").strip() or ("*Question with attachment*" if files else "")
                db.add(ChatMessage(thread_id=tid, role="user", content=display, created_at=now))
                db.add(ChatMessage(thread_id=tid, role="assistant", content=(reply or "").strip(), created_at=now))
                th.updated_at = now
                if int(prev_users or 0) == 0 and (th.title or "").strip() in ("Chat", ""):
                    await _apply_thread_title_first_turn(th, display, reply)
                db.commit()
    return ChatResponse(reply=reply)
