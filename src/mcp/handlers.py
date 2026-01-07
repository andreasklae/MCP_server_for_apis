"""MCP method handlers for JSON-RPC requests."""

import logging
from typing import Any

from src.mcp.models import (
    InitializeParams,
    InitializeResult,
    ServerInfo,
    Capabilities,
    ToolsListResult,
    ToolCallParams,
    ToolCallResult,
    TextContent,
)
from src.mcp.registry import ToolRegistry
from src.mcp.errors import METHOD_NOT_FOUND, INVALID_PARAMS, make_error_data
from src.config.loader import get_settings

logger = logging.getLogger(__name__)

# MCP protocol version we support
PROTOCOL_VERSION = "2024-11-05"


class MCPHandlers:
    """Handlers for MCP protocol methods."""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self._initialized = False

    async def handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle the initialize request."""
        try:
            init_params = InitializeParams(**params)
        except Exception as e:
            logger.warning(f"Invalid initialize params: {e}")
            # Still proceed with defaults
            init_params = None

        settings = get_settings()
        self._initialized = True

        result = InitializeResult(
            protocolVersion=PROTOCOL_VERSION,
            capabilities=Capabilities(tools={}),
            serverInfo=ServerInfo(
                name=settings.server_name,
                version=settings.server_version,
            ),
        )
        return result.model_dump()

    async def handle_initialized(self, params: dict[str, Any]) -> None:
        """Handle the notifications/initialized notification (no response)."""
        logger.info("Client confirmed initialization")
        return None

    async def handle_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle the tools/list request."""
        tools = self.registry.list_tools()
        result = ToolsListResult(tools=tools)
        return result.model_dump()

    async def handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle the tools/call request."""
        try:
            call_params = ToolCallParams(**params)
        except Exception as e:
            logger.warning(f"Invalid tools/call params: {e}")
            return ToolCallResult(
                content=[TextContent(text=f"Invalid parameters: {e}")],
                isError=True,
            ).model_dump()

        logger.info(f"Calling tool: {call_params.name}")
        result = await self.registry.call_tool(
            call_params.name, call_params.arguments
        )
        return result.model_dump()

    async def dispatch(
        self, method: str, params: dict[str, Any]
    ) -> tuple[Any | None, dict[str, Any] | None]:
        """
        Dispatch a method call to the appropriate handler.
        
        Returns (result, error) tuple. One will be None.
        """
        handlers = {
            "initialize": self.handle_initialize,
            "notifications/initialized": self.handle_initialized,
            "tools/list": self.handle_tools_list,
            "tools/call": self.handle_tools_call,
        }

        handler = handlers.get(method)
        if handler is None:
            return None, make_error_data(
                METHOD_NOT_FOUND, f"Method not found: {method}"
            )

        try:
            result = await handler(params)
            return result, None
        except Exception as e:
            logger.exception(f"Error handling method {method}")
            return None, make_error_data(
                INVALID_PARAMS, f"Error processing request: {str(e)}"
            )

