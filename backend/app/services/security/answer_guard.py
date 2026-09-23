"""Shared 'quiet give-up' detector used by both agent modes (docs_qa's
ReAct loop and the LangGraph response_agent). Kept separate from either
agent so both can flag the same failure pattern without duplicating or
drifting the definition of what counts as a low-effort answer.
"""

_LOW_EFFORT_MARKERS = (
    "i don't have enough information",
    "i do not have enough information",
    "unable to determine",
    "cannot determine",
    "no relevant results",
    "not enough context",
    "i don't know",
    "i cannot answer",
    "insufficient information",
)


def is_low_effort_answer(text: str) -> bool:
    """True if the answer reads like a hedge/refusal rather than a real
    attempt -- used together with evidence sufficiency (was there actually
    enough retrieved context to answer?) so a genuine gap isn't punished,
    only a give-up when the evidence was actually there."""
    lowered = (text or "").strip().lower()
    if not lowered:
        return True
    return any(marker in lowered for marker in _LOW_EFFORT_MARKERS)
