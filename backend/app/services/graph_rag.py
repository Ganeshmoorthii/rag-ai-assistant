"""LangGraph Agentic RAG Pipeline.

Implements an Adaptive and Self-Correcting RAG (Self-RAG / Corrective RAG)
architecture using LangGraph StateGraph.

GRAPH TOPOLOGY
--------------
              [START]
                 │
                 ▼
         [route_query_node]
                 │
                 ▼
          [retrieve_node] ◄──────────────┐
                 │                       │ (Conditional Retry Loop)
                 ▼                       │
       [grade_documents_node]            │
                 │                       │
     relevant? ──┼─── (No & retries < max) ──► [rewrite_query_node]
                 │ (Yes or retries exhausted)
                 ▼
          [generate_node]
                 │
                 ▼
      [grade_generation_node]
                 │
                 ▼
               [END]
"""

import json
import re
import time
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import settings
from app.core.flow_log import flow_log
from app.services import llm_client, query_rewriter, retriever


class RAGGraphState(TypedDict):
    question: str
    search_query: str
    documents: List[Dict[str, Any]]
    answer: str
    retry_count: int
    max_retries: int
    needs_rewrite: bool
    route: str
    document_grades: List[Dict[str, Any]]
    hallucination_grade: Optional[str]
    trace: Dict[str, Any]
    config: Dict[str, Any]


# --- Nodes -----------------------------------------------------------------

async def route_query_node(state: RAGGraphState) -> Dict[str, Any]:
    """Analyze query to identify technical identifiers or exact codes."""
    t0 = time.perf_counter()
    question = state["question"]
    trace = state["trace"]

    # Detect exact code symbols, camelCase, snake_case, ALL_CAPS, or endpoints
    code_pattern = r"(?:[A-Z0-9]+(?:[-_][A-Z0-9]+)+|\b[a-z]+(?:[A-Z][a-z0-9]+)+\b|\b/[a-z0-9/_-]+\b|`[^`]+`|\b[a-zA-Z0-9_]+\(\))"
    has_code = bool(re.search(code_pattern, question))

    route = "exact_identifier" if has_code else "semantic_concept"

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    trace["timings_ms"]["graph_route"] = elapsed
    trace["stages"].append(
        {
            "stage": "graph_route",
            "route": route,
            "has_exact_identifier": has_code,
            "timings_ms": elapsed,
        }
    )

    flow_log("graph.route_query", route=route, question=question)
    return {
        "route": route,
        "search_query": question,
        "trace": trace,
    }


async def retrieve_node(state: RAGGraphState) -> Dict[str, Any]:
    """Execute the multi-strategy retrieval pipeline."""
    cfg = state["config"]
    search_query = state.get("search_query") or state["question"]
    route = state.get("route", "semantic_concept")

    # If query contains exact identifiers, ensure hybrid (BM25) is engaged
    hybrid_flag = cfg.get("hybrid")
    if hybrid_flag is None:
        hybrid_flag = True if route == "exact_identifier" else settings.hybrid_enabled
    elif route == "exact_identifier" and not hybrid_flag:
        hybrid_flag = True  # Auto-boost for exact term lookup

    retrieval_result = await retriever.retrieve(
        question=search_query,
        top_k=cfg.get("top_k"),
        hybrid=hybrid_flag,
        rerank=cfg.get("rerank"),
        rewrite=False,  # Handled by LangGraph's rewrite_query_node
        mmr=cfg.get("mmr"),
        hyde=False,
    )

    chunks = retrieval_result["chunks"]
    retriever_trace = retrieval_result["trace"]

    trace = state["trace"]
    # Merge retriever stages into the unified trace
    for stage in retriever_trace.get("stages", []):
        trace["stages"].append(stage)

    for k, v in retriever_trace.get("timings_ms", {}).items():
        trace["timings_ms"][f"retriever_{k}"] = v

    trace["final_chunk_ids"] = [c["id"] for c in chunks]

    flow_log("graph.retrieve", count=len(chunks), query=search_query)
    return {
        "documents": chunks,
        "trace": trace,
    }


