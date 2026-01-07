"""Tool registry for managing MCP tools."""

import importlib
import logging
from typing import Any, Callable, Awaitable
from pathlib import Path

from src.mcp.models import Tool, TextContent, ToolCallResult

logger = logging.getLogger(__name__)

# Type alias for tool handlers
ToolHandler = Callable[[dict[str, Any]], Awaitable[list[TextContent]]]


class ToolDefinition:
    """A registered tool with its metadata and handler."""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: ToolHandler,
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.handler = handler

    def to_mcp_tool(self) -> Tool:
        """Convert to MCP Tool model for protocol responses."""
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.input_schema,
        )


class ToolRegistry:
    """Registry for MCP tools with plugin-style provider loading."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._providers: set[str] = set()

    def register(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: ToolHandler,
    ) -> None:
        """Register a tool with the registry."""
        if name in self._tools:
            logger.warning(f"Tool '{name}' already registered, overwriting")
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
        )
        logger.info(f"Registered tool: {name}")

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """List all registered tools as MCP Tool models."""
        return [tool.to_mcp_tool() for tool in self._tools.values()]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolCallResult:
        """Call a tool by name with the given arguments."""
        tool = self.get(name)
        if tool is None:
            return ToolCallResult(
                content=[TextContent(text=f"Tool not found: {name}")],
                isError=True,
            )

        try:
            content = await tool.handler(arguments)
            return ToolCallResult(content=content, isError=False)
        except Exception as e:
            logger.exception(f"Error executing tool {name}")
            return ToolCallResult(
                content=[TextContent(text=f"Tool execution error: {str(e)}")],
                isError=True,
            )

    def load_provider(self, provider_name: str) -> bool:
        """
        Load a provider module and register its tools.
        
        Providers are expected to be in src/tools/<provider_name>/
        and have a register_tools(registry) function.
        """
        if provider_name in self._providers:
            logger.debug(f"Provider '{provider_name}' already loaded")
            return True

        module_path = f"src.tools.{provider_name}.tools"
        try:
            module = importlib.import_module(module_path)
            if hasattr(module, "register_tools"):
                module.register_tools(self)
                self._providers.add(provider_name)
                logger.info(f"Loaded provider: {provider_name}")
                return True
            else:
                logger.warning(
                    f"Provider '{provider_name}' has no register_tools function"
                )
                return False
        except ImportError as e:
            logger.warning(f"Could not import provider '{provider_name}': {e}")
            return False
        except Exception as e:
            logger.error(f"Error loading provider '{provider_name}': {e}")
            return False

    def load_providers(self, provider_names: list[str]) -> dict[str, bool]:
        """Load multiple providers, returning success status for each."""
        results = {}
        for name in provider_names:
            results[name] = self.load_provider(name)
        return results

    @property
    def tool_count(self) -> int:
        """Return the number of registered tools."""
        return len(self._tools)

    @property
    def provider_count(self) -> int:
        """Return the number of loaded providers."""
        return len(self._providers)


# Global registry instance
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry, creating it if necessary."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the global registry (useful for testing)."""
    global _registry
    _registry = None

