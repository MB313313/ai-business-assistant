from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..db import db_session
from ..models import User

router = APIRouter(tags=["users"])


class AnonymousUserResponse(BaseModel):
    user_id: str


@router.post("/users/anonymous", response_model=AnonymousUserResponse)
async def create_anonymous_user() -> AnonymousUserResponse:
    with db_session() as db:
        u = User()
        db.add(u)
        db.commit()
        db.refresh(u)
        return AnonymousUserResponse(user_id=u.id)

