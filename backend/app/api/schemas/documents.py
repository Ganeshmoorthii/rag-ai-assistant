from pydantic import BaseModel


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    chunks: int


class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    chunks: int


class ChunkInfo(BaseModel):
    id: str
    doc_id: str
    filename: str
    page: int | None = None
    chunk_index: int = 0
    text: str
    word_count: int = 0
    char_count: int = 0

