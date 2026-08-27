from pydantic import BaseModel


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    chunks: int


class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    chunks: int
