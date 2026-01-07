"""JSON-RPC 2.0 message processing."""

import json
import logging
from typing import Any

from pydantic import ValidationError

from src.mcp.models import JsonRpcRequest, JsonRpcResponse, JsonRpcError
from src.mcp.handlers import MCPHandlers
from src.mcp.errors import PARSE_ERROR, INVALID_REQUEST, make_error_data

logger = logging.getLogger(__name__)


class JsonRpcProcessor:
    """Process JSON-RPC 2.0 messages."""

    def __init__(self, handlers: MCPHandlers):
        self.handlers = handlers

    def parse_request(self, raw_data: str | bytes) -> tuple[JsonRpcRequest | None, dict | None]:
        """
        Parse a JSON-RPC request from raw data.
        
        Returns (request, error) tuple. One will be None.
        """
        # Try to parse JSON
        try:
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode("utf-8")
            data = json.loads(raw_data)
        except json.JSONDecodeError as e:
            return None, make_error_data(PARSE_ERROR, f"Invalid JSON: {e}")

        # Validate JSON-RPC structure
        try:
            request = JsonRpcRequest(**data)
            return request, None
        except ValidationError as e:
            return None, make_error_data(
                INVALID_REQUEST, f"Invalid JSON-RPC request: {e}"
            )

    async def process_request(
        self, request: JsonRpcRequest
    ) -> JsonRpcResponse | None:
        """
        Process a validated JSON-RPC request.
        
        Returns None for notifications (requests without id).
        """
        is_notification = request.id is None

        # Dispatch to handler
        result, error = await self.handlers.dispatch(request.method, request.params)

        # Notifications don't get responses
        if is_notification:
            return None

        # Build response
        if error is not None:
            return JsonRpcResponse(
                id=request.id,
                error=JsonRpcError(**error),
            )
        else:
            return JsonRpcResponse(
                id=request.id,
                result=result,
            )

    async def handle_message(self, raw_data: str | bytes) -> JsonRpcResponse | None:
        """
        Handle a raw JSON-RPC message end-to-end.
        
        Returns a response or None for notifications.
        """
        request, parse_error = self.parse_request(raw_data)

        if parse_error is not None:
            # Parse errors don't have a request id
            return JsonRpcResponse(
                id=None,
                error=JsonRpcError(**parse_error),
            )

        return await self.process_request(request)  # type: ignore

    def serialize_response(self, response: JsonRpcResponse) -> str:
        """Serialize a JSON-RPC response to JSON string."""
        return json.dumps(response.model_dump())

