from typing import Any

from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str
    top_k: int | None = None
    hybrid: bool | None = None
    rerank: bool | None = None
    rewrite: bool | None = None
    mmr: bool | None = None
    hyde: bool = False
    retrieval_only: bool = False


class SourceChunk(BaseModel):
    filename: str | None = None
    page: int | None = None
    score: float | None = None
    text: str
    id: str | None = None
    rank: int | None = None
    retrievers: dict[str, Any] | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None
    pre_rerank_score: float | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
    trace: dict[str, Any] | None = None
