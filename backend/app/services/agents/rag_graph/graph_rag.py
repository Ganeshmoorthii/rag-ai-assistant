"""Three-Agent Agentic RAG Pipeline (LangGraph orchestration).

Orchestrates the three agents defined in query_analyser_agent.py,
retrieval_agent.py, and response_agent.py.

GRAPH TOPOLOGY
--------------
        [START]
           |
           v
  [query_analyser_agent]   <- decomposition, classification, complexity
           |
           v
    [retrieval_agent]      <- iterative search/evaluate/rewrite loop,
           |                  run per sub-query concurrently, then merged
           v                  (all internal to this one node)
    [response_agent]       <- evidence synthesis + format selection
           |
           v
   [grade_generation]      <- groundedness check on the final answer
           |
           v
         [END]

Each box maps 1:1 onto one of the three agents in the spec. LangGraph
orchestrates the hand-off between them; each agent owns whatever looping
or fan-out it needs internally (the retry loop and the per-sub-query
fan-out both live inside retrieval_agent.py's own node function).
"""

from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.core import tracing
from app.core.config import settings
from app.core.flow_log import flow_log
from app.core.tracing import traced_node
from app.services.observability.trace_logger import log_interaction_trace
from app.services.agents.rag_graph import (
    live_data_agent,
    manager_agent,
    query_analyser_agent,
    response_agent,
    retrieval_agent,
)


class RAGGraphState(TypedDict):
    question: str
    sub_queries: List[str]
    intent: str
    route: str
    complexity: str
    documents: List[Dict[str, Any]]
    evidence_sufficient: bool
    sub_results: List[Dict[str, Any]]
    answer: str
    format: str
    uncertainty_note: Optional[str]
    hallucination_grade: Optional[str]
    self_corrected: bool
    use_live_data: bool
    operational_observations: List[str]
    operational_data_status: Optional[str]
    max_retries: int
    trace: Dict[str, Any]
    config: Dict[str, Any]


# --- Build StateGraph ------------------------------------------------------

def _route_after_retrieval(state: RAGGraphState) -> str:
    target = "live_data_agent" if state.get("use_live_data") else "response_agent"
    flow_log("graph.handoff", from_node="retrieval_agent", to_node=target)
    return target


def create_rag_graph():
    workflow = StateGraph(RAGGraphState)

    # traced_node wraps each node in a span; the name must match the node's
    # trace["stages"] entry so the stage summary is copied onto the span.
    workflow.add_node("manager", traced_node("manager")(manager_agent.manager_node))
    workflow.add_node(
        "query_analyser", traced_node("query_analyser")(query_analyser_agent.query_analyser_node)
    )
    workflow.add_node(
        "retrieval_agent", traced_node("retrieval_agent")(retrieval_agent.retrieval_agent_node)
    )
    workflow.add_node(
        "live_data_agent", traced_node("live_data_agent")(live_data_agent.live_data_agent_node)
    )
    workflow.add_node(
        "response_agent", traced_node("response_agent")(response_agent.response_agent_node)
    )
    workflow.add_node(
        "grade_generation",
        traced_node("grade_generation", kind="check")(response_agent.grade_generation_node),
    )

    workflow.add_edge(START, "manager")
    workflow.add_edge("manager", "query_analyser")
    workflow.add_edge("query_analyser", "retrieval_agent")
    workflow.add_conditional_edges(
        "retrieval_agent",
        _route_after_retrieval,
        {"live_data_agent": "live_data_agent", "response_agent": "response_agent"},
    )
    workflow.add_edge("live_data_agent", "response_agent")
    workflow.add_edge("response_agent", "grade_generation")
    workflow.add_edge("grade_generation", END)

    return workflow.compile()


_rag_app = None


def get_rag_graph():
    global _rag_app
    if _rag_app is None:
        _rag_app = create_rag_graph()
    return _rag_app


