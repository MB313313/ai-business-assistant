from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..db import db_session, utc_now
from ..models import ChatMessage, ChatThread, User

router = APIRouter(tags=["chats"])


def _require_user_id(x_user_id: str | None) -> str:
    uid = (x_user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Missing X-User-Id header.")
    return uid


class CreateThreadResponse(BaseModel):
    thread_id: str


@router.post("/chats", response_model=CreateThreadResponse)
async def create_thread(x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> CreateThreadResponse:
    uid = _require_user_id(x_user_id)
    with db_session() as db:
        u = db.get(User, uid)
        if u is None:
            raise HTTPException(status_code=401, detail="Unknown user.")
        th = ChatThread(user_id=uid, title="Chat", created_at=utc_now(), updated_at=utc_now())
        db.add(th)
        db.commit()
        db.refresh(th)
        return CreateThreadResponse(thread_id=th.id)


class ThreadOut(BaseModel):
    id: str
    title: str
    pinned: bool
    created_at: datetime
    updated_at: datetime


class ListThreadsResponse(BaseModel):
    threads: list[ThreadOut]


@router.get("/chats", response_model=ListThreadsResponse)
async def list_threads(x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> ListThreadsResponse:
    uid = _require_user_id(x_user_id)
    with db_session() as db:
        u = db.get(User, uid)
        if u is None:
            raise HTTPException(status_code=401, detail="Unknown user.")

        rows = db.execute(
            select(ChatThread)
            .where(ChatThread.user_id == uid)
            .order_by(ChatThread.pinned.desc(), ChatThread.updated_at.desc(), ChatThread.created_at.desc())
        ).scalars()
        threads = [
            ThreadOut(
                id=t.id,
                title=t.title,
                pinned=bool(t.pinned),
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in rows.all()
        ]
        return ListThreadsResponse(threads=threads)


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class ThreadMessagesResponse(BaseModel):
    thread_id: str
    messages: list[ChatMessageOut]


@router.get("/chats/{thread_id}/messages", response_model=ThreadMessagesResponse)
async def list_messages(
    thread_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> ThreadMessagesResponse:
    uid = _require_user_id(x_user_id)
    with db_session() as db:
        th = db.get(ChatThread, thread_id)
        if th is None or th.user_id != uid:
            raise HTTPException(status_code=404, detail="Chat not found.")

        rows = db.execute(
            select(ChatMessage).where(ChatMessage.thread_id == thread_id).order_by(ChatMessage.created_at.asc())
        ).scalars()
        msgs = [
            ChatMessageOut(id=m.id, role=m.role, content=m.content, created_at=m.created_at) for m in rows.all()
        ]
        return ThreadMessagesResponse(thread_id=thread_id, messages=msgs)


class EnsureDefaultThreadResponse(BaseModel):
    thread_id: str


@router.post("/chats/default", response_model=EnsureDefaultThreadResponse)
async def ensure_default_thread(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> EnsureDefaultThreadResponse:
    uid = _require_user_id(x_user_id)
    with db_session() as db:
        u = db.get(User, uid)
        if u is None:
            raise HTTPException(status_code=401, detail="Unknown user.")

        th = db.execute(
            select(ChatThread).where(ChatThread.user_id == uid).order_by(ChatThread.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        if th is None:
            th = ChatThread(user_id=uid, title="Chat", created_at=utc_now(), updated_at=utc_now())
            db.add(th)
            db.commit()
            db.refresh(th)
        return EnsureDefaultThreadResponse(thread_id=th.id)


class RenameThreadRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class RenameThreadResponse(BaseModel):
    ok: bool = Field(True)


@router.patch("/chats/{thread_id}", response_model=RenameThreadResponse)
async def rename_thread(
    thread_id: str,
    body: RenameThreadRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> RenameThreadResponse:
    uid = _require_user_id(x_user_id)
    title = " ".join((body.title or "").strip().split())
    if not title:
        raise HTTPException(status_code=400, detail="Title is required.")
    with db_session() as db:
        th = db.get(ChatThread, thread_id)
        if th is None or th.user_id != uid:
            raise HTTPException(status_code=404, detail="Chat not found.")
        th.title = title[:200]
        # Do not change `updated_at` on rename.
        # Ordering should reflect chat activity (messages), not metadata edits.
        db.commit()
        return RenameThreadResponse()


class PinThreadRequest(BaseModel):
    pinned: bool


class PinThreadResponse(BaseModel):
    ok: bool = Field(True)
    pinned: bool


@router.post("/chats/{thread_id}/pin", response_model=PinThreadResponse)
async def pin_thread(
    thread_id: str,
    body: PinThreadRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> PinThreadResponse:
    uid = _require_user_id(x_user_id)
    with db_session() as db:
        th = db.get(ChatThread, thread_id)
        if th is None or th.user_id != uid:
            raise HTTPException(status_code=404, detail="Chat not found.")
        th.pinned = bool(body.pinned)
        # Do not change `updated_at` when pinning/unpinning.
        # Ordering should reflect chat activity (messages), not pin actions.
        db.commit()
        return PinThreadResponse(pinned=bool(th.pinned))


class DeleteThreadResponse(BaseModel):
    ok: bool = Field(True)


@router.delete("/chats/{thread_id}", response_model=DeleteThreadResponse)
async def delete_thread(
    thread_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> DeleteThreadResponse:
    uid = _require_user_id(x_user_id)
    with db_session() as db:
        th = db.get(ChatThread, thread_id)
        if th is None or th.user_id != uid:
            raise HTTPException(status_code=404, detail="Chat not found.")
        db.delete(th)
        db.commit()
        return DeleteThreadResponse()

