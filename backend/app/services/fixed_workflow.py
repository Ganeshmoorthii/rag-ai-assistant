"""Fixed Developer Documentation Workflow.

Re-implements the identical documentation migration task as a hard-coded,
linear workflow without loops:
- Step 1: Documentation retrieval via `search_docs`
- Step 2: OpenAPI endpoint inspection via `get_openapi_spec`
- Step 3: Deprecation lookup via `check_deprecation`
- Step 4: Single LLM synthesis into migration guidance and v3 code sample

Uses the same tools, same LLM model, and same output contract as docs_agent.
"""

import asyncio
import json
import re
import time
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.flow_log import flow_log
from app.services.doc_tools import ApiVersion, check_deprecation, get_openapi_spec, search_docs

PROMPT_COST_PER_TOKEN = 0.35 / 1_000_000.0
COMPLETION_COST_PER_TOKEN = 0.80 / 1_000_000.0

WORKFLOW_SYSTEM_PROMPT = """You are an expert Developer Documentation & SDK Migration Assistant.
Answer the user's migration question using the provided context from documentation guides,
OpenAPI specifications, and deprecation records.

Requirements:
- Explicitly state the API or SDK version (e.g., v3 or SDK v3).
- Do not recommend deprecated v2 patterns without specifying the v3 replacement.
- When mentioning HTTP endpoints, use the exact endpoint paths from the OpenAPI spec (e.g. /orders/verification or /api/orders/{id}/po).
- Provide a clear, syntactically valid code sample or HTTP request snippet for v3.
"""


def _extract_code_sample(text: str) -> str:
    blocks = re.findall(r"```(?:[a-zA-Z0-9_-]*)\s*\n([\s\S]*?)```", text)
    if blocks:
        return blocks[0].strip()
    snippets = re.findall(r"`([^`\n]+)`", text)
    if snippets:
        return snippets[0].strip()
    return ""


def _extract_candidate_identifiers(question: str) -> Dict[str, str]:
    """Extracts endpoint path and code symbol heuristically from the input question."""
    # Find HTTP endpoint pattern
    endpoint_match = re.search(r"(/(?:api|orders|ebi|health)[a-zA-Z0-9_\-\{\}\./]*)", question)
    endpoint = endpoint_match.group(1).rstrip(".,;:)'\"`]") if endpoint_match else ""

    # Find backtick code symbol or camelCase/function name
    symbol_match = re.search(r"`([a-zA-Z0-9_\(\)]+)`", question)
    if symbol_match:
        symbol = symbol_match.group(1).replace("()", "")
    else:
        # Check camelCase
        cc_match = re.search(r"\b([a-zA-Z]+[A-Z][a-zA-Z0-9]*)\b", question)
        symbol = cc_match.group(1) if cc_match else ""

    return {"endpoint": endpoint, "symbol": symbol}


