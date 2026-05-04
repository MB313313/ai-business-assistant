from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import documents, vector_store

router = APIRouter(tags=["vector"])


class IndexRequest(BaseModel):
    document_id: str = Field(..., min_length=1)


class IndexResponse(BaseModel):
    indexed_chunks: int
    total_vectors: int


@router.post("/vector/index", response_model=IndexResponse)
async def index_document(body: IndexRequest) -> IndexResponse:
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
