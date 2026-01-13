"""HTTP client utilities with retry, timeout handling, and connection pooling."""

import asyncio
import logging
import time
from typing import Any

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.config.loader import get_settings

logger = logging.getLogger(__name__)


# =============================================================================
# Connection Pooling - Shared HTTP Client
# =============================================================================

_shared_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


async def get_shared_client() -> httpx.AsyncClient:
    """Get a shared HTTP client with connection pooling.
    
    This significantly improves performance by reusing TCP connections
    and avoiding SSL handshake overhead for each request.
    """
    global _shared_client
    
    if _shared_client is None or _shared_client.is_closed:
        async with _client_lock:
            # Double-check after acquiring lock
            if _shared_client is None or _shared_client.is_closed:
                settings = get_settings()
                _shared_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(30.0),  # Reasonable default
                    follow_redirects=True,
                    headers={
                        "User-Agent": f"{settings.server_name}/{settings.server_version}",
                    },
                    # Connection pooling settings
                    limits=httpx.Limits(
                        max_keepalive_connections=10,
                        max_connections=20,
                        keepalive_expiry=30.0,
                    ),
                )
                logger.debug("Created shared HTTP client with connection pooling")
    
    return _shared_client


async def close_shared_client() -> None:
    """Close the shared HTTP client (call on shutdown)."""
    global _shared_client
    if _shared_client is not None:
        await _shared_client.aclose()
        _shared_client = None
        logger.debug("Closed shared HTTP client")


def create_http_client(
    timeout: float | None = None,
    base_url: str | None = None,
) -> httpx.AsyncClient:
    """
    Create an async HTTP client with sensible defaults.
    
    NOTE: For better performance, prefer using get_shared_client() which
    provides connection pooling. Use this only when you need a separate
    client with custom settings.
    
    Args:
        timeout: Request timeout in seconds. Uses default from settings if None.
        base_url: Optional base URL for all requests.
    
    Returns:
        Configured httpx.AsyncClient instance.
    """
    settings = get_settings()
    
    if timeout is None:
        timeout = float(settings.default_timeout)
    
    return httpx.AsyncClient(
        base_url=base_url or "",
        timeout=httpx.Timeout(timeout),
        follow_redirects=True,
        headers={
            "User-Agent": f"{settings.server_name}/{settings.server_version}",
        },
    )


# =============================================================================
# Simple In-Memory Cache
# =============================================================================

class SimpleCache:
    """Simple TTL cache for API responses."""
    
    def __init__(self, default_ttl: int = 300):
        """Initialize cache with default TTL in seconds."""
        self._cache: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl
    
    def get(self, key: str) -> Any | None:
        """Get value from cache if not expired."""
        if key in self._cache:
            value, expires_at = self._cache[key]
            if time.time() < expires_at:
                logger.debug(f"Cache hit: {key}")
                return value
            else:
                # Expired, remove it
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set value in cache with TTL."""
        ttl = ttl or self._default_ttl
        self._cache[key] = (value, time.time() + ttl)
        logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
    
    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()


# Global cache instance (5 minute default TTL)
response_cache = SimpleCache(default_ttl=300)


# =============================================================================
# Retry Decorator
# =============================================================================

# Retry decorator for HTTP requests
http_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
    reraise=True,
)


# =============================================================================
# HTTP Helper Functions (using shared client)
# =============================================================================

@http_retry
async def fetch_json(
    url: str,
    params: dict[str, Any] | None = None,
    timeout: float | None = None,
    cache_ttl: int | None = None,
) -> dict[str, Any]:
    """
    Fetch JSON from a URL with retries and optional caching.
    
    Uses shared HTTP client with connection pooling for better performance.
    
    Args:
        url: The URL to fetch.
        params: Optional query parameters.
        timeout: Optional timeout override.
        cache_ttl: If set, cache response for this many seconds.
    
    Returns:
        Parsed JSON response.
    
    Raises:
        httpx.HTTPStatusError: On HTTP error status.
        httpx.TimeoutException: On timeout.
        ValueError: If response is not valid JSON.
    """
    # Check cache first if caching is enabled
    if cache_ttl:
        cache_key = f"GET:{url}:{params}"
        cached = response_cache.get(cache_key)
        if cached is not None:
            return cached
    
    client = await get_shared_client()
    
    # Apply custom timeout if specified
    if timeout:
        response = await client.get(url, params=params, timeout=timeout)
    else:
        response = await client.get(url, params=params)
    
    response.raise_for_status()
    result = response.json()
    
    # Cache result if TTL specified
    if cache_ttl:
        response_cache.set(cache_key, result, cache_ttl)
    
    return result


@http_retry
async def post_json(
    url: str,
    data: dict[str, Any],
    timeout: float | None = None,
) -> dict[str, Any]:
    """
    POST JSON to a URL with retries.
    
    Uses shared HTTP client with connection pooling for better performance.
    
    Args:
        url: The URL to post to.
        data: JSON data to send.
        timeout: Optional timeout override.
    
    Returns:
        Parsed JSON response.
    
    Raises:
        httpx.HTTPStatusError: On HTTP error status.
        httpx.TimeoutException: On timeout.
        ValueError: If response is not valid JSON.
    """
    client = await get_shared_client()
    
    if timeout:
        response = await client.post(url, json=data, timeout=timeout)
    else:
        response = await client.post(url, json=data)
    
    response.raise_for_status()
    return response.json()

