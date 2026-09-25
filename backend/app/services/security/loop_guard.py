"""Generic loop detection, shared across agent modes.

Originally lived only in docs_qa (guarding its ReAct tool-call loop).
Generalized here so the rag_graph retrieval_agent's search/rewrite loop
can use the same repeat-detection + stall-detection mechanics instead of
a bespoke `seen_queries` set, keeping "what counts as stalled" defined
in exactly one place.

Works on any (operation_name, params) pair -- for docs_qa that's
(tool_name, tool_args); for the retrieval_agent it's
("retrieve", {"search_query": ...}).
"""

import hashlib
import json
from typing import Any, Dict, Optional


def make_signature(operation: str, params: Dict[str, Any]) -> str:
    """Canonical signature for an (operation, params) pair so repeats are
    detected even if the caller reorders keys or changes whitespace/case
    slightly."""
    normalized = {
        str(k).strip().lower(): str(v).strip().lower()
        for k, v in (params or {}).items()
    }
    payload = json.dumps(
        {"op": (operation or "").strip().lower(), "params": normalized},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class LoopGuard:
    """Tracks operation signatures across one agent run / one sub-query loop.

    - REPEAT_LIMIT: how many times the *exact same* (operation, params)
      pair may actually execute before we start intercepting it.
    - STALL_LAPS: how many consecutive laps of "no new information" before
      the whole loop is declared stalled and should terminate (catches
      e.g. alternating between two near-identical queries, not just an
      exact repeat).
    """

    REPEAT_LIMIT = 1  # first repeat is intercepted, not the 2nd occurrence
    STALL_LAPS = 4

    def __init__(self) -> None:
        self.seen: Dict[str, int] = {}
        self.consecutive_no_progress_laps = 0

    def register_and_check(self, operation: str, params: Dict[str, Any]) -> Optional[str]:
        """Call BEFORE executing the operation.

        Returns None if it should proceed normally. Returns a corrective
        message string if it should be intercepted (i.e. NOT actually
        executed again) -- the caller should treat this as the
        observation/result instead of re-running the real operation.
        """
        sig = make_signature(operation, params)
        count = self.seen.get(sig, 0)
        self.seen[sig] = count + 1

        if count >= self.REPEAT_LIMIT:
            return (
                f"[LOOP GUARD] This exact {operation} call with these exact "
                "parameters was already made and already has an observation "
                "recorded above. Do not repeat it -- use the prior result or "
                "conclude now."
            )
        return None

    def note_no_progress_lap(self) -> None:
        self.consecutive_no_progress_laps += 1

    def note_progress_lap(self) -> None:
        self.consecutive_no_progress_laps = 0

    def is_stalled(self) -> bool:
        return self.consecutive_no_progress_laps >= self.STALL_LAPS
