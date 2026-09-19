"""Hand-built Developer Documentation Migration Agent Loop.

Enforces all 4 budgets on every loop lap:
1. MAX_ITERS
2. MAX_TOKENS (per-lap accumulation)
3. MAX_COST (per-lap accumulation)
4. MAX_WALL_CLOCK_SECONDS

Includes tool-calling dispatch with think/decision steps and clean termination.
"""

import asyncio
import json
import re
import time
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.flow_log import flow_log
from app.services.agents.docs_qa.doc_tools import TOOLS_SCHEMA, execute_tool

# Pricing per million tokens (Qwen/Llama standard tier rates: $0.35/1M input, $0.80/1M output)
PROMPT_COST_PER_TOKEN = 0.35 / 1_000_000.0
COMPLETION_COST_PER_TOKEN = 0.80 / 1_000_000.0

DEFAULT_MAX_ITERS = 10
DEFAULT_MAX_TOKENS = 120000
DEFAULT_MAX_COST = 0.05  # 5 cents
DEFAULT_MAX_WALL_CLOCK_SECONDS = 120.0

SYSTEM_PROMPT = """You are an expert Developer Documentation & SDK Migration Agent.
Your job is to answer API and SDK migration questions (e.g., migrating from v2 to v3).

You have access to 3 specialized tools:
1. `search_docs(query)`: Search developer guides, manuals, and PDFs for concepts, tutorials, and explanations.
2. `get_openapi_spec(endpoint_path)`: Fetch the OpenAPI 3.0 specification for an HTTP endpoint schema.
3. `check_deprecation(symbol_or_endpoint, api_version)`: Verify if a method/symbol/endpoint is deprecated in target version (v1, v2, v3) and get replacement details.

### ReAct (Reason + Act) & Chain-of-Thought (CoT) Prompting Methodology:
At every lap of your problem solving, strictly follow the ReAct reasoning paradigm:
- Thought: First, explicitly write out your step-by-step reasoning (Chain-of-Thought). Decompose the question into what you currently know, what specific facts are missing, and why you need to call a tool (or whether you have enough facts to answer).
- Action: Call the appropriate tool with exact arguments.
- Observation: Review the data returned from the tool.
- Repeat the Thought -> Action -> Observation cycle until you have all facts needed.
- Final Thought: State that all required facts have been gathered, and provide the complete final answer.

### Few-Shot ReAct Example:
Question: "How do I call getBackorders() in SDK v3, and what replaces the positional agencyId parameter?"
Thought: The user is asking about migrating `getBackorders()` in SDK v3. First, I must check if `getBackorders` has a deprecation or signature change record in v3.
Action: check_deprecation(symbol_or_endpoint="getBackorders", api_version="v3")
Observation: Deprecation Record [v3]: getBackorders positional parameter agencyId is deprecated. Replaced by options object { agencyId, includeDrafts }.
Thought: I have the deprecation notice showing the new options object signature. I do not need further tools. I will now write the final answer with a code snippet.
Final Answer: In SDK v3, `getBackorders()` replaces the legacy positional `agencyId` with an options object: `getBackorders({ agencyId: "123", includeDrafts: true })`...

Guidelines:
- Always precede your tool actions with a clear `Thought:` sentence explaining your reasoning.
- Do not make redundant or duplicate search queries. Once you have the deprecation status and specs, immediately answer.
- In your final response:
  * Explicitly state the API / SDK version (e.g. SDK v3 or API v3).
  * Do NOT recommend deprecated symbols without highlighting the migration replacement.
  * When mentioning HTTP endpoints, use the exact endpoint paths from the OpenAPI spec.
  * Provide a clean, syntactically valid code sample showing the v3 invocation.
"""


def _extract_code_sample(text: str) -> str:
    """Extract code block or inline code snippet from response text."""
    blocks = re.findall(r"```(?:[a-zA-Z0-9_-]*)\s*\n([\s\S]*?)```", text)
    if blocks:
        return blocks[0].strip()
    snippets = re.findall(r"`([^`\n]+)`", text)
    if snippets:
        return snippets[0].strip()
    return ""


