"""Base tool class and decorator for tool registration."""

from abc import ABC, abstractmethod
from typing import Any, Callable, Awaitable
import functools

from src.mcp.models import TextContent


class BaseTool(ABC):
    """Base class for tool implementations."""
    
    name: str
    description: str
    input_schema: dict[str, Any]
    
    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Execute the tool with the given arguments."""
        pass


def tool(
    name: str,
    description: str,
    input_schema: dict[str, Any],
) -> Callable[
    [Callable[[dict[str, Any]], Awaitable[list[TextContent]]]],
    Callable[[dict[str, Any]], Awaitable[list[TextContent]]],
]:
    """
    Decorator to mark a function as an MCP tool.
    
    Usage:
        @tool(
            name="example-ping",
            description="Returns pong",
            input_schema={"type": "object", "properties": {}}
        )
        async def ping(arguments: dict) -> list[TextContent]:
            return [TextContent(text="pong")]
    
    The decorated function will have _tool_metadata attached.
    """
    def decorator(
        func: Callable[[dict[str, Any]], Awaitable[list[TextContent]]]
    ) -> Callable[[dict[str, Any]], Awaitable[list[TextContent]]]:
        @functools.wraps(func)
        async def wrapper(arguments: dict[str, Any]) -> list[TextContent]:
            return await func(arguments)
        
        # Attach metadata for registration
        wrapper._tool_metadata = {  # type: ignore
            "name": name,
            "description": description,
            "input_schema": input_schema,
        }
        return wrapper
    
    return decorator


def get_tool_metadata(
    func: Callable
) -> dict[str, Any] | None:
    """Get tool metadata from a decorated function."""
    return getattr(func, "_tool_metadata", None)

