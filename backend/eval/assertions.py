"""Deterministic assertions for Developer Documentation RAG Evaluation.

Moved out of LLM judge to eliminate model variance and cost on programmatic rules:
1. code_sample_parses: Code blocks in answers parse without syntax errors.
2. endpoint_path_exists_in_spec: All mentioned HTTP endpoint paths exist in OpenAPI spec.
3. api_version_stated: Answers to versioned questions explicitly state the API version.
4. no_deprecated_symbol_without_migration_note: Deprecated symbols must have a migration note.

Total Deterministic Assertions: 4
Total Judged Criteria: 1 (Helpfulness & Semantic Correctness)
"""

import ast
import json
import os
import re
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_PATH = os.path.join(HERE, "openapi_spec.json")

# Default deprecations catalog for Cimplicity / Advita
DEPRECATED_SYMBOLS = {
    "requireApiKey": "Deprecated in v3; use Bearer token middleware or tokenProvider.",
    "legacyKey": "Deprecated in v3; replaced by tenantId + tokenProvider.",
    "AuthClient({ apiKey": "API key initialization deprecated in v3; use tokenProvider.",
    "getBackorders(agencyId)": "Positional parameter deprecated in v3; pass object with includeDrafts.",
}


def load_openapi_spec(spec_path: str = SPEC_PATH) -> dict:
    if os.path.exists(spec_path):
        with open(spec_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"paths": {}}


def _path_matches(pattern: str, actual: str) -> bool:
    """Matches parameterized OpenAPI paths like /api/orders/{id}/po against /api/orders/123/po."""
    regex = "^" + re.sub(r"\{[a-zA-Z0-9_]+\}", r"[a-zA-Z0-9_\\-]+", pattern) + "$"
    return bool(re.match(regex, actual.rstrip("/")))


def check_code_sample_parses(answer: str) -> tuple[bool, str]:
    """Assertion 1: Checks if code blocks in answer parse syntactically."""
    # Extract fenced code blocks
    code_blocks = re.findall(r"```([a-zA-Z0-9_-]*)\s*\n([\s\S]*?)```", answer)
    if not code_blocks:
        # Check for inline backtick code snippets that look like code statements
        inline_snippets = re.findall(r"`([^`\n]+)`", answer)
        for snippet in inline_snippets:
            snippet = snippet.strip()
            # Simple bracket balancing check for inline code
            for open_b, close_b in [("(", ")"), ("{", "}"), ("[", "]")]:
                if snippet.count(open_b) != snippet.count(close_b):
                    return False, f"Unbalanced brackets in code snippet: `{snippet}`"
        return True, "No multiline code blocks; inline snippets syntax check passed."

    for lang, code in code_blocks:
        lang = lang.lower().strip()
        code_str = code.strip()
        if not code_str:
            continue

        if lang in ("py", "python"):
            try:
                ast.parse(code_str)
            except SyntaxError as e:
                return False, f"Python syntax error in code block: {e}"
        elif lang in ("json",):
            try:
                json.loads(code_str)
            except Exception as e:
                return False, f"JSON parse error in code block: {e}"
        else:
            # JavaScript / TypeScript / Generic syntax check (bracket balance and quote pairing)
            stack = []
            matching = {")": "(", "}": "{", "]": "["}
            in_quote = None
            for ch in code_str:
                if ch in ("'", '"', "`") and not in_quote:
                    in_quote = ch
                elif ch == in_quote:
                    in_quote = None
                elif not in_quote:
                    if ch in matching.values():
                        stack.append(ch)
                    elif ch in matching:
                        if not stack or stack[-1] != matching[ch]:
                            return False, f"Mismatched bracket '{ch}' in {lang or 'code'} block"
                        stack.pop()
            if stack:
                return False, f"Unclosed bracket '{stack[-1]}' in {lang or 'code'} block"

    return True, "All code samples parsed successfully."


