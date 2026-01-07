"""Pydantic models for MCP JSON-RPC 2.0 protocol."""

from typing import Any, Literal
from pydantic import BaseModel, Field


# =============================================================================
# JSON-RPC 2.0 Base Models
# =============================================================================


class JsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 request object."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None  # None for notifications
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class JsonRpcError(BaseModel):
    """JSON-RPC 2.0 error object."""

    code: int
    message: str
    data: Any = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response object."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    result: Any = None
    error: JsonRpcError | None = None

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Custom serialization to exclude None fields appropriately."""
        data: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            data["error"] = self.error.model_dump()
        else:
            data["result"] = self.result
        return data


# =============================================================================
# MCP Content Types
# =============================================================================


class TextContent(BaseModel):
    """Text content returned by tools."""

    type: Literal["text"] = "text"
    text: str


class ImageContent(BaseModel):
    """Image content returned by tools (base64 encoded)."""

    type: Literal["image"] = "image"
    data: str  # base64 encoded
    mimeType: str


Content = TextContent | ImageContent


# =============================================================================
# MCP Tool Models
# =============================================================================


class Tool(BaseModel):
    """MCP tool definition."""

    name: str = Field(..., description="Tool name (lowercase with hyphens)")
    description: str = Field(..., description="Human-readable description")
    inputSchema: dict[str, Any] = Field(
        ..., description="JSON Schema for tool input"
    )


class ToolCallResult(BaseModel):
    """Result of a tool call."""

    content: list[TextContent | ImageContent]
    isError: bool = False


# =============================================================================
# MCP Protocol Models
# =============================================================================


class ClientInfo(BaseModel):
    """Client information sent during initialization."""

    name: str
    version: str


class ServerInfo(BaseModel):
    """Server information returned during initialization."""

    name: str
    version: str


class Capabilities(BaseModel):
    """Server capabilities."""

    tools: dict[str, Any] = Field(default_factory=dict)


class InitializeParams(BaseModel):
    """Parameters for initialize request."""

    protocolVersion: str
    capabilities: dict[str, Any] = Field(default_factory=dict)
    clientInfo: ClientInfo


class InitializeResult(BaseModel):
    """Result of initialize request."""

    protocolVersion: str
    capabilities: Capabilities
    serverInfo: ServerInfo


class ToolsListResult(BaseModel):
    """Result of tools/list request."""

    tools: list[Tool]


class ToolCallParams(BaseModel):
    """Parameters for tools/call request."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

