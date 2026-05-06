from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import inspect, text

from . import config as _config  # noqa: F401 — side effect: load `.env`
from .db import engine
from .models import Base
from .services import vector_store

from .api.chat import router as chat_router
from .api.chats import router as chats_router
from .api.documents import router as documents_router
from .api.users import router as users_router
from .api.vector import router as vector_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create DB tables (simple local setup; no migrations required)
    Base.metadata.create_all(bind=engine)

    # Lightweight schema evolution (for dev): add new columns if missing.
    # For production, prefer Alembic migrations.
    insp = inspect(engine)
    if "chat_threads" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("chat_threads")}
        if "pinned" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE chat_threads ADD COLUMN pinned BOOLEAN NOT NULL DEFAULT FALSE"))

    vector_store.try_load_from_disk()
    yield


app = FastAPI(title="AI Business Assistant API", version="0.1.0", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(users_router)
app.include_router(chats_router)
app.include_router(documents_router)
app.include_router(vector_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
