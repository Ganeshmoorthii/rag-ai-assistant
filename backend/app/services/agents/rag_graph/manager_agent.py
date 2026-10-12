"""Manager agent for routing queries to specialist capabilities."""

import json
import re
import time
from typing import Any, Dict

from app.core.flow_log import flow_log
from app.services.llm import llm_client
from app.services.security.injection_guard import wrap_user_question

MANAGER_SYSTEM = (
    "Decide whether answering the user's question requires current records from "
    "the operational database, in addition to document research. Use live data "
    "only when the user asks about current/latest status, quantities, or records "
    "such as agencies, inventory, backorders, commissions, or SDK versions. "
    "General explanations of these topics do not require live data. Respond in "
    'JSON only: {"use_live_data": true or false, "reason": "short reason"}.'
)

_LIVE_DATA_HINTS = re.compile(
    r"\b(current(?:ly)?|latest|today|right now|live|status|in stock|available quantity)\b"
    r"|\b(how many|count|list|show|look up|lookup|check|get|find)\b.{0,60}"
    r"\b(agenc(?:y|ies)|inventor(?:y|ies)|stock|backorders?|commissions?|sdk versions?)\b",
    re.I,
)


def _fallback_plan(question: str) -> Dict[str, Any]:
    return {
        "use_live_data": bool(_LIVE_DATA_HINTS.search(question)),
        "reason": "Fallback routing used because manager planning was unavailable.",
    }


def _parse_plan(raw: str) -> Dict[str, Any]:
    content = re.sub(r"<think>.*?</think>", "", raw, flags=re.S | re.I).strip()
    content = re.sub(r"```(?:json)?", "", content).strip()
    data = json.loads(content)
    use_live_data = data.get("use_live_data")
    if not isinstance(use_live_data, bool):
        raise ValueError("use_live_data must be a boolean")
    reason = data.get("reason", "")
    if not isinstance(reason, str):
        reason = ""
    return {"use_live_data": use_live_data, "reason": reason[:160]}


async def plan_query(question: str) -> Dict[str, Any]:
    """Choose whether live operational data is needed; fail closed to docs."""
    try:
        raw = await llm_client.call_llm_text(
            system_prompt=MANAGER_SYSTEM,
            user_prompt=wrap_user_question(question),
            max_tokens=100,
            temperature=0.0,
        )
        return _parse_plan(raw)
    except Exception as error:  # noqa: BLE001 - manager failure must not block RAG
        flow_log("manager.plan_failed", error=str(error))
        return _fallback_plan(question)


async def manager_node(state: Dict[str, Any]) -> Dict[str, Any]:
    question = state["question"]
    trace = state["trace"]
    started = time.perf_counter()
    if state.get("config", {}).get("retrieval_only"):
        plan = {"use_live_data": False, "reason": "Retrieval-only mode skips live data."}
    else:
        plan = await plan_query(question)
    elapsed = round((time.perf_counter() - started) * 1000, 1)

    trace["timings_ms"]["manager"] = elapsed
    trace["stages"].append(
        {
            "stage": "manager",
            "use_live_data": plan["use_live_data"],
            "reason": plan["reason"],
            "timings_ms": elapsed,
        }
    )
    flow_log("manager.routed", **plan)
    return {"use_live_data": plan["use_live_data"], "trace": trace}