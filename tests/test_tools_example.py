"""Tests for example provider tools."""

import pytest

from src.mcp.registry import ToolRegistry
from src.tools.example.tools import register_tools, ping_handler, echo_handler
from src.tools.example.client import ExampleClient, get_client


class TestExampleClient:
    """Tests for the example client."""
    
    @pytest.mark.asyncio
    async def test_ping_returns_pong(self):
        """Test that ping returns pong."""
        client = ExampleClient()
        result = await client.ping()
        assert result == {"pong": True}
    
    @pytest.mark.asyncio
    async def test_echo_returns_message(self):
        """Test that echo returns the message."""
        client = ExampleClient()
        result = await client.echo("Hello")
        assert result == {"echo": "Hello"}
    
    def test_get_client_returns_singleton(self):
        """Test that get_client returns the same instance."""
        client1 = get_client()
        client2 = get_client()
        assert client1 is client2


class TestExampleHandlers:
    """Tests for example tool handlers."""
    
    @pytest.mark.asyncio
    async def test_ping_handler(self):
        """Test ping handler returns text content."""
        result = await ping_handler({})
        assert len(result) == 1
        assert result[0].type == "text"
        assert "pong" in result[0].text.lower()
    
    @pytest.mark.asyncio
    async def test_echo_handler_with_message(self):
        """Test echo handler with valid message."""
        result = await echo_handler({"message": "Test message"})
        assert len(result) == 1
        assert result[0].type == "text"
        assert "Test message" in result[0].text
    
    @pytest.mark.asyncio
    async def test_echo_handler_without_message(self):
        """Test echo handler without message returns error."""
        result = await echo_handler({})
        assert len(result) == 1
        assert "error" in result[0].text.lower() or "required" in result[0].text.lower()


class TestToolRegistration:
    """Tests for tool registration."""
    
    def test_register_tools_adds_ping(self):
        """Test that register_tools adds ping tool."""
        registry = ToolRegistry()
        register_tools(registry)
        
        tool = registry.get("example-ping")
        assert tool is not None
        assert tool.name == "example-ping"
    
    def test_register_tools_adds_echo(self):
        """Test that register_tools adds echo tool."""
        registry = ToolRegistry()
        register_tools(registry)
        
        tool = registry.get("example-echo")
        assert tool is not None
        assert tool.name == "example-echo"
    
    def test_registered_tools_have_schemas(self):
        """Test that registered tools have input schemas."""
        registry = ToolRegistry()
        register_tools(registry)
        
        ping = registry.get("example-ping")
        assert ping.input_schema["type"] == "object"
        
        echo = registry.get("example-echo")
        assert "message" in echo.input_schema["properties"]


class TestToolRegistry:
    """Tests for the tool registry itself."""
    
    def test_register_and_get(self):
        """Test registering and retrieving a tool."""
        registry = ToolRegistry()
        
        async def dummy_handler(args):
            return []
        
        registry.register(
            name="test-tool",
            description="A test tool",
            input_schema={"type": "object"},
            handler=dummy_handler,
        )
        
        tool = registry.get("test-tool")
        assert tool is not None
        assert tool.name == "test-tool"
        assert tool.description == "A test tool"
    
    def test_list_tools(self):
        """Test listing all tools."""
        registry = ToolRegistry()
        register_tools(registry)
        
        tools = registry.list_tools()
        assert len(tools) == 2
        
        names = [t.name for t in tools]
        assert "example-ping" in names
        assert "example-echo" in names
    
    @pytest.mark.asyncio
    async def test_call_tool_success(self):
        """Test calling a tool successfully."""
        registry = ToolRegistry()
        register_tools(registry)
        
        result = await registry.call_tool("example-ping", {})
        assert result.isError is False
        assert len(result.content) > 0
    
    @pytest.mark.asyncio
    async def test_call_tool_not_found(self):
        """Test calling a nonexistent tool."""
        registry = ToolRegistry()
        
        result = await registry.call_tool("nonexistent", {})
        assert result.isError is True
        assert "not found" in result.content[0].text.lower()
    
    def test_tool_count(self):
        """Test tool count property."""
        registry = ToolRegistry()
        assert registry.tool_count == 0
        
        register_tools(registry)
        assert registry.tool_count == 2