async def run_rag_graph(
    question: str,
    top_k: Optional[int] = None,
    hybrid: Optional[bool] = None,
    rerank: Optional[bool] = None,
    rewrite: Optional[bool] = None,
    mmr: Optional[bool] = None,
    hyde: bool = False,
    retrieval_only: bool = False,
) -> Dict[str, Any]:
    """High-level runner invoked by API routes and evaluation harness.

    Signature is unchanged from the previous single-file implementation, so
    app/api/routes/query.py needs no changes. `hybrid`/`rerank`/`mmr` are
    passed through as explicit overrides when the caller set them; left as
    None, the retrieval_agent decides them dynamically per query instead of
    falling back to one fixed .env default. `rewrite` and `hyde` are kept
    for API compatibility, but the retrieval_agent owns its own rewrite
    step internally, so they aren't threaded further than the trace here.
    """
    graph = get_rag_graph()

    resolved_config = {
        "top_k": top_k or settings.top_k,
        "hybrid": hybrid,
        "rerank": rerank,
        "mmr": mmr,
        "rewrite_requested": rewrite if rewrite is not None else settings.rewrite_enabled,
        "hyde": hyde,
        "retrieval_only": retrieval_only,
    }

    initial_state: RAGGraphState = {
        "question": question,
        "sub_queries": [question],
        "intent": "factual_lookup",
        "route": "semantic_concept",
        "complexity": "simple",
        "documents": [],
        "evidence_sufficient": True,
        "sub_results": [],
        "answer": "",
        "format": "",
        "uncertainty_note": None,
        "hallucination_grade": None,
        "self_corrected": False,
        "use_live_data": False,
        "operational_observations": [],
        "operational_data_status": None,
        "max_retries": settings.graph_max_retries,
        "trace": {
            "original_question": question,
            "engine": "langgraph-manager-specialists",
            "config": resolved_config,
            "stages": [],
            "timings_ms": {},
        },
        "config": resolved_config,
    }

    run, token = tracing.start_run()
    initial_state["trace"]["trace_id"] = run.trace_id
    flow_log("graph.run.started", question=question)
    try:
        with tracing.span("rag_graph", kind="run", question=question):
            final_state = await graph.ainvoke(initial_state)
    except Exception as error:
        flow_log("graph.run.failed", error=str(error), span_tree="\n" + tracing.render_tree(run.spans))
        log_interaction_trace(
            question=question,
            chunks=[],
            answer="",
            trace_info={**initial_state["trace"], "spans": run.spans},
            trace_id=run.trace_id,
            error=f"{type(error).__name__}: {error}",
        )
        raise
    finally:
        tracing.end_run(token)

    trace = final_state["trace"]
    trace["spans"] = run.spans
    trace["timings_ms"]["total"] = round(
        sum(v for k, v in trace["timings_ms"].items() if k != "total"), 1
    )
    trace["final_chunk_ids"] = [c["id"] for c in final_state["documents"]]
    trace["agentic"] = {
        "intent": final_state.get("intent"),
        "route": final_state.get("route"),
        "complexity": final_state.get("complexity"),
        "sub_queries": final_state.get("sub_queries"),
        "evidence_sufficient": final_state.get("evidence_sufficient"),
        "format": final_state.get("format"),
        "uncertainty_note": final_state.get("uncertainty_note"),
        "hallucination_grade": final_state.get("hallucination_grade"),
        "self_corrected": final_state.get("self_corrected", False),
        "use_live_data": final_state.get("use_live_data", False),
        "operational_data_status": final_state.get("operational_data_status"),
    }

    # Guardrail summary: mirrors the docs_agent mode's low_confidence flag
    # so both pipelines expose the same signal shape to the API layer.
    # True when the answer needed a self-correction pass, still failed
    # groundedness after that pass, evidence was never fully sufficient,
    # or a sub-query's rewrite loop stalled without resolving.
    grade = final_state.get("hallucination_grade")
    stalled_any = any(
        sr.get("stalled") for sr in final_state.get("sub_results", [])
    )
    trace["low_confidence"] = bool(
        final_state.get("self_corrected")
        or grade == "citation_mismatch"
        or not final_state.get("evidence_sufficient", True)
        or stalled_any
        or (
            final_state.get("use_live_data")
            and final_state.get("operational_data_status") != "completed"
        )
    )

    flow_log(
        "graph.run.completed",
        trace_id=run.trace_id,
        total_ms=trace["timings_ms"]["total"],
        low_confidence=trace["low_confidence"],
        span_tree="\n" + tracing.render_tree(run.spans),
    )

    return {
        "answer": final_state["answer"],
        "chunks": final_state["documents"],
        "trace": trace,
    }