async def run_fixed_workflow(question: str) -> Dict[str, Any]:
    """Executes the 4-step fixed linear workflow without any loop."""
    start_time = time.perf_counter()
    tools_called: List[str] = []
    step_traces: List[Dict[str, Any]] = []

    flow_log("workflow.started", question=question)

    # --- Step 1: Search Prose Documentation ---
    t0 = time.perf_counter()
    tools_called.append("search_docs")
    docs_result = await search_docs(query=question, top_k=2)
    step_traces.append(
        {
            "step": 1,
            "tool": "search_docs",
            "time_s": round(time.perf_counter() - t0, 3),
            "preview": docs_result[:100],
        }
    )

    # --- Step 2: Inspect OpenAPI Spec ---
    t1 = time.perf_counter()
    ids = _extract_candidate_identifiers(question)
    endpoint = ids["endpoint"]
    if not endpoint:
        # Default probe path from search/question keywords if relevant
        if "backorder" in question.lower():
            endpoint = "/ebi/backorders"
        elif "impersonate" in question.lower():
            endpoint = "/api/v1/impersonate"
        elif "verification" in question.lower() or "sticker" in question.lower():
            endpoint = "/orders/verification"
        elif "revenue" in question.lower():
            endpoint = "/api/revenue"
        else:
            endpoint = "/api/v2/orders"

    tools_called.append("get_openapi_spec")
    spec_result = get_openapi_spec(endpoint_path=endpoint)
    step_traces.append(
        {
            "step": 2,
            "tool": "get_openapi_spec",
            "time_s": round(time.perf_counter() - t1, 3),
            "endpoint": endpoint,
            "preview": spec_result[:100],
        }
    )

    # --- Step 3: Check Deprecations ---
    t2 = time.perf_counter()
    target_symbol = ids["symbol"] or ids["endpoint"] or question
    tools_called.append("check_deprecation")
    deprecations_result = check_deprecation(symbol_or_endpoint=target_symbol, api_version=ApiVersion.V3)
    step_traces.append(
        {
            "step": 3,
            "tool": "check_deprecation",
            "time_s": round(time.perf_counter() - t2, 3),
            "target": target_symbol,
            "preview": deprecations_result[:100],
        }
    )

    # --- Step 4: Synthesize in Single LLM Call (No Loop) ---
    t3 = time.perf_counter()
    user_prompt = (
        f"Question: {question}\n\n"
        f"--- CONTEXT 1: Documentation Search ---\n{docs_result}\n\n"
        f"--- CONTEXT 2: OpenAPI Specification ---\n{spec_result}\n\n"
        f"--- CONTEXT 3: Deprecation Catalog [v3] ---\n{deprecations_result}\n\n"
        "Provide a comprehensive, accurate migration answer explicitly stating the API/SDK version "
        "and providing a v3 code/request snippet."
    )

    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": WORKFLOW_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 500,
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    data = None
    for attempt in range(5):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(settings.llm_url, json=payload, headers=headers)
                if resp.status_code == 429:
                    raw_reset = resp.headers.get("x-ratelimit-reset-tokens", "")
                    reset_s = 5.0
                    m = re.search(r"([\d\.]+)", raw_reset)
                    if m:
                        reset_s = float(m.group(1)) + 0.5
                    flow_log("workflow.llm.rate_limited", attempt=attempt, wait_seconds=reset_s)
                    await asyncio.sleep(min(reset_s, 60.0))
                    continue
                if resp.status_code != 200:
                    flow_log("workflow.llm.error_status", status=resp.status_code, text=resp.text[:250])
                resp.raise_for_status()
                data = resp.json()
                break
        except Exception as e:
            flow_log("workflow.llm.exception", attempt=attempt, error=str(e))
            if attempt == 4:
                raise e
            await asyncio.sleep(2.0)

    if data is None:
        raise RuntimeError("Failed to obtain LLM response after 4 attempts.")

    usage = data.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    if (prompt_tokens + completion_tokens) == 0:
        prompt_tokens = len(user_prompt) // 4
        completion_tokens = len(data.get("choices", [{}])[0].get("message", {}).get("content", "")) // 4

    total_tokens = prompt_tokens + completion_tokens
    total_cost = (prompt_tokens * PROMPT_COST_PER_TOKEN) + (completion_tokens * COMPLETION_COST_PER_TOKEN)

    raw_answer = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    clean_ans = re.sub(r"<think>.*?</think>", "", raw_answer, flags=re.S | re.I).strip()
    final_answer = clean_ans if clean_ans else raw_answer
    code_sample = _extract_code_sample(final_answer)

    step_traces.append(
        {
            "step": 4,
            "tool": "llm_synthesis",
            "time_s": round(time.perf_counter() - t3, 3),
            "tokens": total_tokens,
        }
    )

    wall_clock = round(time.perf_counter() - start_time, 3)

    flow_log(
        "workflow.completed",
        steps=4,
        total_tokens=total_tokens,
        total_cost=round(total_cost, 6),
        wall_clock_s=wall_clock,
    )

    return {
        "answer": final_answer,
        "code_sample": code_sample,
        "tools_called": tools_called,
        "step_count": 4,
        "total_prompt_tokens": prompt_tokens,
        "total_completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 6),
        "wall_clock_seconds": wall_clock,
        "budget_exceeded": False,
        "budget_fired": None,
        "step_traces": step_traces,
    }
