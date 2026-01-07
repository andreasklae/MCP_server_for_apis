"""Wikipedia (MediaWiki) API client."""

import logging
from typing import Any

import httpx

from src.utils.http import create_http_client

logger = logging.getLogger(__name__)


class WikipediaClient:
    """Client for the MediaWiki API."""

    def __init__(self, language: str = "no"):
        self.language = language
        self.base_url = f"https://{language}.wikipedia.org/w/api.php"

    async def search(
        self, query: str, limit: int = 10, offset: int = 0
    ) -> dict[str, Any]:
        """
        Search for Wikipedia articles.
        
        Args:
            query: Search query
            limit: Maximum results (max 500)
            offset: Pagination offset
        
        Returns:
            Search results with titles, snippets, etc.
        """
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": min(limit, 500),
            "sroffset": offset,
            "format": "json",
        }

        async with create_http_client(timeout=30) as client:
            response = await client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

        if "error" in data:
            raise Exception(f"Wikipedia API error: {data['error'].get('info', 'Unknown error')}")

        return data.get("query", {}).get("search", [])

    async def get_summary(
        self, title: str, sentences: int | None = None
    ) -> dict[str, Any]:
        """
        Get article summary/extract.
        
        Args:
            title: Article title
            sentences: Limit to N sentences (optional)
        
        Returns:
            Article extract and metadata
        """
        params = {
            "action": "query",
            "prop": "extracts|info|pageimages",
            "exintro": "true",
            "explaintext": "true",
            "titles": title,
            "format": "json",
            "inprop": "url",
            "pithumbsize": 300,
        }

        if sentences:
            params["exsentences"] = sentences

        async with create_http_client(timeout=30) as client:
            response = await client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

        if "error" in data:
            raise Exception(f"Wikipedia API error: {data['error'].get('info', 'Unknown error')}")

        pages = data.get("query", {}).get("pages", {})
        # Return first page (there should only be one)
        for page_id, page_data in pages.items():
            if page_id == "-1":
                return {"error": "Page not found", "title": title}
            return page_data

        return {"error": "No results", "title": title}

    async def geosearch(
        self, lat: float, lon: float, radius: int = 1000, limit: int = 10
    ) -> list[dict[str, Any]]:
        """
        Find Wikipedia articles near coordinates.
        
        Args:
            lat: Latitude
            lon: Longitude
            radius: Search radius in meters (max 10000)
            limit: Maximum results (max 500)
        
        Returns:
            List of nearby articles with distance
        """
        params = {
            "action": "query",
            "list": "geosearch",
            "gscoord": f"{lat}|{lon}",
            "gsradius": min(radius, 10000),
            "gslimit": min(limit, 500),
            "format": "json",
        }

        async with create_http_client(timeout=30) as client:
            response = await client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

        if "error" in data:
            raise Exception(f"Wikipedia API error: {data['error'].get('info', 'Unknown error')}")

        return data.get("query", {}).get("geosearch", [])


# Default client instance
_clients: dict[str, WikipediaClient] = {}


def get_client(language: str = "no") -> WikipediaClient:
    """Get a Wikipedia client for the specified language."""
    if language not in _clients:
        _clients[language] = WikipediaClient(language)
    return _clients[language]

