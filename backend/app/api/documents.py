from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..services import documents, vision_service

router = APIRouter(tags=["documents"])

_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
_TEXT_SUFFIXES = frozenset({".pdf", ".txt"})
_ALLOWED = _IMAGE_SUFFIXES | _TEXT_SUFFIXES


class UploadDocumentResponse(BaseModel):
    chunk_count: int = Field(..., description="Number of text chunks stored in memory.")
    document_id: str = Field(..., description="Id for this upload (for future RAG / retrieval).")


@router.post("/upload-document", response_model=UploadDocumentResponse)
async def upload_document(file: UploadFile = File(...)) -> UploadDocumentResponse:
    name = (file.filename or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="A file with a filename is required.")

    suffix = ""
    if "." in name:
        suffix = name[name.rfind(".") :].lower()
    if suffix not in _ALLOWED:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported type {suffix!r}. "
                "Upload a PDF, TXT, or a common image (PNG, JPG, JPEG, WebP, GIF)."
            ),
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")

    text: str

    if suffix in _IMAGE_SUFFIXES:
        mime = vision_service.mime_for_document_suffix(suffix)
        try:
            caption = await vision_service.describe_image_for_indexing(raw, mime)
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        caption = (caption or "").strip()
        if not caption:
            raise HTTPException(
                status_code=400,
                detail="Could not read enough detail from the image to index it. Try a clearer image.",
            )
        text = f"[Uploaded business image: {name}]\n{caption}"

    else:
        try:
            text = documents.extract_text(name, raw)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        if suffix == ".pdf":
            try:
                caps = await vision_service.describe_pdf_embedded_images(raw)
            except Exception:
                caps = []
            if caps:
                extra = "\n\n[Visual content from document — auto descriptions]\n" + "\n".join(
                    f"- {c}" for c in caps
                )
                text = (text + extra).strip()

    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="No extractable text found (empty or unreadable content).",
        )

    chunks = documents.chunk_text(text)
    document_id = documents.store_document_chunks(chunks)
    return UploadDocumentResponse(chunk_count=len(chunks), document_id=document_id)
