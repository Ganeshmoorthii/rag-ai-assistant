"""Developer Documentation Tools for Week 7 Agent Loop and Fixed Workflow.

Provides three specialized, non-overlapping tools:
1. search_docs: Searches prose documentation and PDF guides for conceptual information.
2. get_openapi_spec: Queries OpenAPI 3.0 specification for exact HTTP endpoint schemas.
3. check_deprecation: Verifies deprecation status of SDK symbols/endpoints against API versions.
"""

import json
import os
import re
from enum import Enum
from typing import Any, Dict, Optional

from app.core.flow_log import flow_log


class ApiVersion(str, Enum):
    V1 = "v1"
    V2 = "v2"
    V3 = "v3"


HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
SPEC_PATH = os.path.join(BACKEND_DIR, "eval", "datasets", "openapi_spec.json")

# Deprecation and migration catalog by target version
DEPRECATIONS_CATALOG: Dict[str, Dict[str, Dict[str, str]]] = {
    "v3": {
        "requireApiKey": {
            "status": "DEPRECATED",
            "deprecated_in": "v3.0.0",
            "replacement": "Bearer JWT token middleware with verifyToken and requireAuthentication.",
            "details": "API keys bypass permissions in v2; in v3, all caller authentication requires JWT Bearer tokens.",
        },
        "legacyKey": {
            "status": "DEPRECATED",
            "deprecated_in": "v3.0.0",
            "replacement": "tenantId + tokenProvider options.",
            "details": "Static legacy keys are disabled. Multi-tenant token exchange is mandatory in v3.",
        },
        "AuthClient": {
            "status": "SIGNATURE_CHANGED",
            "deprecated_in": "v3.0.0",
            "replacement": "new AuthClient({ tokenProvider, tenantId })",
            "details": "Initializing AuthClient with apiKey is removed in v3. Use tokenProvider and tenantId.",
        },
        "getBackorders": {
            "status": "SIGNATURE_CHANGED",
            "deprecated_in": "v3.0.0",
            "replacement": "getBackorders({ agencyId, includeDrafts })",
            "details": "Positional parameter getBackorders(agencyId) is deprecated in v3. It now takes a config options object.",
        },
        "restockItem": {
            "status": "DEPRECATED",
            "deprecated_in": "v3.0.0",
            "replacement": "POST /api/inventory/reconcile with { itemNumber, agencyCode, quantity }",
            "details": "3-argument positional restockItem(itemId, qty, legacyFlag) was removed; replaced by reconciliation API.",
        },
        "/api/v2/orders": {
            "status": "DEPRECATED",
            "deprecated_in": "v3.0.0",
            "replacement": "POST /orders/verification and PUT /api/orders/{id}/po",
            "details": "The monolithic /api/v2/orders endpoint is sunset in v3. Use dedicated workflow endpoints.",
        },
        "validateApikey": {
            "status": "DEPRECATED",
            "deprecated_in": "v3.0.0",
            "replacement": "verifyToken middleware",
            "details": "Replaced by Redis-cached JWKS verification via verifyToken middleware.",
        },
    },
    "v2": {
        "basicAuth": {
            "status": "DEPRECATED",
            "deprecated_in": "v2.0.0",
            "replacement": "API Key header (x-api-key)",
            "details": "HTTP Basic Authentication was removed in v2 in favor of API keys.",
        }
    },
    "v1": {},
}


def _load_openapi_spec() -> dict:
    if os.path.exists(SPEC_PATH):
        try:
            with open(SPEC_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"paths": {}}


async def search_docs(query: str, top_k: int = 3) -> str:
    """Searches developer documentation guides, PDFs, and conceptual manuals for technical explanations and usage examples. Use this ONLY to search prose guides and documentation articles."""
    try:
        from app.services.retrieval import retriever
        retriever.ensure_bm25_index()
        res = await retriever.retrieve(question=query, top_k=top_k, rewrite=False, rerank=False)
        chunks = res.get("chunks", [])
        if not chunks:
            return f"No documentation articles found matching query: '{query}'."

        formatted_chunks = []
        for i, c in enumerate(chunks[:2], 1):
            doc_ref = f"[{c.get('filename', 'doc')} p.{c.get('page', '?')}]"
            text_snippet = c.get("text", "").strip()[:280]
            formatted_chunks.append(f"Result {i} {doc_ref}:\n{text_snippet}")

        flow_log("tools.search_docs", query=query, chunk_count=len(chunks))
        return "\n\n---\n\n".join(formatted_chunks)
    except Exception as e:
        flow_log("tools.search_docs.error", query=query, error=str(e))
        return f"Error searching documentation: {str(e)}"


def _format_endpoint_spec(path_str: str, defn: dict) -> str:
    lines = [f"Endpoint: {path_str}"]
    for method, m_info in defn.items():
        lines.append(f"  Method: {method.upper()}")
        if "summary" in m_info:
            lines.append(f"  Summary: {m_info.get('summary')}")
        if "parameters" in m_info:
            params = [
                f"{param.get('name')} ({param.get('in')}, required={param.get('required', False)})"
                for param in m_info["parameters"]
            ]
            lines.append(f"  Parameters: {', '.join(params)}")
        if "requestBody" in m_info:
            schema = m_info["requestBody"].get("content", {}).get("application/json", {}).get("schema", {})
            req_props = schema.get("required", [])
            props = list(schema.get("properties", {}).keys())
            lines.append(f"  Request Body: properties={props}, required={req_props}")
        if "responses" in m_info:
            resps = [f"{code}: {r.get('description')}" for code, r in m_info["responses"].items()]
            lines.append(f"  Responses: {', '.join(resps)}")
    return "\n".join(lines)


