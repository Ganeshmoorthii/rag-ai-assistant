"""Retrieval Agent.

Finds, evaluates, and refines evidence needed to answer the user's query.

- Iterative Retrieval        -- search, evaluate the evidence, and
  rewrite/refine the query and search again when the evidence is
  insufficient, up to max_retries.
- Search Strategy Selection  -- dynamically choose semantic / BM25(hybrid) /
  rerank / MMR based on the query_analyser's routing hint, instead of a
  single static config.
- Evidence Quality Scoring   -- score retrieved evidence across relevance,
  coverage, authority, freshness, and contradiction, and use those signals
  (not a single boolean) to decide sufficiency.

Runs one iterative retrieval loop per sub-query from the query_analyser's
plan, concurrently, then merges everything into one deduplicated,
re-ranked document set for the response_agent.
"""

import asyncio
import json
import re
import time
from typing import Any, Dict, List

from app.core.config import settings
from app.core.flow_log import flow_log
from app.services.retrieval import query_rewriter, retriever
from app.services.llm import llm_client


SCORE_SYSTEM = (
    "You evaluate retrieved passages against a user question for a "
    "retrieval-augmented generation system. Score across five dimensions, "
    "each 0.0-1.0 (except contradiction, which is boolean):\n"
    "- relevance: do the passages address the question directly?\n"
    "- coverage: do they cover ALL aspects of the question, or only part?\n"
    "- authority: do they read as authoritative source material (vs vague "
    "or tangential)?\n"
    "- freshness: is there any sign this content is outdated or superseded "
    "relative to the question? (1.0 = no such sign)\n"
    "- contradiction: do any of the passages contradict each other?\n\n"
    "Respond in JSON ONLY:\n"
    '{"relevance": 0.0, "coverage": 0.0, "authority": 0.0, "freshness": 0.0, '
    '"contradiction": false, "reason": "brief explanation"}'
)

# Evidence counts as sufficient once relevance and coverage both clear the
# bar and there's no contradiction. Authority/freshness inform the reason
# surfaced in the trace and to the response_agent, but don't alone block
# generation -- plenty of internal docs are authoritative without a formal
# "freshness" signal to point to.
RELEVANCE_THRESHOLD = 0.6
COVERAGE_THRESHOLD = 0.5


def _extract_json(raw: str) -> Dict[str, Any]:
    raw_clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.S | re.I).strip()
    raw_clean = re.sub(r"```(?:json)?", "", raw_clean).strip()
    return json.loads(raw_clean)


def select_strategy(route: str, base_config: Dict[str, Any]) -> Dict[str, Any]:
    """Dynamically pick retrieval strategy flags for this query.

    `base_config` carries any explicit overrides the caller (API request)
    supplied -- those always win. Anything left as None is decided HERE
    based on the query's route, rather than falling through to one fixed
    .env default for every query.
    """
    cfg = dict(base_config)

    if cfg.get("hybrid") is None:
        # Exact identifiers are BM25's territory; dense-only search
        # routinely misses them entirely.
        cfg["hybrid"] = True if route == "exact_identifier" else settings.hybrid_enabled
    if cfg.get("rerank") is None:
        cfg["rerank"] = settings.rerank_enabled
    if cfg.get("mmr") is None:
        # Concept-y questions benefit more from diversity; exact-identifier
        # lookups usually want the single best match, not spread coverage.
        cfg["mmr"] = settings.mmr_enabled if route == "semantic_concept" else False

    return cfg


