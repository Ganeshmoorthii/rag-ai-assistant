"""Query Analyser Agent.

Analyzes the user's query and produces a retrieval plan for the
retrieval_agent to execute:

- Query Decomposition   -- split multi-part questions into independent
  sub-queries, each with its own retrieval pass.
- Query Classification  -- identify intent: factual_lookup, comparison,
  summarization, troubleshooting, or explanation.
- Query Complexity Detection -- decide whether the question needs a single
  retrieval pass ("simple") or the full agentic multi-query flow
  ("complex").
"""

import json
import re
import time
from typing import Any, Dict, List

from app.core.flow_log import flow_log
from app.services.llm import llm_client
from app.services.security.query_plan_validator import validate_sub_queries

VALID_INTENTS = {
    "factual_lookup",
    "comparison",
    "summarization",
    "troubleshooting",
    "explanation",
}

DECOMPOSE_SYSTEM = (
    "You analyse a user question for a document retrieval system. Decide if "
    "it actually contains more than one independent question that each need "
    "their own evidence lookup (e.g. \"What is X and how does Y compare to "
    "Z?\"). Respond in JSON ONLY:\n"
    '{"sub_queries": ["...", "..."]}\n'
    "If the question is a single question, return a list with just that one "
    "question, reworded as a clean standalone query. Preserve exact "
    "identifiers, codes, and technical terms verbatim. Never invent "
    "sub-questions that were not implied by the original."
)

CLASSIFY_SYSTEM = (
    "Classify the user's question intent for a document retrieval system. "
    "Respond in JSON ONLY:\n"
    '{"intent": "..."}\n'
    "Where intent is exactly one of: factual_lookup, comparison, "
    "summarization, troubleshooting, explanation."
)

# Detects exact code symbols, camelCase, snake_case, ALL_CAPS, or endpoints.
# Used as a retrieval-strategy routing hint (handed to the retrieval_agent)
# and as a classification fallback if the LLM call fails.
_CODE_PATTERN = re.compile(
    r"(?:[A-Z0-9]+(?:[-_][A-Z0-9]+)+|\b[a-z]+(?:[A-Z][a-z0-9]+)+\b|\b/[a-z0-9/_-]+\b|`[^`]+`|\b[a-zA-Z0-9_]+\(\))"
)

# Cheap pre-filter before spending an LLM call on decomposition: a question
# with no conjunction / multiple question marks is almost certainly single-part.
_SPLIT_HINTS = re.compile(r"\band\b|\bor\b|;|\?.+\?", re.I)


def _extract_json(raw: str) -> Dict[str, Any]:
    raw_clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.S | re.I).strip()
    raw_clean = re.sub(r"```(?:json)?", "", raw_clean).strip()
    return json.loads(raw_clean)


async def decompose_query(question: str) -> Dict[str, Any]:
    """Split a query into independent sub-queries, if it has more than one.

    Returns the validated/bounded sub_queries plus a guardrails report --
    see app.services.security.query_plan_validator.validate_sub_queries
    for why raw LLM output is never trusted directly here. Each sub-query
    spawns its own concurrent retrieval loop downstream, so an
    ungrounded/hallucinated decomposition doesn't just give a wrong
    answer -- it silently multiplies cost and latency.
    """
    if not _SPLIT_HINTS.search(question):
        return {"sub_queries": [question], "guardrails": None}

    try:
        raw = await llm_client.call_llm_text(
            system_prompt=DECOMPOSE_SYSTEM,
            user_prompt=question,
            max_tokens=200,
            temperature=0.0,
        )
        data = _extract_json(raw)
        raw_sub_queries = [str(q) for q in data.get("sub_queries", [])]
        validated = validate_sub_queries(raw_sub_queries, question)
        g = validated["guardrails"]
        if g["dropped_empty_or_length"] or g["dropped_duplicate"] or g["truncated_to_max"]:
            flow_log("query_analyser.decompose_guardrail", question=question, **g)
        return validated
    except Exception as e:  # noqa: BLE001 - deliberate graceful degradation
        flow_log("query_analyser.decompose_failed", error=str(e))
        return {"sub_queries": [question], "guardrails": None}


async def classify_query(question: str) -> str:
    """Identify the user's intent."""
    try:
        raw = await llm_client.call_llm_text(
            system_prompt=CLASSIFY_SYSTEM,
            user_prompt=question,
            max_tokens=50,
            temperature=0.0,
        )
        data = _extract_json(raw)
        intent = str(data.get("intent", "")).strip().lower()
        if intent in VALID_INTENTS:
            return intent
    except Exception as e:  # noqa: BLE001
        flow_log("query_analyser.classify_failed", error=str(e))

    # Heuristic fallback if the LLM call failed or returned junk.
    q = question.lower()
    if any(w in q for w in ("vs", "versus", "compare", "difference between")):
        return "comparison"
    if any(w in q for w in ("summarize", "summarise", "overview", "tl;dr")):
        return "summarization"
    if any(w in q for w in ("error", "fail", "broken", "not working", "issue", "bug")):
        return "troubleshooting"
    if any(w in q for w in ("why", "how does", "explain")):
        return "explanation"
    return "factual_lookup"


def detect_route(question: str) -> str:
    """Exact-identifier vs semantic-concept routing hint for retrieval strategy."""
    return "exact_identifier" if _CODE_PATTERN.search(question) else "semantic_concept"


def detect_complexity(question: str, sub_queries: List[str]) -> str:
    """Simple (single retrieval pass) vs complex (agentic multi-query flow)."""
    if len(sub_queries) > 1:
        return "complex"
    # A single but long, multi-clause question can still warrant the
    # agentic flow even without an explicit decomposition split.
    return "complex" if len(question.split()) > 30 else "simple"


async def analyse_query(question: str) -> Dict[str, Any]:
    """Run the full analysis and return a retrieval plan."""
    t0 = time.perf_counter()

    decomposition = await decompose_query(question)
    sub_queries = decomposition["sub_queries"]
    intent = await classify_query(question)
    route = detect_route(question)
    complexity = detect_complexity(question, sub_queries)

    plan = {
        "sub_queries": sub_queries,
        "intent": intent,
        "route": route,
        "complexity": complexity,
    }

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    flow_log("query_analyser.completed", plan=plan, elapsed_ms=elapsed)
    return {"plan": plan, "elapsed_ms": elapsed}


# --- LangGraph node ---------------------------------------------------------

async def query_analyser_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node wrapper: analyse the question and populate the plan."""
    question = state["question"]
    trace = state["trace"]

    result = await analyse_query(question)
    plan = result["plan"]

    trace["timings_ms"]["query_analyser"] = result["elapsed_ms"]
    trace["stages"].append(
        {
            "stage": "query_analyser",
            "sub_queries": plan["sub_queries"],
            "intent": plan["intent"],
            "route": plan["route"],
            "complexity": plan["complexity"],
            "timings_ms": result["elapsed_ms"],
        }
    )

    flow_log("query_analyser.node", **plan)
    return {
        "sub_queries": plan["sub_queries"],
        "intent": plan["intent"],
        "route": plan["route"],
        "complexity": plan["complexity"],
        "trace": trace,
    }
