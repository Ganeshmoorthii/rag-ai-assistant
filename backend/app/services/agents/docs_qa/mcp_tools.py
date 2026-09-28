"""OpenAPI adapter for calling the MCP service as LLM function tools."""

import json
import re
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.core.flow_log import flow_log
from app.services.security.injection_guard import wrap_untrusted

_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
_EXCLUDED_TAGS = {"resources", "prompts"}


def _resolve_schema(schema: dict[str, Any], components: dict[str, Any], seen: set[str] | None = None) -> dict[str, Any]:
    seen = seen or set()
    reference = schema.get("$ref")
    if reference:
        name = reference.rsplit("/", 1)[-1]
        if name in seen:
            return {"type": "object"}
        return _resolve_schema(components.get(name, {}), components, seen | {name})

    result = {
        key: value
        for key, value in schema.items()
        if key in {"type", "description", "enum", "default", "format", "required", "additionalProperties"}
    }
    if "properties" in schema:
        result["properties"] = {
            name: _resolve_schema(value, components, seen)
            for name, value in schema["properties"].items()
        }
    if "items" in schema:
        result["items"] = _resolve_schema(schema["items"], components, seen)
    if "anyOf" in schema:
        choices = [choice for choice in schema["anyOf"] if choice.get("type") != "null"]
        if len(choices) == 1:
            result.update(_resolve_schema(choices[0], components, seen))
        else:
            result["anyOf"] = [_resolve_schema(choice, components, seen) for choice in choices]
    return result


def build_mcp_tools(openapi: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Build LLM function schemas and request metadata from MCP OpenAPI."""
    tools = []
    operations = {}
    components = openapi.get("components", {}).get("schemas", {})

    for path, path_item in openapi.get("paths", {}).items():
        if not path.startswith("/mcp/"):
            continue
        for method, operation in path_item.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            tags = set(operation.get("tags", []))
            if not tags or tags & _EXCLUDED_TAGS:
                continue

            operation_id = operation.get("operationId") or f"{method}_{path}"
            name = re.sub(r"[^a-zA-Z0-9_-]", "_", f"mcp_{operation_id}")[:64]
            parameters = path_item.get("parameters", []) + operation.get("parameters", [])
            properties: dict[str, Any] = {}
            required = []
            for parameter in parameters:
                parameter_name = parameter["name"]
                properties[parameter_name] = _resolve_schema(parameter.get("schema", {}), components)
                if parameter.get("description"):
                    properties[parameter_name]["description"] = parameter["description"]
                if parameter.get("required"):
                    required.append(parameter_name)

            request_body = operation.get("requestBody", {})
            body_schema = request_body.get("content", {}).get("application/json", {}).get("schema")
            if body_schema:
                properties["body"] = _resolve_schema(body_schema, components)
                properties["body"].setdefault("description", "JSON request body")
                if request_body.get("required"):
                    required.append("body")

            description = operation.get("summary") or operation.get("description") or operation_id
            description += f" ({method.upper()} {path})."
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description[:1024],
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                        },
                    },
                }
            )
            operations[name] = {
                "method": method.upper(),
                "path": path,
                "parameters": parameters,
                "has_body": bool(body_schema),
            }

    return tools, operations


async def load_mcp_tools() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Load the available MCP tools; return empty collections if MCP is offline."""
    if not settings.mcp_server_url:
        return [], {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.mcp_server_url.rstrip('/')}/openapi.json")
            response.raise_for_status()
        return build_mcp_tools(response.json())
    except (httpx.HTTPError, ValueError) as error:
        flow_log("agent.mcp_tools.unavailable", server_url=settings.mcp_server_url, error=str(error))
        return [], {}


async def execute_mcp_tool(
    name: str,
    arguments: dict[str, Any],
    operations: dict[str, dict[str, Any]],
) -> str:
    """Proxy one selected tool call to its MCP route and mark its data untrusted."""
    operation = operations.get(name)
    if not operation:
        return f"Unknown MCP tool: {name}."

    path = operation["path"]
    query = {}
    for parameter in operation["parameters"]:
        parameter_name = parameter["name"]
        if parameter_name not in arguments:
            continue
        if parameter.get("in") == "path":
            path = path.replace("{" + parameter_name + "}", quote(str(arguments[parameter_name]), safe=""))
        elif parameter.get("in") == "query":
            query[parameter_name] = arguments[parameter_name]

    request_body = {"json": arguments.get("body")} if operation["has_body"] else {}
    url = f"{settings.mcp_server_url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(operation["method"], url, params=query, **request_body)
            response.raise_for_status()
    except httpx.HTTPStatusError as error:
        return f"MCP tool failed with HTTP {error.response.status_code}: {error.response.text[:1000]}"
    except httpx.HTTPError as error:
        return f"MCP tool request failed: {error}"

    content = response.text or "Request completed successfully with no response body."
    try:
        content = json.dumps(response.json(), ensure_ascii=True)
    except ValueError:
        pass
    return wrap_untrusted(content, tag="tool_observation", source=name)