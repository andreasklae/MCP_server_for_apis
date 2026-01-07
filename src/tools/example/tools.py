"""Example provider tools - demonstrates the tool implementation pattern."""

from typing import Any

from src.mcp.models import TextContent
from src.mcp.registry import ToolRegistry
from src.tools.example.client import get_client


async def ping_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle the example-ping tool call."""
    client = get_client()
    result = await client.ping()
    return [TextContent(text=f"pong: {result['pong']}")]


async def echo_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle the example-echo tool call."""
    message = arguments.get("message", "")
    if not message:
        return [TextContent(text="Error: 'message' argument is required")]
    
    client = get_client()
    result = await client.echo(message)
    return [TextContent(text=f"Echo: {result['echo']}")]


def register_tools(registry: ToolRegistry) -> None:
    """Register all example provider tools with the registry."""
    
    # Tool: example-ping
    registry.register(
        name="example-ping",
        description="Returns a simple pong response. Use this to test if the MCP server is working.",
        input_schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
        handler=ping_handler,
    )
    
    # Tool: example-echo
    registry.register(
        name="example-echo",
        description="Echoes back the provided message. Use this to test tool argument passing.",
        input_schema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message to echo back",
                },
            },
            "required": ["message"],
        },
        handler=echo_handler,
    )

