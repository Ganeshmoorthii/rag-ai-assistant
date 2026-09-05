import httpx
from fastapi import APIRouter, HTTPException

from app.api.schemas import QueryRequest, QueryResponse
from app.core.config import settings
from app.core.flow_log import flow_log
from app.services.llm_client import generate_answer
from app.services.trace_logger import log_interaction_trace
from app.services import retriever

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query_documents(payload: QueryRequest):
    flow_log(
        "request.received",
        question=payload.question,
        top_k=payload.top_k,
        hybrid=payload.hybrid,
        rerank=payload.rerank,
        rewrite=payload.rewrite,
        mmr=payload.mmr,
        hyde=payload.hyde,
        retrieval_only=payload.retrieval_only,
    )
    result = await retriever.retrieve(
        payload.question,
        top_k=payload.top_k,
        hybrid=payload.hybrid,
        rerank=payload.rerank,
        rewrite=payload.rewrite,
        mmr=payload.mmr,
        hyde=payload.hyde,
    )
    matches = result["chunks"]
    flow_log(
        "retrieval.completed",
        chunk_count=len(matches),
        chunks=matches,
        trace=result["trace"],
    )

    resolved_config = {
        "top_k": payload.top_k or settings.top_k,
        "hybrid": payload.hybrid if payload.hybrid is not None else settings.hybrid_enabled,
        "rerank": payload.rerank if payload.rerank is not None else settings.rerank_enabled,
        "rewrite": payload.rewrite if payload.rewrite is not None else settings.rewrite_enabled,
        "mmr": payload.mmr if payload.mmr is not None else settings.mmr_enabled,
        "hyde": payload.hyde,
        "retrieval_only": payload.retrieval_only,
    }

    if not matches:
        flow_log("response.no_matches")
        answer = "No documents have been uploaded yet, or no relevant content was found."
        tr = log_interaction_trace(
            question=payload.question,
            chunks=[],
            answer=answer,
            trace_info=result["trace"],
            config=resolved_config,
        )
        if tr:
            result["trace"]["trace_id"] = tr["trace_id"]
        return QueryResponse(
            answer=answer,
            sources=[],
            trace=result["trace"],
        )

    if payload.retrieval_only:
        flow_log("response.retrieval_only", chunks=matches)
        answer = "(retrieval_only=true — generation skipped)"
        tr = log_interaction_trace(
            question=payload.question,
            chunks=matches,
            answer=answer,
            trace_info=result["trace"],
            config=resolved_config,
        )
        if tr:
            result["trace"]["trace_id"] = tr["trace_id"]
        return QueryResponse(
            answer=answer,
            sources=matches,
            trace=result["trace"],
        )

    try:
        answer = await generate_answer(payload.question, matches)
    except RuntimeError as e:
        flow_log("llm.error", error=str(e))
        log_interaction_trace(
            question=payload.question,
            chunks=matches,
            answer="",
            trace_info=result["trace"],
            config=resolved_config,
            error=str(e),
        )
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        flow_log(
            "llm.error",
            status_code=e.response.status_code,
            response=e.response.text,
        )
        log_interaction_trace(
            question=payload.question,
            chunks=matches,
            answer="",
            trace_info=result["trace"],
            config=resolved_config,
            error=f"{e.response.status_code} {e.response.text}",
        )
        raise HTTPException(
            status_code=502,
            detail=f"LLM provider request failed: {e.response.status_code} {e.response.text}",
        )

    flow_log("response.completed", answer=answer, sources=matches)
    tr = log_interaction_trace(
        question=payload.question,
        chunks=matches,
        answer=answer,
        trace_info=result["trace"],
        config=resolved_config,
    )
    if tr:
        result["trace"]["trace_id"] = tr["trace_id"]

    return QueryResponse(answer=answer, sources=matches, trace=result["trace"])
