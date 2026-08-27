import os
import uuid

from fastapi import APIRouter, HTTPException, UploadFile

from app.api.schemas import DocumentInfo, UploadResponse
from app.core.config import settings
from app.services import retriever, vector_store
from app.services.ingest import ingest_pdf

router = APIRouter()


@router.post("/documents", response_model=UploadResponse)
async def upload_document(file: UploadFile):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    dest_path = os.path.join(settings.upload_dir, safe_name)

    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)

    result = ingest_pdf(dest_path, file.filename)
    if result["chunks"] == 0:
        os.remove(dest_path)
        raise HTTPException(
            status_code=422,
            detail="No text could be extracted from this PDF, even with OCR. "
            "The file may be empty, corrupted, or unsupported.",
        )

    retriever.invalidate_bm25_index()
    return UploadResponse(**result)


@router.get("/documents", response_model=list[DocumentInfo])
async def get_documents():
    return vector_store.list_documents()


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    vector_store.delete_document(doc_id)
    retriever.invalidate_bm25_index()
    return {"status": "deleted", "doc_id": doc_id}
