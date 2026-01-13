"""Riksantikvaren ArcGIS REST API client."""

import json
import logging
from typing import Any

from src.utils.http import fetch_json

logger = logging.getLogger(__name__)

# Only fetch fields we actually use in formatting - reduces response size significantly
ESSENTIAL_FIELDS = (
    "OBJECTID,navn,Navn,lokalitetsnavn,Lokalitetsnavn,tittel,"
    "kategori,kulturminnekategori,kommune,fylke,vernetype,vernestatus,"
    "datering,kulturminnedatering,funksjon,kulturminneopprinneligfunksjon,"
    "linkKulturminnesok"
)


class RiksantikvarenArcGISClient:
    """Client for the Riksantikvaren ArcGIS REST API.
    
    Uses shared HTTP client with connection pooling for better performance.
    """

    BASE_URL = "https://kart.ra.no/arcgis/rest/services/Distribusjon"
    
    # Cache TTLs
    SERVICES_CACHE_TTL = 3600  # 1 hour for service list
    QUERY_TIMEOUT = 30  # 30s timeout for queries

    async def list_services(self) -> dict[str, Any]:
        """
        List available map services.
        
        Cached for 1 hour as services rarely change.
        
        Returns:
            Services metadata
        """
        return await fetch_json(
            f"{self.BASE_URL}",
            params={"f": "json"},
            cache_ttl=self.SERVICES_CACHE_TTL,
        )

    async def get_service_info(self, service_name: str) -> dict[str, Any]:
        """
        Get information about a specific map service.
        
        Args:
            service_name: Service name (e.g., 'Kulturminner')
        
        Returns:
            Service metadata including layers
        """
        return await fetch_json(
            f"{self.BASE_URL}/{service_name}/MapServer",
            params={"f": "json"},
            cache_ttl=self.SERVICES_CACHE_TTL,
        )

    async def query_layer(
        self,
        service_name: str,
        layer_id: int,
        where: str = "1=1",
        geometry: dict[str, Any] | None = None,
        geometry_type: str = "esriGeometryEnvelope",
        spatial_rel: str = "esriSpatialRelIntersects",
        out_fields: str | None = None,
        return_geometry: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        Query features from a layer.
        
        Args:
            service_name: Service name (e.g., 'Kulturminner')
            layer_id: Layer ID within the service
            where: SQL WHERE clause
            geometry: Geometry for spatial query (JSON)
            geometry_type: Type of geometry
            spatial_rel: Spatial relationship
            out_fields: Fields to return (defaults to essential fields only)
            return_geometry: Whether to include geometry
            limit: Max records
            offset: Result offset
        
        Returns:
            Query results (GeoJSON)
        """
        # Use essential fields by default to reduce response size
        if out_fields is None:
            out_fields = ESSENTIAL_FIELDS
        
        params: dict[str, Any] = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": str(return_geometry).lower(),
            "outSR": "4326",  # WGS84
            "f": "geojson",
            "resultRecordCount": limit,
            "resultOffset": offset,
        }

        if geometry:
            params["geometry"] = json.dumps(geometry)
            params["geometryType"] = geometry_type
            params["spatialRel"] = spatial_rel
            params["inSR"] = "4326"

        return await fetch_json(
            f"{self.BASE_URL}/{service_name}/MapServer/{layer_id}/query",
            params=params,
            timeout=self.QUERY_TIMEOUT,
        )

    async def query_nearby(
        self,
        service_name: str,
        layer_id: int,
        lat: float,
        lon: float,
        distance: int = 1000,  # meters
        out_fields: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Query features near a point.
        
        Args:
            service_name: Service name
            layer_id: Layer ID
            lat: Latitude
            lon: Longitude
            distance: Search distance in meters
            out_fields: Fields to return (defaults to essential fields)
            limit: Max records
        
        Returns:
            GeoJSON FeatureCollection
        """
        # Use essential fields by default to reduce response size
        if out_fields is None:
            out_fields = ESSENTIAL_FIELDS
        
        geometry = {"x": lon, "y": lat}
        
        params = {
            "where": "1=1",
            "geometry": json.dumps(geometry),
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "distance": distance,
            "units": "esriSRUnit_Meter",
            "inSR": "4326",
            "outSR": "4326",
            "outFields": out_fields,
            "returnGeometry": "true",
            "f": "geojson",
            "resultRecordCount": limit,
        }

        return await fetch_json(
            f"{self.BASE_URL}/{service_name}/MapServer/{layer_id}/query",
            params=params,
            timeout=self.QUERY_TIMEOUT,
        )

    async def query_bbox(
        self,
        service_name: str,
        layer_id: int,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        out_fields: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Query features within a bounding box.
        
        Args:
            service_name: Service name
            layer_id: Layer ID
            min_lon, min_lat, max_lon, max_lat: Bounding box
            out_fields: Fields to return (defaults to essential fields)
            limit: Max records
        
        Returns:
            GeoJSON FeatureCollection
        """
        geometry = {
            "xmin": min_lon,
            "ymin": min_lat,
            "xmax": max_lon,
            "ymax": max_lat,
        }

        return await self.query_layer(
            service_name=service_name,
            layer_id=layer_id,
            geometry=geometry,
            geometry_type="esriGeometryEnvelope",
            out_fields=out_fields,
            limit=limit,
        )


# Singleton client
_client: RiksantikvarenArcGISClient | None = None


def get_client() -> RiksantikvarenArcGISClient:
    """Get the Riksantikvaren ArcGIS client instance."""
    global _client
    if _client is None:
        _client = RiksantikvarenArcGISClient()
    return _client


# Available services in the Distribusjon folder
AVAILABLE_SERVICES = {
    "Kulturminner20180301": {
        "description": "All cultural heritage sites from Askeladden (2018 dataset)",
        "layers": {
            0: "Bygninger (Buildings)",
            1: "FredaBygninger (Protected buildings)",
            2: "SefrakBygninger (SEFRAK buildings)",
            3: "Kulturminner (Heritage sites - icons)",
            4: "Enkeltminneikoner (Single monuments - icons)",
            5: "Lokalitetsikoner (Localities - icons)",
            6: "Enkeltminner (Single monuments - polygons)",  # Best for queries
            7: "Lokaliteter (Localities - polygons)",
            8: "Sikringssoner (Protection zones)",
            9: "Brannvern (Fire protection)",
            10: "Brannsmitteomradeikoner (Fire spread areas - icons)",
            11: "VerneverdigTetteTrehusmiljoikoner (Preservation areas - icons)",
            12: "Brannsmitteomrader (Fire spread areas)",
            13: "VerneverdigTetteTrehusmiljoer (Preservation areas)",
            14: "Kulturmiljoer (Cultural environments)",
            15: "Kulturmiljoer_flate (Cultural environments - polygons)",
            16: "Kulturmiljoikoner (Cultural environments - icons)",
        }
    },
    "FjernmalteArkeologiskeKulturminner": {
        "description": "Remotely sensed archaeological heritage sites",
        "layers": {
            0: "Fjernmålte arkeologiske kulturminner",
        }
    },
}

# Default service and layer for queries
DEFAULT_SERVICE = "Kulturminner20180301"
DEFAULT_LAYER = 6  # Enkeltminner - has the best data

