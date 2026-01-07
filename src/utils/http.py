"""HTTP client utilities with retry and timeout handling."""

import logging
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


def create_http_client(
    timeout: float | None = None,
    base_url: str | None = None,
) -> httpx.AsyncClient:
    """
    Create an async HTTP client with sensible defaults.
    
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


# Retry decorator for HTTP requests
http_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
    reraise=True,
)


@http_retry
async def fetch_json(
    url: str,
    params: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """
    Fetch JSON from a URL with retries.
    
    Args:
        url: The URL to fetch.
        params: Optional query parameters.
        timeout: Optional timeout override.
    
    Returns:
        Parsed JSON response.
    
    Raises:
        httpx.HTTPStatusError: On HTTP error status.
        httpx.TimeoutException: On timeout.
        ValueError: If response is not valid JSON.
    """
    async with create_http_client(timeout=timeout) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


@http_retry
async def post_json(
    url: str,
    data: dict[str, Any],
    timeout: float | None = None,
) -> dict[str, Any]:
    """
    POST JSON to a URL with retries.
    
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
    async with create_http_client(timeout=timeout) as client:
        response = await client.post(url, json=data)
        response.raise_for_status()
        return response.json()

