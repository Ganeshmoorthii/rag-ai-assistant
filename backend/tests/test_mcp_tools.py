import os
import asyncio
import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
MCP_DIR = os.path.abspath(os.path.join(BACKEND_DIR, "..", "mcp"))
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

from app.services.agents.docs_qa.mcp_tools import build_mcp_tools, execute_mcp_tool
from app.services.agents.rag_graph import response_agent
from app.services.llm import llm_client
from src.server import app as mcp_app


class TestMcpToolSchemas(unittest.TestCase):
    def test_builds_database_tools_and_skips_resources(self):
        openapi = {
            "components": {
                "schemas": {
                    "AgencyCreate": {
                        "type": "object",
                        "required": ["agency_code"],
                        "properties": {"agency_code": {"type": "string"}},
                    }
                }
            },
            "paths": {
                "/mcp/agencies": {
                    "post": {
                        "operationId": "create_agency",
                        "tags": ["agencies"],
                        "requestBody": {
                            "required": True,
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AgencyCreate"}}},
                        },
                    }
                },
                "/mcp/resources/agencies/summary": {
                    "get": {"operationId": "agency_summary", "tags": ["resources"]}
                },
            },
        }

        tools, operations = build_mcp_tools(openapi)

        self.assertEqual(len(tools), 1)
        self.assertIn("mcp_create_agency", operations)
        schema = tools[0]["function"]["parameters"]
        self.assertEqual(schema["required"], ["body"])
        self.assertEqual(schema["properties"]["body"]["properties"]["agency_code"]["type"], "string")

    def test_discovers_registered_mcp_database_tools(self):
        tools, operations = build_mcp_tools(mcp_app.openapi())

        self.assertGreaterEqual(len(tools), 10)
        self.assertTrue(any("agencies" in name for name in operations))
        self.assertTrue(any("inventory" in name for name in operations))
        self.assertTrue(any("backorders" in name for name in operations))
        self.assertTrue(any("commissions" in name for name in operations))
        self.assertTrue(any("sdk_versions" in name for name in operations))

    def test_executes_selected_tool_with_path_and_query_arguments(self):
        observed = {}

        def handle_request(request):
            observed["path"] = request.url.path
            observed["query"] = dict(request.url.params)
            return httpx.Response(200, json={"agency_code": "AC-1"})

        client_type = httpx.AsyncClient
        operations = {
            "mcp_get_agency": {
                "method": "GET",
                "path": "/mcp/agencies/{agency_code}",
                "parameters": [
                    {"name": "agency_code", "in": "path"},
                    {"name": "active_only", "in": "query"},
                ],
                "has_body": False,
            }
        }

        def create_client(**kwargs):
            return client_type(transport=httpx.MockTransport(handle_request), **kwargs)

        with patch("app.services.agents.docs_qa.mcp_tools.httpx.AsyncClient", side_effect=create_client):
            result = asyncio.run(
                execute_mcp_tool(
                    "mcp_get_agency",
                    {"agency_code": "AC-1", "active_only": False},
                    operations,
                )
            )

        self.assertEqual(observed["path"], "/mcp/agencies/AC-1")
        self.assertEqual(observed["query"], {"active_only": "false"})
        self.assertIn("AC-1", result)


class TestLlmToolCalling(unittest.IsolatedAsyncioTestCase):
    async def test_dispatches_function_and_synthesizes_observation(self):
        requests = []
        executed = []

        def handle_request(request):
            payload = json.loads(request.content)
            requests.append(payload)
            if len(requests) == 1:
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "call-1",
                                            "type": "function",
                                            "function": {
                                                "name": "mcp_list_agencies",
                                                "arguments": "{}",
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": "Agency AC-1 is active."}}]},
            )

        async def execute_tool(name, arguments):
            executed.append((name, arguments))
            return '{"agency_code":"AC-1","active":true}'

        client_type = httpx.AsyncClient

        def create_client(**kwargs):
            return client_type(transport=httpx.MockTransport(handle_request), **kwargs)

        test_settings = SimpleNamespace(
            llm_api_key="test-key",
            llm_model="test-model",
            llm_url="https://llm.test/chat/completions",
            llm_provider="test provider",
        )
        with (
            patch("app.services.llm.llm_client.settings", test_settings),
            patch("app.services.llm.llm_client.httpx.AsyncClient", side_effect=create_client),
        ):
            answer = await llm_client.call_llm_text(
                system_prompt="Use MCP for current agency data.",
                user_prompt="Which agencies are active?",
                tools=[{"type": "function", "function": {"name": "mcp_list_agencies"}}],
                tool_executor=execute_tool,
            )

        self.assertEqual(answer, "Agency AC-1 is active.")
        self.assertEqual(executed, [("mcp_list_agencies", {})])
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["tool_choice"], "auto")
        self.assertTrue(any(message["role"] == "tool" for message in requests[1]["messages"]))

    async def test_graph_response_uses_mcp_without_retrieved_documents(self):
        tool_name = "mcp_list_agencies"
        schemas = [{"type": "function", "function": {"name": tool_name}}]
        operations = {tool_name: {"method": "GET", "path": "/mcp/agencies", "parameters": [], "has_body": False}}
        trace = {"stages": [], "timings_ms": {}}

        async def complete_with_tool(**kwargs):
            self.assertEqual(kwargs["tools"], schemas)
            observation = await kwargs["tool_executor"](tool_name, {})
            self.assertIn("AC-1", observation)
            return "Agency AC-1 is active."

        state = {
            "question": "Which agencies are active?",
            "documents": [],
            "intent": "factual_lookup",
            "evidence_sufficient": False,
            "sub_results": [],
            "trace": trace,
            "config": {},
        }
        with (
            patch.object(response_agent, "load_mcp_tools", new=AsyncMock(return_value=(schemas, operations))),
            patch.object(response_agent, "execute_mcp_tool", new=AsyncMock(return_value='{"agency_code":"AC-1"}')),
            patch.object(response_agent.llm_client, "call_llm_text", side_effect=complete_with_tool),
        ):
            result = await response_agent.response_agent_node(state)

        self.assertEqual(result["answer"], "Agency AC-1 is active.")
        response_stage = trace["stages"][0]
        self.assertEqual(response_stage["mcp_tools_called"], [tool_name])


if __name__ == "__main__":
    unittest.main()