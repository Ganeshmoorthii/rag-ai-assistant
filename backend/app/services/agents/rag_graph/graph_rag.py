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

from app.core.config import settings
from app.services.agents.rag_graph import query_analyser_agent, response_agent, retrieval_agent


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
    max_retries: int
    trace: Dict[str, Any]
    config: Dict[str, Any]


# --- Build StateGraph ------------------------------------------------------

def create_rag_graph():
    workflow = StateGraph(RAGGraphState)

    workflow.add_node("query_analyser", query_analyser_agent.query_analyser_node)
    workflow.add_node("retrieval_agent", retrieval_agent.retrieval_agent_node)
    workflow.add_node("response_agent", response_agent.response_agent_node)
    workflow.add_node("grade_generation", response_agent.grade_generation_node)

    workflow.add_edge(START, "query_analyser")
    workflow.add_edge("query_analyser", "retrieval_agent")
    workflow.add_edge("retrieval_agent", "response_agent")
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
        "max_retries": settings.graph_max_retries,
        "trace": {
            "original_question": question,
            "engine": "langgraph-3-agent",
            "config": resolved_config,
            "stages": [],
            "timings_ms": {},
        },
        "config": resolved_config,
    }

    final_state = await graph.ainvoke(initial_state)

    trace = final_state["trace"]
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
    )

    return {
        "answer": final_state["answer"],
        "chunks": final_state["documents"],
        "trace": trace,
    }
