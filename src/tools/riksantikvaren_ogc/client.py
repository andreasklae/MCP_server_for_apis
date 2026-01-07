"""Riksantikvaren OGC API client."""

import logging
from typing import Any

from src.utils.http import create_http_client

logger = logging.getLogger(__name__)


class RiksantikvarenOGCClient:
    """Client for the Riksantikvaren OGC API Features."""

    BASE_URL = "https://api.ra.no"

    async def list_collections(self) -> list[dict[str, Any]]:
        """
        List available data collections.
        
        Returns:
            List of collection metadata
        """
        async with create_http_client(timeout=60) as client:
            response = await client.get(f"{self.BASE_URL}/collections", params={"f": "json"})
            response.raise_for_status()
            data = response.json()
            return data.get("collections", [])

    async def get_collection(self, collection_id: str) -> dict[str, Any]:
        """
        Get metadata for a specific collection.
        
        Args:
            collection_id: Collection identifier
        
        Returns:
            Collection metadata
        """
        async with create_http_client(timeout=60) as client:
            response = await client.get(
                f"{self.BASE_URL}/collections/{collection_id}",
                params={"f": "json"}
            )
            response.raise_for_status()
            return response.json()

    async def get_features(
        self,
        collection_id: str,
        bbox: tuple[float, float, float, float] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        Query features from a collection.
        
        Args:
            collection_id: Collection identifier
            bbox: Bounding box as (min_lon, min_lat, max_lon, max_lat)
            limit: Maximum features to return
            offset: Pagination offset
        
        Returns:
            GeoJSON FeatureCollection
        """
        params: dict[str, Any] = {
            "f": "json",
            "limit": min(limit, 100),  # API can be unstable with large limits
            "offset": offset,
        }

        if bbox:
            params["bbox"] = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"

        async with create_http_client(timeout=60) as client:
            response = await client.get(
                f"{self.BASE_URL}/collections/{collection_id}/items",
                params=params
            )
            response.raise_for_status()
            return response.json()

    async def get_feature(self, collection_id: str, feature_id: str) -> dict[str, Any]:
        """
        Get a single feature by ID.
        
        Args:
            collection_id: Collection identifier
            feature_id: Feature identifier
        
        Returns:
            GeoJSON Feature
        """
        async with create_http_client(timeout=60) as client:
            response = await client.get(
                f"{self.BASE_URL}/collections/{collection_id}/items/{feature_id}",
                params={"f": "json"}
            )
            response.raise_for_status()
            return response.json()

    async def search_nearby(
        self,
        lat: float,
        lon: float,
        radius_deg: float = 0.01,  # ~1km at 60°N
        collection_id: str = "kulturminner",
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Search for features near a point using bbox.
        
        Args:
            lat: Latitude
            lon: Longitude
            radius_deg: Search radius in degrees (approx 0.01 = 1km)
            collection_id: Collection to search
            limit: Maximum results
        
        Returns:
            GeoJSON FeatureCollection
        """
        bbox = (
            lon - radius_deg,
            lat - radius_deg,
            lon + radius_deg,
            lat + radius_deg,
        )
        return await self.get_features(collection_id, bbox=bbox, limit=limit)


# Singleton client
_client: RiksantikvarenOGCClient | None = None


def get_client() -> RiksantikvarenOGCClient:
    """Get the Riksantikvaren OGC client instance."""
    global _client
    if _client is None:
        _client = RiksantikvarenOGCClient()
    return _client

