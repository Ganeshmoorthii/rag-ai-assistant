import httpx
from fastapi import APIRouter, HTTPException

from app.api.schemas import QueryRequest, QueryResponse
from app.core.config import settings
from app.core.flow_log import flow_log
from app.services.llm.llm_client import generate_answer
from app.services.observability.trace_logger import log_interaction_trace
from app.services.agents.rag_graph import graph_rag
from app.services.retrieval import retriever

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
        use_graph=payload.use_graph,
        use_agent=payload.use_agent,
    )

    if payload.use_agent:
        from app.services.agents.docs_qa.docs_agent import run_docs_agent
        flow_log("agent.route.started", question=payload.question)
        agent_out = await run_docs_agent(payload.question)
        answer = agent_out.get("answer", "")
        flow_log("agent.route.completed", laps=agent_out.get("lap_count", 1), total_tokens=agent_out.get("total_tokens", 0))
        return QueryResponse(
            answer=answer,
            sources=[],
            trace={
                "strategy": "Docs Agent Loop (Week 7)",
                "timings_ms": {"total": agent_out.get("wall_clock_seconds", 0.0) * 1000},
            },
            agent_execution={
                "mode": "Docs Agent Loop (Week 7)",
                "lap_count": agent_out.get("lap_count", 1),
                "tools_called": agent_out.get("tools_called", []),
                "total_tokens": agent_out.get("total_tokens", 0),
                "total_cost": agent_out.get("total_cost", 0.0),
                "wall_clock_seconds": agent_out.get("wall_clock_seconds", 0.0),
                "budget_fired": agent_out.get("budget_fired"),
                "budget_exceeded": agent_out.get("budget_exceeded", False),
                "lap_traces": agent_out.get("lap_traces", []),
            },
        )

    use_graph = (
        payload.use_graph
        if payload.use_graph is not None
        else settings.use_langgraph
    )
    if use_graph:
        flow_log("graph.execution.started", question=payload.question)
        graph_result = await graph_rag.run_rag_graph(
            question=payload.question,
            top_k=payload.top_k,
            hybrid=payload.hybrid,
            rerank=payload.rerank,
            rewrite=payload.rewrite,
            mmr=payload.mmr,
            hyde=payload.hyde,
            retrieval_only=payload.retrieval_only,
        )
        matches = graph_result["chunks"]
        answer = graph_result["answer"]
        trace = graph_result["trace"]

        resolved_config = {
            "top_k": payload.top_k or settings.top_k,
            "hybrid": payload.hybrid if payload.hybrid is not None else settings.hybrid_enabled,
            "rerank": payload.rerank if payload.rerank is not None else settings.rerank_enabled,
            "rewrite": payload.rewrite if payload.rewrite is not None else settings.rewrite_enabled,
            "mmr": payload.mmr if payload.mmr is not None else settings.mmr_enabled,
            "hyde": payload.hyde,
            "retrieval_only": payload.retrieval_only,
            "use_graph": True,
        }

        flow_log("response.completed", answer=answer, sources=matches)
        tr = log_interaction_trace(
            question=payload.question,
            chunks=matches,
            answer=answer,
            trace_info=trace,
            config=resolved_config,
        )
        if tr:
            trace["trace_id"] = tr["trace_id"]

        return QueryResponse(answer=answer, sources=matches, trace=trace)

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