async def grade_documents_node(state: RAGGraphState) -> Dict[str, Any]:
    """Assess whether retrieved documents contain relevant context (Self-RAG check)."""
    t0 = time.perf_counter()
    question = state["question"]
    documents = state.get("documents", [])
    trace = state["trace"]

    if not documents:
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        trace["stages"].append(
            {
                "stage": "graph_grade_documents",
                "relevant": False,
                "reason": "No documents retrieved",
                "timings_ms": elapsed,
            }
        )
        return {
            "needs_rewrite": True,
            "document_grades": [{"relevant": False, "reason": "empty"}],
            "trace": trace,
        }

    if not settings.grade_documents or not settings.llm_api_key:
        # Fallback heuristic: check if top chunk has good similarity score
        top_score = documents[0].get("score") or 0.0
        relevant = top_score > 0.35 if documents else False
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        trace["stages"].append(
            {
                "stage": "graph_grade_documents",
                "relevant": relevant,
                "reason": f"Heuristic score check: top score {round(top_score, 4)}",
                "timings_ms": elapsed,
            }
        )
        return {
            "needs_rewrite": not relevant,
            "document_grades": [{"relevant": relevant, "method": "heuristic"}],
            "trace": trace,
        }

    # Use LLM evaluator for document relevance grading
    system_prompt = (
        "You are an expert evaluator assessing whether retrieved passages contain "
        "relevant information to answer a user's question. Respond in JSON only with:\n"
        "{\"relevant\": true or false, \"reason\": \"brief explanation\"}"
    )
    context_preview = "\n\n".join(
        f"[{d.get('filename')} p.{d.get('page')}]: {d.get('text', '')[:300]}"
        for d in documents[:3]
    )
    user_prompt = f"Question: {question}\n\nPassages:\n{context_preview}"

    try:
        raw = await llm_client.call_llm_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=150,
            temperature=0.0,
        )
        # Parse JSON
        raw_clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.S | re.I).strip()
        raw_clean = re.sub(r"```(?:json)?", "", raw_clean).strip()
        data = json.loads(raw_clean)
        relevant = bool(data.get("relevant", True))
        reason = data.get("reason", "")
    except Exception as e:
        flow_log("graph.grade_documents.error", error=str(e))
        relevant = True  # Fail open
        reason = f"Grading skipped: {str(e)}"

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    trace["timings_ms"]["graph_grade_documents"] = elapsed
    trace["stages"].append(
        {
            "stage": "graph_grade_documents",
            "relevant": relevant,
            "reason": reason,
            "timings_ms": elapsed,
        }
    )

    flow_log("graph.grade_documents", relevant=relevant, reason=reason)
    return {
        "needs_rewrite": not relevant,
        "document_grades": [{"relevant": relevant, "reason": reason}],
        "trace": trace,
    }


def decide_to_generate(state: RAGGraphState) -> str:
    """Conditional edge: decide whether to rewrite and retry or proceed to generate."""
    if state["needs_rewrite"] and state["retry_count"] < state["max_retries"]:
        return "rewrite_query"
    return "generate"


async def rewrite_query_node(state: RAGGraphState) -> Dict[str, Any]:
    """Self-correction: formulate an improved search query when retrieval failed."""
    t0 = time.perf_counter()
    question = state["question"]
    trace = state["trace"]
    retry_count = state.get("retry_count", 0) + 1

    try:
        new_query = await query_rewriter.rewrite_query(question)
    except Exception as e:
        flow_log("graph.rewrite_query.error", error=str(e))
        new_query = question

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    trace["timings_ms"][f"graph_rewrite_retry_{retry_count}"] = elapsed
    trace["stages"].append(
        {
            "stage": "graph_self_correction_rewrite",
            "retry_count": retry_count,
            "before": question,
            "after": new_query,
            "timings_ms": elapsed,
        }
    )

    flow_log("graph.rewrite_query", retry=retry_count, new_query=new_query)
    return {
        "search_query": new_query,
        "retry_count": retry_count,
        "trace": trace,
    }


