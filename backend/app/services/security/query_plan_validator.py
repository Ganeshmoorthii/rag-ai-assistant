"""Pre-fan-out validation for the query_analyser agent's decomposition.

This is the rag_graph pipeline's equivalent of docs_qa's tool_validator:
bound and sanity-check LLM-produced structure BEFORE it's allowed to
drive downstream work, instead of trusting it blindly. Here the
"structure" is a list of sub-queries rather than a tool call, and the
risk isn't a wrong tool -- it's an ungrounded/hallucinated decomposition
silently multiplying retrieval cost and latency (each sub-query spawns
its own concurrent retrieval loop).

Kept in services/security/ (next to answer_guard, injection_guard,
loop_guard, validation) so all cross-agent guard logic lives in one
place instead of being duplicated inline per agent.
"""

from typing import Any, Dict, List

# Hard cap on fan-out.
MAX_SUB_QUERIES = 4
MIN_SUB_QUERY_WORDS = 2
MAX_SUB_QUERY_WORDS = 40


def validate_sub_queries(raw_sub_queries: List[str], original_question: str) -> Dict[str, Any]:
    """Sanity-check and bound the query_analyser's own decomposition output.

    Returns the cleaned list plus a small guardrail report so the trace can
    show *why* the plan differs from the raw LLM output, instead of the
    fan-out silently changing shape.
    """
    seen_lower = set()
    deduped: List[str] = []
    dropped_empty_or_length = 0
    dropped_duplicate = 0

    for q in raw_sub_queries:
        q = (q or "").strip()
        if not q:
            dropped_empty_or_length += 1
            continue
        word_count = len(q.split())
        if word_count < MIN_SUB_QUERY_WORDS or word_count > MAX_SUB_QUERY_WORDS:
            dropped_empty_or_length += 1
            continue
        key = q.lower()
        if key in seen_lower:
            dropped_duplicate += 1
            continue
        seen_lower.add(key)
        deduped.append(q)

    capped = deduped[:MAX_SUB_QUERIES]
    truncated = len(deduped) > MAX_SUB_QUERIES

    if not capped:
        # Every candidate was rejected -- fail open to the original
        # question rather than returning an empty plan.
        capped = [original_question]

    return {
        "sub_queries": capped,
        "guardrails": {
            "dropped_empty_or_length": dropped_empty_or_length,
            "dropped_duplicate": dropped_duplicate,
            "truncated_to_max": truncated,
            "raw_count": len(raw_sub_queries),
            "final_count": len(capped),
        },
    }
