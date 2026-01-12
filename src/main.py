"""FastAPI MCP Server - Main application entrypoint."""

import json
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config.loader import get_settings, load_api_config, get_enabled_providers
from src.mcp.registry import get_registry
from src.mcp.handlers import MCPHandlers
from src.mcp.jsonrpc import JsonRpcProcessor
from src.mcp.transport_sse import (
    get_session_manager,
    create_sse_response,
)
from src.security.auth import AuthMiddleware
from src.utils.rate_limit import RateLimitMiddleware
from src.utils.logging import setup_logging, set_request_id, get_logger

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    # Startup
    setup_logging()
    log = get_logger("startup")
    
    settings = get_settings()
    log.info(
        "Starting MCP server",
        server_name=settings.server_name,
        version=settings.server_version,
        auth_enabled=settings.auth_enabled,
    )
    
    # Load API configuration and register tools
    config = load_api_config()
    enabled_providers = get_enabled_providers(config)
    log.info("Loading providers", providers=enabled_providers)
    
    registry = get_registry()
    results = registry.load_providers(enabled_providers)
    
    for provider, success in results.items():
        if success:
            log.info("Loaded provider", provider=provider)
        else:
            log.warning("Failed to load provider", provider=provider)
    
    log.info(
        "Tool registry ready",
        tool_count=registry.tool_count,
        provider_count=registry.provider_count,
    )
    
    # Start session cleanup task
    session_manager = get_session_manager()
    await session_manager.start_cleanup_task()
    
    yield
    
    # Shutdown
    log.info("Shutting down MCP server")
    session_manager.stop_cleanup_task()


# Create FastAPI app
app = FastAPI(
    title="Kulturarv MCP Server",
    description="MCP server for Norwegian cultural heritage APIs - OpenAI Agent Builder compatible",
    version="1.0.0",
    lifespan=lifespan,
)

# Add middleware in reverse order (last added = first to process incoming requests)
# So we add: RateLimitMiddleware, AuthMiddleware, then CORS (CORS needs to be LAST to process FIRST)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthMiddleware)

# CORS must be added LAST so it processes incoming requests FIRST (handles OPTIONS preflight)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for MCP compatibility
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# Request ID middleware
@app.middleware("http")
async def add_request_id_middleware(request: Request, call_next):
    """Add request ID to all requests."""
    request_id = request.headers.get("X-Request-ID") or set_request_id()
    set_request_id(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# =============================================================================
# Health and Info Endpoints
# =============================================================================


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/debug/auth")
async def debug_auth() -> dict:
    """Debug endpoint to check auth status (remove in production)."""
    import os
    settings = get_settings()
    return {
        "auth_enabled": settings.auth_enabled,
        "token_length": len(settings.mcp_auth_token) if settings.mcp_auth_token else 0,
        "token_set": bool(settings.mcp_auth_token),
        "env_var_set": bool(os.environ.get("MCP_AUTH_TOKEN")),
        "env_var_length": len(os.environ.get("MCP_AUTH_TOKEN", "")),
    }


@app.get("/")
async def root() -> dict:
    """Root endpoint with server info."""
    settings = get_settings()
    registry = get_registry()
    
    return {
        "name": settings.server_name,
        "version": settings.server_version,
        "description": "MCP server for Norwegian cultural heritage APIs",
        "endpoints": {
            "health": "/health",
            "sse": "/sse",
            "message": "/message",
            "docs": "/docs",
        },
        "tools_available": registry.tool_count,
        "mcp_protocol_version": "2024-11-05",
    }


# =============================================================================
# MCP Endpoints
# =============================================================================


@app.get("/sse")
async def sse_endpoint(request: Request):
    """
    SSE endpoint for MCP session establishment.
    
    Returns an SSE stream that:
    1. Sends an 'endpoint' event with the message URL
    2. Streams tool results and other events
    """
    session_manager = get_session_manager()
    session = session_manager.create_session()
    
    log = get_logger("sse")
    log.info("SSE session created", session_id=session.session_id)
    
    return await create_sse_response(session, "/message")


@app.post("/message")
async def message_endpoint(request: Request) -> JSONResponse:
    """
    Message endpoint for JSON-RPC requests.
    
    Accepts JSON-RPC 2.0 messages and returns responses.
    If session_id is provided, also pushes result to SSE stream.
    """
    # Get session ID if provided
    session_id = request.query_params.get("session_id")
    
    # Parse request body
    try:
        body = await request.body()
    except Exception as e:
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Could not read request body: {e}"},
            }
        )
    
    # Process the message
    registry = get_registry()
    handlers = MCPHandlers(registry)
    processor = JsonRpcProcessor(handlers)
    
    response = await processor.handle_message(body)
    
    if response is None:
        # Notification - no response needed
        return JSONResponse(content={"status": "ok"}, status_code=202)
    
    response_data = response.model_dump()
    
    # If there's a session, also push to SSE
    if session_id:
        session_manager = get_session_manager()
        session = session_manager.get_session(session_id)
        if session:
            await session.send_event("message", json.dumps(response_data))
    
    return JSONResponse(content=response_data)