async def generate_node(state: RAGGraphState) -> Dict[str, Any]:
    """Generate the grounded answer using retrieved documents."""
    t0 = time.perf_counter()
    question = state["question"]
    documents = state.get("documents", [])
    trace = state["trace"]

    cfg = state.get("config", {})
    if cfg.get("retrieval_only"):
        answer = "(retrieval_only=true — generation skipped)"
    elif not documents:
        answer = "No relevant documents were found in the knowledge base to answer your question."
    else:
        answer = await llm_client.generate_answer(question, documents)

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    trace["timings_ms"]["graph_generate"] = elapsed
    trace["stages"].append(
        {
            "stage": "graph_generate",
            "document_count": len(documents),
            "retrieval_only": bool(cfg.get("retrieval_only")),
            "timings_ms": elapsed,
        }
    )

    flow_log("graph.generate", answer_preview=answer[:100])
    return {
        "answer": answer,
        "trace": trace,
    }


async def grade_generation_node(state: RAGGraphState) -> Dict[str, Any]:
    """Assess answer groundedness against retrieved context."""
    t0 = time.perf_counter()
    answer = state.get("answer", "")
    documents = state.get("documents", [])
    trace = state["trace"]
    cfg = state.get("config", {})

    if cfg.get("retrieval_only"):
        grade = "skipped_retrieval_only"
    elif not documents or not settings.grade_hallucinations or not settings.llm_api_key:
        grade = "unverified"
    else:
        citations = re.findall(r"\[([^\]]+\.pdf)\s+p\.(\d+)\]", answer)
        if citations:
            known_pairs = {(d.get("filename"), str(d.get("page"))) for d in documents}
            grounded = all((f, p) in known_pairs for f, p in citations)
            grade = "grounded" if grounded else "citation_mismatch"
        else:
            grade = "grounded_no_citations"

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    trace["timings_ms"]["graph_grade_generation"] = elapsed
    trace["stages"].append(
        {
            "stage": "graph_grade_generation",
            "hallucination_grade": grade,
            "timings_ms": elapsed,
        }
    )

    flow_log("graph.grade_generation", grade=grade)
    return {
        "hallucination_grade": grade,
        "trace": trace,
    }


# --- Build StateGraph ------------------------------------------------------

def create_rag_graph():
    workflow = StateGraph(RAGGraphState)

    workflow.add_node("route_query", route_query_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("grade_documents", grade_documents_node)
    workflow.add_node("rewrite_query", rewrite_query_node)
    workflow.add_node("generate", generate_node)
    workflow.add_node("grade_generation", grade_generation_node)

    workflow.add_edge(START, "route_query")
    workflow.add_edge("route_query", "retrieve")
    workflow.add_edge("retrieve", "grade_documents")
    workflow.add_conditional_edges(
        "grade_documents",
        decide_to_generate,
        {
            "rewrite_query": "rewrite_query",
            "generate": "generate",
        },
    )
    workflow.add_edge("rewrite_query", "retrieve")
    workflow.add_edge("generate", "grade_generation")
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
    """High-level runner invoked by API routes and evaluation harness."""
    graph = get_rag_graph()

    resolved_config = {
        "top_k": top_k or settings.top_k,
        "hybrid": hybrid if hybrid is not None else settings.hybrid_enabled,
        "rerank": rerank if rerank is not None else settings.rerank_enabled,
        "rewrite": rewrite if rewrite is not None else settings.rewrite_enabled,
        "mmr": mmr if mmr is not None else settings.mmr_enabled,
        "hyde": hyde,
        "retrieval_only": retrieval_only,
    }

    initial_state: RAGGraphState = {
        "question": question,
        "search_query": question,
        "documents": [],
        "answer": "",
        "retry_count": 0,
        "max_retries": settings.graph_max_retries,
        "needs_rewrite": False,
        "route": "semantic_concept",
        "document_grades": [],
        "hallucination_grade": None,
        "trace": {
            "original_question": question,
            "engine": "langgraph",
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
        "route": final_state.get("route"),
        "retry_count": final_state.get("retry_count", 0),
        "document_grades": final_state.get("document_grades", []),
        "hallucination_grade": final_state.get("hallucination_grade"),
    }

    return {
        "answer": final_state["answer"],
        "chunks": final_state["documents"],
        "trace": trace,
    }
