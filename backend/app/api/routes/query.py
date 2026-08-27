import httpx
from fastapi import APIRouter, HTTPException

from app.api.schemas import QueryRequest, QueryResponse
from app.services.llm_client import generate_answer
from app.services import retriever

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query_documents(payload: QueryRequest):
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

    if not matches:
        return QueryResponse(
            answer="No documents have been uploaded yet, or no relevant content was found.",
            sources=[],
            trace=result["trace"],
        )

    if payload.retrieval_only:
        return QueryResponse(
            answer="(retrieval_only=true — generation skipped)",
            sources=matches,
            trace=result["trace"],
        )

    try:
        answer = await generate_answer(payload.question, matches)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"OpenRouter request failed: {e.response.status_code} {e.response.text}",
        )

    return QueryResponse(answer=answer, sources=matches, trace=result["trace"])