# =============================================================================
# Chat API Endpoint
# =============================================================================

# Simple in-memory rate limiter for chat (per IP)
chat_rate_limits: dict[str, list[float]] = defaultdict(list)


def check_chat_rate_limit(client_ip: str) -> bool:
    """Check if client IP is within rate limit. Returns True if allowed."""
    settings = get_settings()
    now = time.time()
    hour_ago = now - 3600
    
    # Clean old entries
    chat_rate_limits[client_ip] = [
        t for t in chat_rate_limits[client_ip] if t > hour_ago
    ]
    
    # Check limit
    if len(chat_rate_limits[client_ip]) >= settings.chat_rate_limit_per_hour:
        return False
    
    # Record this request
    chat_rate_limits[client_ip].append(now)
    return True


@app.post("/api/chat")
async def chat_endpoint(request: Request) -> JSONResponse:
    """
    Chat endpoint for the AI agent.
    
    Requires MCP auth token in Authorization header.
    Rate limited per IP to control OpenAI costs.
    """
    settings = get_settings()
    
    # Check if chat is enabled
    if not settings.chat_enabled:
        return JSONResponse(
            status_code=503,
            content={"error": "Chat service not configured"}
        )
    
    # Get client IP for rate limiting
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    
    # Check rate limit
    if not check_chat_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": f"Maximum {settings.chat_rate_limit_per_hour} messages per hour"
            }
        )
    
    # Parse request body
    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid JSON: {e}"}
        )
    
    # Import here to avoid circular imports
    from src.agent.runner import AgentRunner, ChatRequest
    
    try:
        chat_request = ChatRequest(**body)
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid request: {e}"}
        )
    
    # Run the agent
    log = get_logger("chat")
    log.info("Chat request", message_length=len(chat_request.message), sources=chat_request.sources)
    
    try:
        runner = AgentRunner(settings.openai_api_key)
        response = await runner.chat(chat_request)
        
        log.info(
            "Chat response",
            tools_used=response.tools_used,
            sources_consulted=response.sources_consulted,
        )
        
        return JSONResponse(content=response.model_dump())
        
    except Exception as e:
        log.error("Chat error", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Chat processing failed: {str(e)}"}
        )


@app.get("/api/chat/status")
async def chat_status() -> dict:
    """Check if chat is available and get configuration."""
    settings = get_settings()
    return {
        "enabled": settings.chat_enabled,
        "rate_limit_per_hour": settings.chat_rate_limit_per_hour,
        "sources_available": ["wikipedia", "snl", "riksantikvaren"],
    }


# =============================================================================
# Main Entry Point
# =============================================================================


def main() -> None:
    """Run the server with uvicorn."""
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    main()

