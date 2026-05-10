from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..db import db_session
from ..models import User, UserKnowledgeDocument
from ..services import documents, vector_store

router = APIRouter(tags=["vector"])


class IndexRequest(BaseModel):
    document_id: str = Field(..., min_length=1)


class IndexResponse(BaseModel):
    indexed_chunks: int
    total_vectors: int


@router.post("/vector/index", response_model=IndexResponse)
async def index_document(
    body: IndexRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> IndexResponse:
    chunks = documents.get_document_chunks(body.document_id)
    if chunks is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown document_id, or chunks are no longer in memory (re-upload required).",
        )
    filtered = [c.strip() for c in chunks if c.strip()]
    if not filtered:
        raise HTTPException(status_code=400, detail="No non-empty chunks to index.")
    try:
        indexed, total = await vector_store.index_document_chunks(body.document_id, filtered)
    except RuntimeError as e:
        if "OPENAI_API_KEY" in str(e):
            raise HTTPException(status_code=503, detail=str(e)) from e
        raise HTTPException(status_code=502, detail=str(e)) from e

    uid = (x_user_id or "").strip()
    if uid:
        doc_id = (body.document_id or "").strip()
        if doc_id:
            with db_session() as db:
                u = db.get(User, uid)
                if u is not None:
                    exists = db.execute(
                        select(func.count())
                        .select_from(UserKnowledgeDocument)
                        .where(
                            UserKnowledgeDocument.user_id == uid,
                            UserKnowledgeDocument.document_id == doc_id,
                        )
                    ).scalar_one()
                    if not int(exists or 0):
                        db.add(UserKnowledgeDocument(user_id=uid, document_id=doc_id))
                        db.commit()

    return IndexResponse(indexed_chunks=indexed, total_vectors=total)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000)
    top_k: int = Field(5, ge=1, le=50)


class SearchHit(BaseModel):
    document_id: str
    text: str
    score: float


class SearchResponse(BaseModel):
    results: list[SearchHit]


@router.post("/vector/search", response_model=SearchResponse)
async def search_chunks(body: SearchRequest) -> SearchResponse:
    try:
        hits = await vector_store.retrieve_relevant_chunks(body.query, body.top_k)
    except RuntimeError as e:
        if "OPENAI_API_KEY" in str(e):
            raise HTTPException(status_code=503, detail=str(e)) from e
        raise HTTPException(status_code=502, detail=str(e)) from e
    return SearchResponse(results=[SearchHit(**h) for h in hits])
