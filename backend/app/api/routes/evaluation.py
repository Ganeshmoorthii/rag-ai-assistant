import json
import os
import sys

import httpx
from fastapi import APIRouter, HTTPException

from app.api.schemas import EvalRequest, EvalResponse, TriageRequest, TriageResponse
from app.core.config import settings
from app.services import metrics, retriever
from app.services.llm_client import generate_answer

router = APIRouter()

GOLDEN_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "eval", "golden_set.json")
)


def _load_eval_module():
    backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)
    from eval.run_eval import CONFIGS, load_golden, run_config

    return CONFIGS, load_golden, run_config


@router.post("/triage", response_model=TriageResponse)
async def triage_failure(payload: TriageRequest):
    expected = [entry.model_dump() for entry in payload.expected]
    top_k = payload.top_k or settings.top_k
    result = await retriever.retrieve(
        payload.question,
        top_k=top_k,
        hybrid=payload.hybrid,
        rerank=payload.rerank,
        rewrite=payload.rewrite,
        mmr=payload.mmr,
        hyde=payload.hyde,
    )
    chunks = result["chunks"]

    hit = metrics.hit_at_k(chunks, expected, top_k)
    rank = metrics.first_hit_rank(chunks, expected)
    recall = metrics.recall_at_k(chunks, expected, top_k)
    reciprocal_rank = metrics.reciprocal_rank(chunks, expected)

    answer = None
    if payload.generate and chunks:
        try:
            answer = await generate_answer(payload.question, chunks)
        except (RuntimeError, httpx.HTTPStatusError) as error:
            answer = f"(generation failed: {error})"

    expected_pages = ", ".join(f"{entry['filename']} p.{entry['page']}" for entry in expected)
    retrieved_pages = ", ".join(
        f"{chunk.get('filename')} p.{chunk.get('page')}" for chunk in chunks[:top_k]
    )

    if not hit:
        verdict = "retrieval_failure"
        reasoning = (
            f"RETRIEVAL FAILURE. None of the expected pages ({expected_pages}) appeared "
            f"in the top {top_k}. Retrieved instead: {retrieved_pages}."
        )
    elif rank and rank > 1 and recall < 1.0:
        verdict = "partial_retrieval"
        reasoning = (
            f"PARTIAL RETRIEVAL. A correct page was found at rank {rank}, but only "
            f"{recall:.0%} of expected pages made the top {top_k}."
        )
    else:
        verdict = "generation_candidate"
        reasoning = (
            f"RETRIEVAL SUCCEEDED. The expected page was at rank {rank}, and "
            f"{recall:.0%} of expected pages were in the top {top_k}."
        )

    return TriageResponse(
        question=payload.question,
        verdict=verdict,
        reasoning=reasoning,
        retrieved_correct_chunk=hit,
        first_hit_rank=rank,
        hit_at_k=hit,
        recall_at_k=round(recall, 4),
        reciprocal_rank=round(reciprocal_rank, 4),
        sources=chunks,
        answer=answer,
        trace=result["trace"],
    )


@router.get("/golden-set")
async def get_golden_set():
    if not os.path.exists(GOLDEN_PATH):
        raise HTTPException(status_code=404, detail="golden_set.json not found")
    with open(GOLDEN_PATH, encoding="utf-8") as file:
        return json.load(file)


@router.post("/evaluate", response_model=EvalResponse)
async def evaluate(payload: EvalRequest):
    configs, load_golden, run_config = _load_eval_module()
    if payload.config not in configs:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown config '{payload.config}'. Available: {', '.join(configs)}",
        )

    questions = load_golden()
    retriever.ensure_bm25_index(force=True)
    run = await run_config(payload.config, questions, payload.top_k or settings.top_k)
    return EvalResponse(**run)


@router.get("/configs")
async def list_configs():
    configs, _, _ = _load_eval_module()
    return [
        {
            "name": name,
            "description": config["_desc"],
            "flags": {key: value for key, value in config.items() if not key.startswith("_")},
        }
        for name, config in configs.items()
    ]


@router.get("/retrieval-settings")
async def retrieval_settings():
    return {
        "top_k": settings.top_k,
        "hybrid_enabled": settings.hybrid_enabled,
        "rerank_enabled": settings.rerank_enabled,
        "rewrite_enabled": settings.rewrite_enabled,
        "mmr_enabled": settings.mmr_enabled,
        "candidate_k": settings.candidate_k,
        "rrf_k": settings.rrf_k,
        "mmr_lambda": settings.mmr_lambda,
        "rerank_model": settings.rerank_model,
        "embedding_model": settings.embedding_model,
        "bm25_index_size": retriever.ensure_bm25_index(),
    }