def check_endpoint_path_exists_in_spec(answer: str, openapi_spec: dict | None = None) -> tuple[bool, str]:
    """Assertion 2: Checks if all mentioned endpoint paths exist in OpenAPI spec."""
    if openapi_spec is None:
        openapi_spec = load_openapi_spec()
    spec_paths = list(openapi_spec.get("paths", {}).keys())

    # Find paths like /api/... or /orders/... or /ebi/...
    candidates = set(re.findall(r"(/(?:api|orders|ebi|health)[a-zA-Z0-9_\-\{\}\./]*)", answer))
    # Clean trailing punctuation
    cleaned_candidates = set()
    for c in candidates:
        c_clean = c.rstrip(".,;:)'\"`]")
        if len(c_clean) > 1 and not c_clean.endswith("/"):
            cleaned_candidates.add(c_clean)

    for path in cleaned_candidates:
        matched = False
        for spec_p in spec_paths:
            if _path_matches(spec_p, path) or path == spec_p:
                matched = True
                break
        if not matched:
            return False, f"Endpoint '{path}' does not exist in OpenAPI specification."

    return True, f"All {len(cleaned_candidates)} detected endpoints verified in OpenAPI spec."


def check_api_version_stated(answer: str, question: str, required_version: str | None = None) -> tuple[bool, str]:
    """Assertion 3: Answers to version-specific queries must explicitly state the API/SDK version."""
    target_version = required_version
    if not target_version:
        # Detect if question asks about a specific version
        v_match = re.search(r"\b(v[1-9]|SDK\s*v[1-9]|v[1-9]\.[0-9]+)\b", question, re.IGNORECASE)
        if v_match:
            target_version = v_match.group(1).lower()

    if target_version:
        # Check if the target version token is explicitly mentioned in the answer
        norm_v = target_version.replace("sdk", "").strip()
        ans_lower = answer.lower()
        if norm_v not in ans_lower:
            return False, f"Question targets '{target_version}' but answer does not state '{norm_v}'."

    return True, f"API version check passed (target: {target_version or 'general'})."


def check_no_deprecated_symbols(answer: str, deprecated_dict: dict[str, str] | None = None) -> tuple[bool, str]:
    """Assertion 4: Deprecated symbols must not appear without an explicit migration note."""
    if deprecated_dict is None:
        deprecated_dict = DEPRECATED_SYMBOLS

    ans_lower = answer.lower()
    for symbol, note in deprecated_dict.items():
        if symbol.lower() in ans_lower:
            # Check for migration markers
            migration_markers = ["deprecat", "migrat", "legacy", "in v3", "in sdk v3", "removed in", "replaced by"]
            has_marker = any(marker in ans_lower for marker in migration_markers)
            if not has_marker:
                return False, f"Deprecated symbol '{symbol}' used without migration note. ({note})"

    return True, "No unannotated deprecated symbols found."


def run_all_assertions(case: dict, openapi_spec: dict | None = None) -> dict[str, Any]:
    """Runs all 4 deterministic assertions on an evaluation case."""
    ans = case.get("answer", "")
    q = case.get("question", "")
    req_ver = case.get("required_version")

    p_code, r_code = check_code_sample_parses(ans)
    p_spec, r_spec = check_endpoint_path_exists_in_spec(ans, openapi_spec)
    p_ver, r_ver = check_api_version_stated(ans, q, req_ver)
    p_dep, r_dep = check_no_deprecated_symbols(ans)

    all_passed = p_code and p_spec and p_ver and p_dep

    return {
        "passed": all_passed,
        "details": {
            "code_sample_parses": {"passed": p_code, "reason": r_code},
            "endpoint_path_exists_in_spec": {"passed": p_spec, "reason": r_spec},
            "api_version_stated": {"passed": p_ver, "reason": r_ver},
            "no_deprecated_symbol_without_migration_note": {"passed": p_dep, "reason": r_dep},
        },
    }
