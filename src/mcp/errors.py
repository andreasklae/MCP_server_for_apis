"""JSON-RPC 2.0 error codes and error response helpers."""

from typing import Any

# Standard JSON-RPC 2.0 error codes
PARSE_ERROR = -32700  # Invalid JSON was received
INVALID_REQUEST = -32600  # The JSON sent is not a valid Request object
METHOD_NOT_FOUND = -32601  # The method does not exist / is not available
INVALID_PARAMS = -32602  # Invalid method parameter(s)
INTERNAL_ERROR = -32603  # Internal JSON-RPC error

# Custom error codes (server-defined, must be between -32000 and -32099)
TOOL_EXECUTION_ERROR = -32000  # Tool execution failed
AUTHENTICATION_ERROR = -32001  # Authentication required or failed
RATE_LIMIT_ERROR = -32002  # Rate limit exceeded


def error_message(code: int) -> str:
    """Get the standard message for a JSON-RPC error code."""
    messages = {
        PARSE_ERROR: "Parse error",
        INVALID_REQUEST: "Invalid Request",
        METHOD_NOT_FOUND: "Method not found",
        INVALID_PARAMS: "Invalid params",
        INTERNAL_ERROR: "Internal error",
        TOOL_EXECUTION_ERROR: "Tool execution error",
        AUTHENTICATION_ERROR: "Authentication required",
        RATE_LIMIT_ERROR: "Rate limit exceeded",
    }
    return messages.get(code, "Unknown error")


def make_error_data(code: int, message: str | None = None, data: Any = None) -> dict[str, Any]:
    """Create an error object for JSON-RPC response."""
    error: dict[str, Any] = {
        "code": code,
        "message": message or error_message(code),
    }
    if data is not None:
        error["data"] = data
    return error

