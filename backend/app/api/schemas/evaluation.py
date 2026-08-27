from typing import Any

from pydantic import BaseModel

from .query import SourceChunk


class ExpectedPage(BaseModel):
    filename: str
    page: int


class TriageRequest(BaseModel):
    question: str
    expected: list[ExpectedPage]
    top_k: int | None = None
    hybrid: bool | None = None
    rerank: bool | None = None
    rewrite: bool | None = None
    mmr: bool | None = None
    hyde: bool = False
    generate: bool = True


class TriageResponse(BaseModel):
    question: str
    verdict: str
    reasoning: str
    retrieved_correct_chunk: bool
    first_hit_rank: int | None
    hit_at_k: bool
    recall_at_k: float
    reciprocal_rank: float
    sources: list[SourceChunk]
    answer: str | None = None
    trace: dict[str, Any] | None = None


class EvalRequest(BaseModel):
    config: str = "baseline"
    top_k: int | None = None


class EvalResponse(BaseModel):
    config_name: str
    config: dict[str, Any]
    description: str
    top_k: int
    overall: dict[str, Any]
    by_category: dict[str, Any]
    questions: list[dict[str, Any]]
