"""Loop detection for the docs_qa agent loop.

Thin, backward-compatible wrapper around the shared
app.services.security.loop_guard.LoopGuard so both agent modes
(docs_qa's ReAct loop and rag_graph's retrieval_agent) share one
definition of "repeated call" and "stalled loop" instead of two that
could silently drift apart.

Kept as its own module (rather than deleting it) so existing imports
(`from app.services.agents.docs_qa.loop_guard import LoopGuard`) keep
working unchanged, with the docs_qa-specific tool/args vocabulary.
"""

from typing import Any, Dict, Optional

from app.services.security.loop_guard import LoopGuard as _SharedLoopGuard
from app.services.security.loop_guard import make_signature as make_call_signature

__all__ = ["LoopGuard", "make_call_signature"]


class LoopGuard(_SharedLoopGuard):
    """docs_qa-flavored facade: (tool_name, args) instead of (operation, params)."""

    def register_and_check(self, tool_name: str, args: Dict[str, Any]) -> Optional[str]:
        return super().register_and_check(tool_name, args)

    def note_tool_only_lap(self) -> None:
        self.note_no_progress_lap()
