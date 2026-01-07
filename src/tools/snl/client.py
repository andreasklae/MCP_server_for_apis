"""Store Norske Leksikon (SNL) API client."""

import logging
from typing import Any

from src.utils.http import create_http_client

logger = logging.getLogger(__name__)


class SNLClient:
    """Client for the SNL API."""

    BASE_URL = "https://snl.no"

    async def search(
        self, query: str, limit: int = 10, offset: int = 0
    ) -> list[dict[str, Any]]:
        """
        Search for articles in SNL.
        
        Args:
            query: Search term
            limit: Maximum results
            offset: Pagination offset
        
        Returns:
            List of article previews
        """
        params = {
            "query": query,
            "limit": limit,
            "offset": offset,
        }

        async with create_http_client(timeout=30) as client:
            response = await client.get(
                f"{self.BASE_URL}/api/v1/search", params=params
            )
            response.raise_for_status()
            return response.json()

    async def get_article(self, identifier: str) -> dict[str, Any]:
        """
        Get an article by ID or slug.
        
        Args:
            identifier: Article ID (numeric) or URL slug
        
        Returns:
            Full article data
        """
        # Check if it's a numeric ID or a slug
        if identifier.isdigit():
            url = f"{self.BASE_URL}/api/v1/article/{identifier}"
        else:
            # It's a slug - use the .json endpoint
            # Remove leading slash if present
            slug = identifier.lstrip("/")
            url = f"{self.BASE_URL}/{slug}.json"

        async with create_http_client(timeout=30) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()


# Singleton client
_client: SNLClient | None = None


def get_client() -> SNLClient:
    """Get the SNL client instance."""
    global _client
    if _client is None:
        _client = SNLClient()
    return _client