def get_openapi_spec(endpoint_path: str) -> str:
    """Retrieves the exact HTTP specification for an endpoint path from the OpenAPI 3.0 schema (including HTTP method, parameters, request body JSON format, and status codes). Use this ONLY for HTTP endpoint schema inspection."""
    spec = _load_openapi_spec()
    paths = spec.get("paths", {})

    cleaned_query = endpoint_path.strip().rstrip("/")
    if not cleaned_query.startswith("/"):
        cleaned_query = "/" + cleaned_query

    # Exact match
    if cleaned_query in paths:
        flow_log("tools.get_openapi_spec", endpoint=cleaned_query, found=True)
        return _format_endpoint_spec(cleaned_query, paths[cleaned_query])

    # Parametrized or partial match (e.g. /api/orders/123/po vs /api/orders/{id}/po)
    matches = []
    for p, defn in paths.items():
        pattern = "^" + re.sub(r"\{[a-zA-Z0-9_]+\}", r"[^/]+", p) + "$"
        if re.match(pattern, cleaned_query) or cleaned_query in p or p in cleaned_query:
            matches.append(_format_endpoint_spec(p, defn))

    flow_log("tools.get_openapi_spec", endpoint=cleaned_query, matches=len(matches))
    if matches:
        return "\n\n".join(matches)

    available = list(paths.keys())
    return (
        f"Endpoint '{endpoint_path}' not found in OpenAPI specification. "
        f"Available endpoints in spec: {', '.join(available)}"
    )


def check_deprecation(symbol_or_endpoint: str, api_version: ApiVersion) -> str:
    """Checks whether a specific SDK symbol, method name, or HTTP endpoint is deprecated in the specified API version, returning the deprecation notice, replacement symbol/path, and migration details. Use this ONLY for deprecation and version compatibility verification."""
    ver_str = api_version.value if isinstance(api_version, ApiVersion) else str(api_version).lower()
    cat = DEPRECATIONS_CATALOG.get(ver_str, {})

    target = symbol_or_endpoint.strip()
    # Normalize clean key
    found_key = None
    for k in cat.keys():
        if k.lower() == target.lower() or k.lower() in target.lower() or target.lower() in k.lower():
            found_key = k
            break

    flow_log("tools.check_deprecation", target=target, version=ver_str, found=bool(found_key))
    if found_key:
        info = cat[found_key]
        return (
            f"Deprecation Record [{ver_str}]:\n"
            f"- Symbol/Endpoint: {found_key}\n"
            f"- Status: {info['status']}\n"
            f"- Deprecated In: {info.get('deprecated_in', ver_str)}\n"
            f"- Replacement: {info['replacement']}\n"
            f"- Details: {info['details']}"
        )

    return (
        f"Deprecation check for '{symbol_or_endpoint}' in {ver_str}: "
        f"No deprecation or sunset record found. Symbol is considered active in {ver_str}."
    )


# Standard OpenAI / OpenRouter function calling schemas
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "Searches developer documentation guides, PDFs, and conceptual manuals for technical explanations and usage examples. Use this ONLY to search prose guides and documentation articles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The technical documentation search query, e.g. 'order types and components' or 'stickersheet AI verification'",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_openapi_spec",
            "description": "Retrieves the exact HTTP specification for an endpoint path from the OpenAPI 3.0 schema (including HTTP method, parameters, request body JSON format, and status codes). Use this ONLY for HTTP endpoint schema inspection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "endpoint_path": {
                        "type": "string",
                        "description": "The HTTP path of the endpoint, e.g. /api/v1/impersonate or /ebi/backorders",
                    }
                },
                "required": ["endpoint_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_deprecation",
            "description": "Checks whether a specific SDK symbol, method name, or HTTP endpoint is deprecated in the specified API version, returning the deprecation notice, replacement symbol/path, and migration details. Use this ONLY for deprecation and version compatibility verification.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol_or_endpoint": {
                        "type": "string",
                        "description": "The SDK function, class name, or HTTP endpoint to check (e.g. 'getBackorders', 'requireApiKey', '/api/v2/orders')",
                    },
                    "api_version": {
                        "type": "string",
                        "enum": ["v1", "v2", "v3"],
                        "description": "The target API/SDK version to evaluate deprecation against",
                    },
                },
                "required": ["symbol_or_endpoint", "api_version"],
            },
        },
    },
]


async def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Dispatches a tool call by name with argument validation."""
    if tool_name == "search_docs":
        query = arguments.get("query", "")
        return await search_docs(query=query)
    elif tool_name == "get_openapi_spec":
        endpoint = arguments.get("endpoint_path", "")
        return get_openapi_spec(endpoint_path=endpoint)
    elif tool_name == "check_deprecation":
        target = arguments.get("symbol_or_endpoint", "")
        ver_val = arguments.get("api_version", "v3")
        try:
            ver_enum = ApiVersion(ver_val.lower())
        except Exception:
            ver_enum = ApiVersion.V3
        return check_deprecation(symbol_or_endpoint=target, api_version=ver_enum)
    else:
        return f"Unknown tool: '{tool_name}'. Available tools: search_docs, get_openapi_spec, check_deprecation."