async def score_evidence(question: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Multi-dimensional evidence quality scoring."""
    if not documents:
        return {
            "relevance": 0.0,
            "coverage": 0.0,
            "authority": 0.0,
            "freshness": 0.0,
            "contradiction": False,
            "reason": "No documents retrieved",
            "method": "empty",
        }

    if not settings.grade_documents or not settings.llm_api_key:
        top_score = documents[0].get("score") or 0.0
        relevance = min(max(top_score, 0.0), 1.0)
        return {
            "relevance": relevance,
            "coverage": relevance,
            "authority": 0.5,
            "freshness": 1.0,
            "contradiction": False,
            "reason": f"Heuristic score check: top score {round(top_score, 4)}",
            "method": "heuristic",
        }

    context_preview = "\n\n".join(
        f"[{d.get('filename')} p.{d.get('page')}]: {d.get('text', '')[:300]}"
        for d in documents[:5]
    )
    user_prompt = f"Question: {question}\n\nPassages:\n{context_preview}"

    try:
        raw = await llm_client.call_llm_text(
            system_prompt=SCORE_SYSTEM,
            user_prompt=user_prompt,
            max_tokens=200,
            temperature=0.0,
        )
        data = _extract_json(raw)
        return {
            "relevance": float(data.get("relevance", 0.5)),
            "coverage": float(data.get("coverage", 0.5)),
            "authority": float(data.get("authority", 0.5)),
            "freshness": float(data.get("freshness", 1.0)),
            "contradiction": bool(data.get("contradiction", False)),
            "reason": data.get("reason", ""),
            "method": "llm",
        }
    except Exception as e:  # noqa: BLE001 - fail open, never block on grading
        flow_log("retrieval_agent.score_evidence.error", error=str(e))
        return {
            "relevance": 1.0,
            "coverage": 1.0,
            "authority": 0.5,
            "freshness": 1.0,
            "contradiction": False,
            "reason": f"Scoring skipped: {str(e)}",
            "method": "fail_open",
        }


def _is_sufficient(scores: Dict[str, Any]) -> bool:
    return (
        scores.get("relevance", 0.0) >= RELEVANCE_THRESHOLD
        and scores.get("coverage", 0.0) >= COVERAGE_THRESHOLD
        and not scores.get("contradiction", False)
    )


async def _retrieve_for_subquery(
    sub_query: str,
    route: str,
    base_config: Dict[str, Any],
    max_retries: int,
) -> Dict[str, Any]:
    """Run the search -> evaluate -> rewrite -> search-again loop for one sub-query.

        Search
          |
          v
      Evaluate Evidence
          |
          v
      Sufficient? --YES--> stop
          |
          NO (and retries remain)
          |
          v
      Rewrite / Refine Query --> Search again
    """
    strategy = select_strategy(route, base_config)
    search_query = sub_query
    retry_count = 0
    documents: List[Dict[str, Any]] = []
    scores: Dict[str, Any] = {}
    laps: List[Dict[str, Any]] = []

    while True:
        result = await retriever.retrieve(
            question=search_query,
            top_k=base_config.get("top_k"),
            hybrid=strategy["hybrid"],
            rerank=strategy["rerank"],
            rewrite=False,  # this agent owns its own rewrite step below
            mmr=strategy["mmr"],
            hyde=False,
        )
        documents = result["chunks"]
        scores = await score_evidence(sub_query, documents)
        sufficient = _is_sufficient(scores)

        laps.append(
            {
                "attempt": retry_count,
                "search_query": search_query,
                "strategy": strategy,
                "document_count": len(documents),
                "scores": scores,
                "sufficient": sufficient,
            }
        )

        flow_log(
            "retrieval_agent.lap",
            sub_query=sub_query,
            attempt=retry_count,
            search_query=search_query,
            sufficient=sufficient,
            scores=scores,
        )

        if sufficient or retry_count >= max_retries:
            break

        retry_count += 1
        try:
            search_query = await query_rewriter.rewrite_query(sub_query)
        except Exception as e:  # noqa: BLE001
            flow_log("retrieval_agent.rewrite_failed", error=str(e))
            break

    return {
        "sub_query": sub_query,
        "search_query": search_query,
        "documents": documents,
        "scores": scores,
        "sufficient": _is_sufficient(scores),
        "retry_count": retry_count,
        "laps": laps,
    }


def _merge_documents(sub_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate by chunk id across sub-queries, keeping the best score."""
    merged: Dict[str, Dict[str, Any]] = {}
    for sr in sub_results:
        for doc in sr["documents"]:
            cid = doc["id"]
            existing = merged.get(cid)
            if existing is None or (doc.get("score") or 0) > (existing.get("score") or 0):
                merged[cid] = doc
    ranked = sorted(merged.values(), key=lambda d: -(d.get("score") or 0))
    for rank, d in enumerate(ranked, start=1):
        d["rank"] = rank
    return ranked


async def run_retrieval_agent(
    sub_queries: List[str],
    route: str,
    base_config: Dict[str, Any],
    max_retries: int,
) -> Dict[str, Any]:
    """Run the iterative retrieval loop across all sub-queries concurrently.

    Complex queries (more than one sub-query) fan out into one retrieval
    loop per sub-query, run with asyncio.gather, then merge into a single
    deduplicated document set. Simple queries are just the len==1 case of
    the same code path.
    """
    t0 = time.perf_counter()

    sub_results = await asyncio.gather(
        *[
            _retrieve_for_subquery(sq, route, base_config, max_retries)
            for sq in sub_queries
        ]
    )
    sub_results = list(sub_results)

    documents = _merge_documents(sub_results)
    overall_sufficient = all(sr["sufficient"] for sr in sub_results)

    elapsed = round((time.perf_counter() - t0) * 1000, 1)

    flow_log(
        "retrieval_agent.completed",
        sub_query_count=len(sub_queries),
        document_count=len(documents),
        overall_sufficient=overall_sufficient,
        elapsed_ms=elapsed,
    )

    return {
        "documents": documents,
        "sub_results": sub_results,
        "sufficient": overall_sufficient,
        "elapsed_ms": elapsed,
    }


# --- LangGraph node ---------------------------------------------------------

async def retrieval_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node wrapper: run the retrieval agent over the query plan."""
    cfg = state["config"]
    sub_queries = state.get("sub_queries") or [state["question"]]
    route = state.get("route", "semantic_concept")
    max_retries = state.get("max_retries", settings.graph_max_retries)
    trace = state["trace"]

    result = await run_retrieval_agent(sub_queries, route, cfg, max_retries)

    trace["timings_ms"]["retrieval_agent"] = result["elapsed_ms"]
    trace["stages"].append(
        {
            "stage": "retrieval_agent",
            "sub_query_count": len(sub_queries),
            "document_count": len(result["documents"]),
            "sufficient": result["sufficient"],
            "sub_results": [
                {
                    "sub_query": sr["sub_query"],
                    "final_search_query": sr["search_query"],
                    "retry_count": sr["retry_count"],
                    "scores": sr["scores"],
                    "document_count": len(sr["documents"]),
                }
                for sr in result["sub_results"]
            ],
            "timings_ms": result["elapsed_ms"],
        }
    )
    trace["final_chunk_ids"] = [d["id"] for d in result["documents"]]

    return {
        "documents": result["documents"],
        "evidence_sufficient": result["sufficient"],
        "sub_results": result["sub_results"],
        "trace": trace,
    }
