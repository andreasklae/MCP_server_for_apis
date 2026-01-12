"""Authentication middleware and utilities."""

import logging
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.config.loader import get_settings

logger = logging.getLogger(__name__)


def verify_auth_token(token: str | None) -> bool:
    """
    Verify an authentication token.
    
    Returns True if:
    - Auth is disabled (no MCP_AUTH_TOKEN set)
    - Token matches the configured MCP_AUTH_TOKEN
    """
    settings = get_settings()
    
    # If no auth token configured, allow all
    if not settings.auth_enabled:
        return True
    
    # Check if token matches
    if token is None:
        return False
    
    return token == settings.mcp_auth_token


def extract_bearer_token(authorization: str | None) -> str | None:
    """Extract token from Authorization header."""
    if authorization is None:
        return None
    
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    
    return parts[1]


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce authentication on protected endpoints."""
    
    # Paths that require authentication (when enabled)
    PROTECTED_PATHS = ["/sse", "/message", "/api/chat", "/api/chat/stream"]
    
    # Paths that are always public (no auth required)
    PUBLIC_PATHS = [
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/debug",
    ]
    
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        settings = get_settings()
        
        path = request.url.path
        logger.debug(
            f"Auth check: path={path}, auth_enabled={settings.auth_enabled}, "
            f"token_set={bool(settings.mcp_auth_token)}"
        )
        
        # Skip auth if not enabled
        if not settings.auth_enabled:
            logger.debug("Auth disabled, skipping")
            return await call_next(request)
        
        # Check protected paths FIRST (before public paths check)
        if any(path.startswith(p) for p in self.PROTECTED_PATHS):
            auth_header = request.headers.get("Authorization")
            token = extract_bearer_token(auth_header)
            
            if not verify_auth_token(token):
                logger.warning(f"Unauthorized access attempt to {path}")
                
                # Return appropriate error format based on endpoint
                if path.startswith("/api/"):
                    # REST API format
                    return JSONResponse(
                        status_code=401,
                        content={
                            "error": "Authentication required",
                            "message": "Please provide a valid API token in the Authorization header",
                        },
                    )
                else:
                    # MCP JSON-RPC format
                    return JSONResponse(
                        status_code=401,
                        content={
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {
                                "code": -32001,
                                "message": "Authentication required",
                            },
                        },
                    )
        
        return await call_next(request)

