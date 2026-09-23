"""Pre-execution validation for docs_qa agent tool calls.

Catches two of the four target failure modes cheaply, WITHOUT an extra
LLM call, before a tool is ever executed:

  - "wrong tool"     -- the argument shape doesn't match what the chosen
                        tool expects (e.g. a prose question passed to
                        get_openapi_spec, which wants a URL path).
  - "made-up inputs" -- the argument names a symbol/endpoint that does
                        not fuzzy-match anything in our known catalogs,
                        i.e. the model likely hallucinated it.

Validation failures are not hard blocks -- the tool still may be the
right one and the input may be a legitimate one we just don't have
cataloged. Instead we attach warnings that the caller can (a) feed back
to the model as a corrective nudge for tool-shape mismatches, or (b) tag
onto the tool's result so the final answer is forced to hedge instead of
stating a fabricated fact confidently.
"""

import difflib
import os
from typing import Any, Dict, List

from app.services.agents.docs_qa.doc_tools import DEPRECATIONS_CATALOG, _load_openapi_spec

_ENDPOINT_SHAPE_HINTS = ("/",)


def _looks_like_endpoint(value: str) -> bool:
    return isinstance(value, str) and "/" in value.strip()


def _known_endpoints() -> List[str]:
    return list(_load_openapi_spec().get("paths", {}).keys())


def _known_symbols() -> List[str]:
    symbols: List[str] = []
    for version_cat in DEPRECATIONS_CATALOG.values():
        symbols.extend(version_cat.keys())
    return symbols


class ValidationResult:
    def __init__(self, ok: bool, reason: str = "", corrective_message: str = ""):
        self.ok = ok
        self.reason = reason
        self.corrective_message = corrective_message
        self.grounded = True  # False => argument is likely hallucinated


def validate_tool_call(tool_name: str, args: Dict[str, Any]) -> ValidationResult:
    """Run cheap, non-LLM checks before a tool is executed.

    Returns ValidationResult.ok=False only for clear shape mismatches
    (wrong tool for the argument given) -- those should be intercepted
    and NOT executed. For "made-up input" cases we still let execution
    proceed (the tool's own "not found" handling is fine) but mark
    `grounded=False` so the caller can flag the result as unverified.
    """
    if tool_name == "get_openapi_spec":
        endpoint = str(args.get("endpoint_path") or "").strip()
        if not _looks_like_endpoint(endpoint):
            return ValidationResult(
                ok=False,
                reason="argument does not look like an HTTP path",
                corrective_message=(
                    f"[TOOL VALIDATOR] '{endpoint}' does not look like an HTTP "
                    "endpoint path (expected something like /api/v2/orders). "
                    "If you're looking for a concept or explanation, call "
                    "search_docs instead. If you meant a specific endpoint, "
                    "retry with the correct path."
                ),
            )
        known = _known_endpoints()
        close = difflib.get_close_matches(endpoint, known, n=1, cutoff=0.6)
        result = ValidationResult(ok=True)
        result.grounded = bool(close) or endpoint in known
        return result

    if tool_name == "check_deprecation":
        target = str(args.get("symbol_or_endpoint") or "").strip()
        api_version = str(args.get("api_version") or "").strip().lower()
        if api_version not in ("v1", "v2", "v3"):
            return ValidationResult(
                ok=False,
                reason="invalid api_version",
                corrective_message=(
                    f"[TOOL VALIDATOR] '{args.get('api_version')}' is not a valid "
                    "api_version. It must be exactly one of: v1, v2, v3. Retry "
                    "with a valid version -- do not guess or default silently."
                ),
            )
        known = _known_symbols()
        close = difflib.get_close_matches(target, known, n=1, cutoff=0.6)
        result = ValidationResult(ok=True)
        result.grounded = bool(close) or any(
            target.lower() in k.lower() or k.lower() in target.lower() for k in known
        )
        return result

    if tool_name == "search_docs":
        query = str(args.get("query") or "").strip()
        if not query:
            return ValidationResult(
                ok=False,
                reason="empty query",
                corrective_message=(
                    "[TOOL VALIDATOR] search_docs was called with an empty "
                    "query. Provide specific keywords describing what you're "
                    "looking for."
                ),
            )
        return ValidationResult(ok=True)

    # Unknown tool name -- let execute_tool()'s own fallback handle it.
    return ValidationResult(ok=True)
