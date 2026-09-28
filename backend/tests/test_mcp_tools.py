import os
import asyncio
import sys
import unittest
from unittest.mock import patch

import httpx

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
MCP_DIR = os.path.abspath(os.path.join(BACKEND_DIR, "..", "mcp"))
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

from app.services.agents.docs_qa.mcp_tools import build_mcp_tools, execute_mcp_tool
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


if __name__ == "__main__":
    unittest.main()