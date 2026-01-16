"""Riksantikvaren OGC API client."""

import logging
from typing import Any

from src.utils.http import fetch_json

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
    """Client for the Riksantikvaren OGC API Features.
    
    Uses shared HTTP client with connection pooling and caching for better performance.
    """

    BASE_URL = "https://api.ra.no"
    
    # Cache TTLs
    DATASETS_CACHE_TTL = 3600  # 1 hour for dataset list (rarely changes)
    COLLECTIONS_CACHE_TTL = 3600  # 1 hour for collections
    FEATURES_TIMEOUT = 30  # 30s timeout for feature queries

    async def list_datasets(self) -> list[dict[str, Any]]:
        """
        List available datasets (APIs).
        
        Cached for 1 hour as datasets rarely change.
        
        Returns:
            List of dataset metadata
        """
        data = await fetch_json(
            f"{self.BASE_URL}",
            params={"f": "json"},
            cache_ttl=self.DATASETS_CACHE_TTL,
        )
        return data.get("apis", [])

    async def list_collections(self, dataset_id: str = "kulturminner") -> list[dict[str, Any]]:
        """
        List available collections within a dataset.
        
        Cached for 1 hour as collections rarely change.
        
        Args:
            dataset_id: Dataset identifier (e.g., 'kulturminner', 'kulturmiljoer')
        
        Returns:
            List of collection metadata
        """
        data = await fetch_json(
            f"{self.BASE_URL}/{dataset_id}/collections",
            params={"f": "json"},
            cache_ttl=self.COLLECTIONS_CACHE_TTL,
        )
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
        return await fetch_json(
            f"{self.BASE_URL}/{dataset_id}/collections/{collection_id}",
            params={"f": "json"},
            cache_ttl=self.COLLECTIONS_CACHE_TTL,
        )

    async def get_features(
        self,
        dataset_id: str = "kulturminner",
        collection_id: str = "kulturminner",
        bbox: tuple[float, float, float, float] | None = None,
        limit: int = 50,
        offset: int = 0,
        cql_filter: str | None = None,
    ) -> dict[str, Any]:
        """
        Query features from a collection.

        Args:
            dataset_id: Dataset identifier (default: 'kulturminner')
            collection_id: Collection identifier (default: 'kulturminner')
            bbox: Bounding box as (min_lon, min_lat, max_lon, max_lat)
            limit: Maximum features to return
            offset: Pagination offset
            cql_filter: CQL2 filter expression for advanced queries (e.g., text search)

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

        if cql_filter:
            params["filter"] = cql_filter
            params["filter-lang"] = "cql2-text"

        return await fetch_json(
            f"{self.BASE_URL}/{dataset_id}/collections/{collection_id}/items",
            params=params,
            timeout=self.FEATURES_TIMEOUT,
        )

    async def get_feature(
        self,
        feature_id: str,
        dataset_id: str = "kulturminner",
        collection_id: str = "kulturminner",
    ) -> dict[str, Any]:
        """
        Get a single feature by ID.
        
        Individual features cached for 5 minutes (default TTL).
        
        Args:
            feature_id: Feature identifier
            dataset_id: Dataset identifier
            collection_id: Collection identifier
        
        Returns:
            GeoJSON Feature
        """
        return await fetch_json(
            f"{self.BASE_URL}/{dataset_id}/collections/{collection_id}/items/{feature_id}",
            params={"f": "json"},
            timeout=self.FEATURES_TIMEOUT,
            cache_ttl=300,  # Cache individual features for 5 minutes
        )

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

    async def search_text(
        self,
        query: str,
        dataset_id: str = "kulturminner",
        collection_id: str = "kulturminner",
        search_fields: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Search for features by text using CQL2 LIKE with case-insensitive matching.

        Args:
            query: Search term(s) to find in feature names/descriptions
            dataset_id: Dataset identifier (default: 'kulturminner')
            collection_id: Collection identifier (default: 'kulturminner')
            search_fields: Fields to search (default: ['navn', 'informasjon'])
            limit: Maximum results

        Returns:
            GeoJSON FeatureCollection

        Example:
            # Search for "slott" in kulturminner
            results = await client.search_text("slott", dataset_id="kulturminner")
        """
        if search_fields is None:
            search_fields = ["navn", "informasjon"]

        # Build CQL2 filter with case-insensitive LIKE for each field
        # Format: CASEI(field) LIKE CASEI('%term%')
        filter_parts = []
        for field in search_fields:
            filter_parts.append(f"CASEI({field}) LIKE CASEI('%{query}%')")

        # Combine with OR operator
        cql_filter = " OR ".join(filter_parts)

        return await self.get_features(
            dataset_id=dataset_id,
            collection_id=collection_id,
            cql_filter=cql_filter,
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