async def run_docs_agent(
    question: str,
    max_iters: int = DEFAULT_MAX_ITERS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_cost: float = DEFAULT_MAX_COST,
    max_wall_clock_seconds: float = DEFAULT_MAX_WALL_CLOCK_SECONDS,
) -> Dict[str, Any]:
    """Runs the hand-built agent loop with full budget enforcement on every lap."""
    start_time = time.perf_counter()
    lap_count = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    total_cost = 0.0

    tools_called: List[str] = []
    lap_traces: List[Dict[str, Any]] = []

    budget_exceeded = False
    budget_fired: Optional[str] = None
    final_answer = ""

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    flow_log(
        "agent.loop.started",
        question=question,
        max_iters=max_iters,
        max_tokens=max_tokens,
        max_cost=max_cost,
        max_wall_clock_seconds=max_wall_clock_seconds,
    )

    while True:
        # --- 1. Pre-call Budget Checks ---
        elapsed = time.perf_counter() - start_time
        if elapsed >= max_wall_clock_seconds:
            budget_exceeded = True
            budget_fired = "MAX_WALL_CLOCK"
            flow_log("agent.budget_terminated", budget="MAX_WALL_CLOCK", elapsed_s=round(elapsed, 3))
            break

        if lap_count >= max_iters:
            budget_exceeded = True
            budget_fired = "MAX_ITERS"
            flow_log("agent.budget_terminated", budget="MAX_ITERS", lap_count=lap_count)
            break

        if total_tokens >= max_tokens:
            budget_exceeded = True
            budget_fired = "MAX_TOKENS"
            flow_log("agent.budget_terminated", budget="MAX_TOKENS", total_tokens=total_tokens)
            break

        if total_cost >= max_cost:
            budget_exceeded = True
            budget_fired = "MAX_COST"
            flow_log("agent.budget_terminated", budget="MAX_COST", total_cost=round(total_cost, 6))
            break

        lap_start = time.perf_counter()
        lap_idx = lap_count + 1

        # --- 2. Call LLM with Tool Schemas (force synthesis on final allowed lap) ---
        is_final_lap = (lap_idx == max_iters and lap_idx > 1)
        req_messages = list(messages)
        if is_final_lap:
            req_messages.append(
                {
                    "role": "user",
                    "content": "You have reached your research lap limit. Based on all the observations and evidence collected above, provide your final complete answer directly now.",
                }
            )

        payload = {
            "model": settings.llm_model,
            "messages": req_messages,
            "temperature": 0.0,
            "max_tokens": 750 if is_final_lap else 500,
        }
        if not is_final_lap:
            payload["tools"] = TOOLS_SCHEMA
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }

        data = None
        for attempt in range(5):
            try:
                async with httpx.AsyncClient(timeout=max(5.0, max_wall_clock_seconds - elapsed)) as client:
                    resp = await client.post(settings.llm_url, json=payload, headers=headers)
                    if resp.status_code == 429:
                        raw_reset = resp.headers.get("x-ratelimit-reset-tokens", "")
                        reset_s = 5.0
                        m = re.search(r"([\d\.]+)", raw_reset)
                        if m:
                            reset_s = float(m.group(1)) + 0.5
                        flow_log("agent.llm.rate_limited", lap=lap_idx, attempt=attempt, wait_seconds=reset_s)
                        await asyncio.sleep(min(reset_s, 60.0))
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    break
            except Exception as e:
                if attempt == 4:
                    flow_log("agent.llm.error", lap=lap_idx, error=str(e))
                    if "timeout" in str(e).lower() or (time.perf_counter() - start_time) >= max_wall_clock_seconds:
                        budget_exceeded = True
                        budget_fired = "MAX_WALL_CLOCK"
                    final_answer = f"Agent encountered error during LLM invocation: {str(e)}"
                    break
                await asyncio.sleep(2.0)

        if data is None:
            break

        # --- 3. Accumulate Tokens & Cost across EVERY lap ---
        usage = data.get("usage", {})
        lap_prompt = usage.get("prompt_tokens", 0)
        lap_completion = usage.get("completion_tokens", 0)
        lap_tokens = lap_prompt + lap_completion

        # Fallback estimation if provider returns empty usage
        if lap_tokens == 0:
            lap_prompt = sum(len(m.get("content", "")) // 4 for m in messages)
            lap_completion = len(data.get("choices", [{}])[0].get("message", {}).get("content", "") or "") // 4
            lap_tokens = lap_prompt + lap_completion

        total_prompt_tokens += lap_prompt
        total_completion_tokens += lap_completion
        total_tokens += lap_tokens

        lap_cost = (lap_prompt * PROMPT_COST_PER_TOKEN) + (lap_completion * COMPLETION_COST_PER_TOKEN)
        total_cost += lap_cost

        lap_elapsed = time.perf_counter() - lap_start
        lap_count += 1

        # --- 4. Post-call Budget Checks ---
        cum_elapsed = time.perf_counter() - start_time
        if cum_elapsed >= max_wall_clock_seconds:
            budget_exceeded = True
            budget_fired = "MAX_WALL_CLOCK"
            flow_log("agent.budget_terminated", budget="MAX_WALL_CLOCK", elapsed_s=round(cum_elapsed, 3))
            break

        if total_tokens >= max_tokens:
            budget_exceeded = True
            budget_fired = "MAX_TOKENS"
            flow_log("agent.budget_terminated", budget="MAX_TOKENS", total_tokens=total_tokens)
            break

        if total_cost >= max_cost:
            budget_exceeded = True
            budget_fired = "MAX_COST"
            flow_log("agent.budget_terminated", budget="MAX_COST", total_cost=round(total_cost, 6))
            break

        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        msg_tool_calls = msg.get("tool_calls")
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning") or ""
        if not reasoning and "<think>" in content:
            m_think = re.search(r"<think>(.*?)</think>", content, flags=re.S | re.I)
            if m_think:
                reasoning = m_think.group(1).strip()
        if not reasoning and "Thought:" in content:
            m_thought = re.search(r"Thought:\s*(.*?)(?=\nAction:|\nFinal Answer:|\nEXECUTE|\n\n|$)", content, flags=re.S | re.I)
            if m_thought:
                reasoning = m_thought.group(1).strip()

        # --- 5. Tool Decision / Dispatch ---
        if msg_tool_calls:
            # Append assistant message with tool calls to message history
            messages.append(msg)

            lap_executed_tools = []
            for tc in msg_tool_calls:
                call_id = tc.get("id")
                fn = tc.get("function", {})
                fn_name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {}

                tools_called.append(fn_name)
                # Execute tool
                tool_output = await execute_tool(fn_name, args)

                lap_executed_tools.append(
                    {
                        "tool": fn_name,
                        "args": args,
                        "output": tool_output,
                        "output_preview": tool_output[:140],
                    }
                )

                # Append tool observation message
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": fn_name,
                        "content": tool_output,
                    }
                )

            lap_traces.append(
                {
                    "lap": lap_idx,
                    "type": "tool_call",
                    "reasoning": reasoning[:200] if reasoning else "",
                    "tools": lap_executed_tools,
                    "lap_tokens": lap_tokens,
                    "cum_tokens": total_tokens,
                    "lap_time_s": round(lap_elapsed, 3),
                }
            )
            flow_log(
                "agent.lap.tool_call",
                lap=lap_idx,
                tools=[t["tool"] for t in lap_executed_tools],
                cum_tokens=total_tokens,
            )
            # Continue loop to next lap
            continue
        else:
            # Model generated a direct answer without tool call -> Completed
            clean_content = re.sub(r"<think>(?:.*?</think>|.*$)", "", content, flags=re.S | re.I).strip()
            if "Final Answer:" in clean_content:
                clean_content = clean_content.split("Final Answer:", 1)[-1].strip()
            else:
                clean_content = re.sub(r"^Thought:\s*.*?(?=\n\n|\n[A-Z]|$)", "", clean_content, flags=re.S).strip()
            final_answer = clean_content if clean_content else content.strip()
            lap_traces.append(
                {
                    "lap": lap_idx,
                    "type": "final_answer",
                    "reasoning": reasoning[:200] if reasoning else "",
                    "answer_preview": final_answer[:120],
                    "lap_tokens": lap_tokens,
                    "cum_tokens": total_tokens,
                    "lap_time_s": round(lap_elapsed, 3),
                }
            )
            flow_log("agent.lap.finished", lap=lap_idx, cum_tokens=total_tokens)
            break

    total_wall_clock = round(time.perf_counter() - start_time, 3)

    if budget_exceeded:
        if not final_answer:
            final_answer = (
                f"[TERMINATED_EARLY] Agent budget '{budget_fired}' fired at lap {lap_count} "
                f"(total tokens: {total_tokens}, cost: ${round(total_cost, 5)}, wall-clock: {total_wall_clock}s). "
                f"Loop halted cleanly to prevent runaway execution."
            )

    code_sample = _extract_code_sample(final_answer)

    result = {
        "answer": final_answer,
        "code_sample": code_sample,
        "tools_called": tools_called,
        "lap_count": lap_count,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 6),
        "wall_clock_seconds": total_wall_clock,
        "budget_exceeded": budget_exceeded,
        "budget_fired": budget_fired,
        "lap_traces": lap_traces,
    }

    flow_log(
        "agent.completed",
        laps=lap_count,
        total_tokens=total_tokens,
        total_cost=round(total_cost, 6),
        wall_clock_s=total_wall_clock,
        budget_fired=budget_fired,
    )
    return result
