"""Loop detection for the docs_qa agent loop.

The existing budgets (MAX_ITERS/MAX_TOKENS/MAX_COST/MAX_WALL_CLOCK) stop a
runaway loop from running forever, but they don't notice the *behavioral*
failure of looping: calling the same tool with the same arguments over
and over, burning budget without making progress. This module catches
that specific pattern so we can short-circuit it cheaply -- by injecting
a corrective message instead of re-running the tool -- well before any
budget is exhausted.
"""

import hashlib
import json
from typing import Any, Dict, Optional


def make_call_signature(tool_name: str, args: Dict[str, Any]) -> str:
    """Canonical signature for a (tool, args) pair so repeats are detected
    even if the LLM reorders keys or changes whitespace/case slightly."""
    normalized = {
        str(k).strip().lower(): str(v).strip().lower()
        for k, v in (args or {}).items()
    }
    payload = json.dumps({"tool": (tool_name or "").strip().lower(), "args": normalized}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class LoopGuard:
    """Tracks tool-call signatures across one agent run.

    - REPEAT_LIMIT: how many times the *exact same* (tool, args) pair may
      be actually executed before we start intercepting it.
    - STALL_LAPS: how many consecutive laps of "tool call, no new
      information" before we declare the whole loop stalled and force
      termination (distinct from a single repeated call -- this catches
      e.g. alternating between two near-identical queries).
    """

    REPEAT_LIMIT = 1  # first repeat is intercepted, not the 2nd occurrence
    STALL_LAPS = 4

    def __init__(self) -> None:
        self.seen_calls: Dict[str, int] = {}
        self.consecutive_tool_only_laps = 0

    def register_and_check(self, tool_name: str, args: Dict[str, Any]) -> Optional[str]:
        """Call BEFORE executing a tool.

        Returns None if the call should proceed normally. Returns a
        corrective message string if the call should be intercepted
        (i.e. NOT actually executed again) -- the caller should feed
        this string back as the tool's observation instead of the real
        result, so the model self-corrects without burning a duplicate
        real tool execution or a wasted retrieval/API call.
        """
        sig = make_call_signature(tool_name, args)
        count = self.seen_calls.get(sig, 0)
        self.seen_calls[sig] = count + 1

        if count >= self.REPEAT_LIMIT:
            return (
                f"[LOOP GUARD] You already called {tool_name} with these "
                "exact arguments and already have that observation above. "
                "Do not repeat this call -- either use the prior result or "
                "provide your final answer now."
            )
        return None

    def note_tool_only_lap(self) -> None:
        self.consecutive_tool_only_laps += 1

    def note_progress_lap(self) -> None:
        self.consecutive_tool_only_laps = 0

    def is_stalled(self) -> bool:
        return self.consecutive_tool_only_laps >= self.STALL_LAPS
