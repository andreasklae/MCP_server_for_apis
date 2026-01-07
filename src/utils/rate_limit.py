"""Rate limiting middleware and utilities."""

import logging
import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.config.loader import get_settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple in-memory rate limiter using sliding window."""
    
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.window_size = 60  # seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
    
    def is_allowed(self, key: str) -> tuple[bool, int]:
        """
        Check if a request is allowed for the given key.
        
        Args:
            key: Identifier for the client (e.g., IP address).
        
        Returns:
            Tuple of (is_allowed, remaining_requests).
        """
        now = time.time()
        window_start = now - self.window_size
        
        # Clean old requests
        self._requests[key] = [
            ts for ts in self._requests[key] if ts > window_start
        ]
        
        # Check limit
        current_count = len(self._requests[key])
        remaining = max(0, self.requests_per_minute - current_count)
        
        if current_count >= self.requests_per_minute:
            return False, 0
        
        # Record this request
        self._requests[key].append(now)
        return True, remaining - 1
    
    def reset(self, key: str | None = None) -> None:
        """Reset rate limit for a key or all keys."""
        if key is None:
            self._requests.clear()
        else:
            self._requests.pop(key, None)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce rate limiting."""
    
    def __init__(self, app, limiter: RateLimiter | None = None):
        super().__init__(app)
        settings = get_settings()
        self.enabled = settings.rate_limit_enabled
        self.limiter = limiter or RateLimiter(settings.rate_limit_per_minute)
    
    def _get_client_key(self, request: Request) -> str:
        """Get identifier for rate limiting (IP address)."""
        # Check for forwarded IP (behind proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        # Fall back to direct client IP
        if request.client:
            return request.client.host
        
        return "unknown"
    
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        if not self.enabled:
            return await call_next(request)
        
        client_key = self._get_client_key(request)
        is_allowed, remaining = self.limiter.is_allowed(client_key)
        
        if not is_allowed:
            logger.warning(f"Rate limit exceeded for {client_key}")
            return JSONResponse(
                status_code=429,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32002,
                        "message": "Rate limit exceeded. Please try again later.",
                    },
                },
                headers={
                    "X-RateLimit-Limit": str(self.limiter.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": "60",
                },
            )
        
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.limiter.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        
        return response

