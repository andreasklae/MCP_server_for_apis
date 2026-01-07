"""Riksantikvaren OGC API client."""

import logging
from typing import Any

from src.utils.http import create_http_client

logger = logging.getLogger(__name__)


# Available datasets on the Riksantikvaren OGC API
AVAILABLE_DATASETS = {
    "kulturminner": {
        "title": "Kulturminner",
        "description": "All cultural heritage sites registered in Askeladden",
        "collections": ["kulturminner", "sikringssoner"],
    },
    "kulturmiljoer": {
        "title": "Kulturmiljøer",
        "description": "Protected cultural environments and world heritage sites",
        "collections": ["kulturmiljoer"],
    },
    "brukerminner": {
        "title": "Brukerminner",
        "description": "User-contributed cultural memories",
        "collections": ["brukerminner"],
    },
    "KulturminnerFredaBygninger": {
        "title": "Freda bygninger",
        "description": "Protected buildings",
        "collections": ["fredabygninger"],
    },
    "KulturminnerSEFRAKbygninger": {
        "title": "SEFRAK-bygninger",
        "description": "SEFRAK registered buildings (pre-1900)",
        "collections": ["sefrakbygninger"],
    },
    "brannvern": {
        "title": "Brannvern",
        "description": "Fire protection areas",
        "collections": ["brannvern"],
    },
}


class RiksantikvarenOGCClient:
    """Client for the Riksantikvaren OGC API Features."""

    BASE_URL = "https://api.ra.no"

    async def list_datasets(self) -> list[dict[str, Any]]:
        """
        List available datasets (APIs).
        
        Returns:
            List of dataset metadata
        """
        async with create_http_client(timeout=60) as client:
            response = await client.get(f"{self.BASE_URL}", params={"f": "json"})
            response.raise_for_status()
            data = response.json()
            return data.get("apis", [])

    async def list_collections(self, dataset_id: str = "kulturminner") -> list[dict[str, Any]]:
        """
        List available collections within a dataset.
        
        Args:
            dataset_id: Dataset identifier (e.g., 'kulturminner', 'kulturmiljoer')
        
        Returns:
            List of collection metadata
        """
        async with create_http_client(timeout=60) as client:
            response = await client.get(
                f"{self.BASE_URL}/{dataset_id}/collections",
                params={"f": "json"}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("collections", [])

    async def get_collection(self, dataset_id: str, collection_id: str) -> dict[str, Any]:
        """
        Get metadata for a specific collection.
        
        Args:
            dataset_id: Dataset identifier
            collection_id: Collection identifier
        
        Returns:
            Collection metadata
        """
        async with create_http_client(timeout=60) as client:
            response = await client.get(
                f"{self.BASE_URL}/{dataset_id}/collections/{collection_id}",
                params={"f": "json"}
            )
            response.raise_for_status()
            return response.json()

    async def get_features(
        self,
        dataset_id: str = "kulturminner",
        collection_id: str = "kulturminner",
        bbox: tuple[float, float, float, float] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        Query features from a collection.
        
        Args:
            dataset_id: Dataset identifier (default: 'kulturminner')
            collection_id: Collection identifier (default: 'kulturminner')
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
                f"{self.BASE_URL}/{dataset_id}/collections/{collection_id}/items",
                params=params
            )
            response.raise_for_status()
            return response.json()

    async def get_feature(
        self,
        feature_id: str,
        dataset_id: str = "kulturminner",
        collection_id: str = "kulturminner",
    ) -> dict[str, Any]:
        """
        Get a single feature by ID.
        
        Args:
            feature_id: Feature identifier
            dataset_id: Dataset identifier
            collection_id: Collection identifier
        
        Returns:
            GeoJSON Feature
        """
        async with create_http_client(timeout=60) as client:
            response = await client.get(
                f"{self.BASE_URL}/{dataset_id}/collections/{collection_id}/items/{feature_id}",
                params={"f": "json"}
            )
            response.raise_for_status()
            return response.json()

    async def search_nearby(
        self,
        lat: float,
        lon: float,
        radius_deg: float = 0.01,  # ~1km at 60°N
        dataset_id: str = "kulturminner",
        collection_id: str = "kulturminner",
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Search for features near a point using bbox.
        
        Args:
            lat: Latitude
            lon: Longitude
            radius_deg: Search radius in degrees (approx 0.01 = 1km)
            dataset_id: Dataset to search
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
        return await self.get_features(
            dataset_id=dataset_id,
            collection_id=collection_id,
            bbox=bbox,
            limit=limit,
        )


# Singleton client
_client: RiksantikvarenOGCClient | None = None


def get_client() -> RiksantikvarenOGCClient:
    """Get the Riksantikvaren OGC client instance."""
    global _client
    if _client is None:
        _client = RiksantikvarenOGCClient()
    return _client

