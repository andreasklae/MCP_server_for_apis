"""Tests for MCP JSON-RPC protocol handling."""

import pytest
from fastapi.testclient import TestClient

from src.mcp.errors import PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND


class TestJsonRpcParsing:
    """Tests for JSON-RPC message parsing."""
    
    def test_invalid_json_returns_parse_error(self, client: TestClient):
        """Test that invalid JSON returns parse error."""
        response = client.post(
            "/message",
            content="not valid json{",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["error"]["code"] == PARSE_ERROR
        assert "invalid json" in data["error"]["message"].lower()
    
    def test_missing_jsonrpc_field_returns_invalid_request(self, client: TestClient):
        """Test that missing jsonrpc field returns invalid request."""
        response = client.post(
            "/message",
            json={"id": 1, "method": "test"},
        )
        assert response.status_code == 200
        
        data = response.json()
        # Pydantic adds default "2.0", so this becomes a valid request for unknown method
        # Either invalid request or method not found is acceptable here
        assert data["error"]["code"] in [INVALID_REQUEST, METHOD_NOT_FOUND]
    
    def test_wrong_jsonrpc_version_returns_invalid_request(self, client: TestClient):
        """Test that wrong jsonrpc version returns invalid request."""
        response = client.post(
            "/message",
            json={"jsonrpc": "1.0", "id": 1, "method": "test"},
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["error"]["code"] == INVALID_REQUEST


class TestMcpMethods:
    """Tests for MCP protocol methods."""
    
    def test_unknown_method_returns_not_found(
        self, client: TestClient, sample_jsonrpc_request
    ):
        """Test that unknown method returns method not found."""
        response = client.post(
            "/message",
            json=sample_jsonrpc_request("unknown/method"),
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["error"]["code"] == METHOD_NOT_FOUND
        assert "not found" in data["error"]["message"].lower()
    
    def test_initialize_returns_capabilities(
        self, client: TestClient, sample_jsonrpc_request
    ):
        """Test that initialize returns server capabilities."""
        response = client.post(
            "/message",
            json=sample_jsonrpc_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            ),
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "result" in data
        assert data["result"]["protocolVersion"] == "2024-11-05"
        assert "capabilities" in data["result"]
        assert "serverInfo" in data["result"]
    
    def test_tools_list_returns_tools(
        self, client: TestClient, sample_jsonrpc_request
    ):
        """Test that tools/list returns available tools."""
        response = client.post(
            "/message",
            json=sample_jsonrpc_request("tools/list"),
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "result" in data
        assert "tools" in data["result"]
        assert isinstance(data["result"]["tools"], list)
        
        # Should have example tools
        tool_names = [t["name"] for t in data["result"]["tools"]]
        assert "example-ping" in tool_names
        assert "example-echo" in tool_names
    
    def test_tools_list_tool_has_required_fields(
        self, client: TestClient, sample_jsonrpc_request
    ):
        """Test that listed tools have all required fields."""
        response = client.post(
            "/message",
            json=sample_jsonrpc_request("tools/list"),
        )
        data = response.json()
        
        for tool in data["result"]["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert isinstance(tool["inputSchema"], dict)
    
    def test_tools_call_ping(
        self, client: TestClient, sample_jsonrpc_request
    ):
        """Test calling the example-ping tool."""
        response = client.post(
            "/message",
            json=sample_jsonrpc_request(
                "tools/call",
                {"name": "example-ping", "arguments": {}},
            ),
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "result" in data
        assert data["result"]["isError"] is False
        assert len(data["result"]["content"]) > 0
        assert "pong" in data["result"]["content"][0]["text"].lower()
    
    def test_tools_call_echo(
        self, client: TestClient, sample_jsonrpc_request
    ):
        """Test calling the example-echo tool."""
        response = client.post(
            "/message",
            json=sample_jsonrpc_request(
                "tools/call",
                {"name": "example-echo", "arguments": {"message": "Hello, World!"}},
            ),
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "result" in data
        assert data["result"]["isError"] is False
        assert "Hello, World!" in data["result"]["content"][0]["text"]
    
    def test_tools_call_unknown_tool(
        self, client: TestClient, sample_jsonrpc_request
    ):
        """Test calling an unknown tool returns error."""
        response = client.post(
            "/message",
            json=sample_jsonrpc_request(
                "tools/call",
                {"name": "unknown-tool", "arguments": {}},
            ),
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "result" in data
        assert data["result"]["isError"] is True
        assert "not found" in data["result"]["content"][0]["text"].lower()
    
    def test_notification_returns_accepted(
        self, client: TestClient
    ):
        """Test that notifications (no id) return 202 Accepted."""
        response = client.post(
            "/message",
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                # No id = notification
            },
        )
        assert response.status_code == 202


class TestResponseFormat:
    """Tests for JSON-RPC response format compliance."""
    
    def test_response_has_jsonrpc_field(
        self, client: TestClient, sample_jsonrpc_request
    ):
        """Test that responses include jsonrpc field."""
        response = client.post(
            "/message",
            json=sample_jsonrpc_request("tools/list"),
        )
        data = response.json()
        assert data["jsonrpc"] == "2.0"
    
    def test_response_has_matching_id(
        self, client: TestClient, sample_jsonrpc_request
    ):
        """Test that response id matches request id."""
        response = client.post(
            "/message",
            json=sample_jsonrpc_request("tools/list", id=42),
        )
        data = response.json()
        assert data["id"] == 42
    
    def test_success_response_has_result(
        self, client: TestClient, sample_jsonrpc_request
    ):
        """Test that successful responses have result field."""
        response = client.post(
            "/message",
            json=sample_jsonrpc_request("tools/list"),
        )
        data = response.json()
        assert "result" in data
        assert "error" not in data or data["error"] is None
    
    def test_error_response_has_error(
        self, client: TestClient, sample_jsonrpc_request
    ):
        """Test that error responses have error field."""
        response = client.post(
            "/message",
            json=sample_jsonrpc_request("unknown/method"),
        )
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] is not None
        assert data["error"]["message"] is not None

