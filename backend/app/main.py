from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import config as _config  # noqa: F401 — side effect: load `.env`
from .services import vector_store

from .api.chat import router as chat_router
from .api.documents import router as documents_router
from .api.vector import router as vector_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    vector_store.try_load_from_disk()
    yield


app = FastAPI(title="AI Business Assistant API", version="0.1.0", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(vector_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
