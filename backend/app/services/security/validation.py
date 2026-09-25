"""Shared pre-execution validation result shape.

Used by any guard that needs to say "should this LLM-produced input be
allowed to proceed, and if it does proceed, should it be trusted as
grounded" -- without every agent module inventing its own version of
the same three fields.
"""


class ValidationResult:
    """
    ok:        False => intercept, do NOT execute/use this input as-is.
               Caller should surface `corrective_message` instead.
    grounded:  False => execution may proceed, but the input didn't
               confidently match anything in a known catalog/plan, so the
               result should be flagged as unverified rather than stated
               as confident fact.
    """

    def __init__(self, ok: bool, reason: str = "", corrective_message: str = ""):
        self.ok = ok
        self.reason = reason
        self.corrective_message = corrective_message
        self.grounded = True
