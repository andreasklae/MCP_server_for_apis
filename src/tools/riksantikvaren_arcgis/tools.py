"""Riksantikvaren ArcGIS REST API provider tools."""

import logging
import math
from typing import Any

from src.mcp.models import TextContent
from src.mcp.registry import ToolRegistry
from src.tools.riksantikvaren_arcgis.client import (
    get_client,
    AVAILABLE_SERVICES,
    DEFAULT_SERVICE,
    DEFAULT_LAYER,
)

logger = logging.getLogger(__name__)


def _calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in meters using Haversine formula."""
    R = 6371000  # Earth's radius in meters
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c


def format_feature(feature: dict[str, Any], index: int = 0, center_lat: float | None = None, center_lon: float | None = None) -> str:
    """Format a GeoJSON feature for display.
    
    Args:
        feature: GeoJSON feature
        index: Feature index for fallback naming
        center_lat: Optional center latitude for distance calculation
        center_lon: Optional center longitude for distance calculation
    """
    props = feature.get("properties", {})
    geometry = feature.get("geometry", {})
    
    # Try to get a name from various possible fields
    name = (
        props.get("navn") or 
        props.get("Navn") or
        props.get("lokalitetsnavn") or
        props.get("Lokalitetsnavn") or
        props.get("tittel") or
        f"Feature {props.get('OBJECTID', index)}"
    )
    
    lines = [f"**{name}**"]
    
    # Add key properties (case-insensitive matching)
    prop_lower = {k.lower(): v for k, v in props.items()}
    
    if prop_lower.get("kategori") or prop_lower.get("kulturminnekategori"):
        lines.append(f"  Kategori: {prop_lower.get('kategori') or prop_lower.get('kulturminnekategori')}")
    if prop_lower.get("kommune"):
        lines.append(f"  Kommune: {prop_lower['kommune']}")
    if prop_lower.get("fylke"):
        lines.append(f"  Fylke: {prop_lower['fylke']}")
    if prop_lower.get("vernetype"):
        lines.append(f"  Vernetype: {prop_lower['vernetype']}")
    if prop_lower.get("vernestatus"):
        lines.append(f"  Vernestatus: {prop_lower['vernestatus']}")
    if prop_lower.get("datering") or prop_lower.get("kulturminnedatering"):
        lines.append(f"  Datering: {prop_lower.get('datering') or prop_lower.get('kulturminnedatering')}")
    if prop_lower.get("funksjon") or prop_lower.get("kulturminneopprinneligfunksjon"):
        lines.append(f"  Funksjon: {prop_lower.get('funksjon') or prop_lower.get('kulturminneopprinneligfunksjon')}")
    
    # Add link to kulturminnesok (ArcGIS uses 'linkKulturminnesok')
    link = prop_lower.get("linkkulturminnesok")
    if link:
        # Normalize HTTP to HTTPS
        if link.startswith("http://"):
            link = "https://" + link[7:]
        lines.append(f"  Lenke: {link}")
    
    # Add coordinates and distance if point geometry
    feature_lat, feature_lon = None, None
    
    if geometry.get("type") == "Point" and geometry.get("coordinates"):
        coords = geometry["coordinates"]
        if len(coords) >= 2:
            feature_lon, feature_lat = coords[0], coords[1]
            lines.append(f"  Koordinater: {feature_lat:.5f}, {feature_lon:.5f}")
    # Also handle Polygon centroid display
    elif geometry.get("type") == "Polygon" and geometry.get("coordinates"):
        coords = geometry["coordinates"][0][0] if geometry["coordinates"] else []
        if len(coords) >= 2:
            feature_lon, feature_lat = coords[0], coords[1]
            lines.append(f"  Koordinater: ~{feature_lat:.5f}, {feature_lon:.5f}")
    
    # Calculate and add distance from center point if provided
    if center_lat is not None and center_lon is not None and feature_lat is not None and feature_lon is not None:
        distance = _calculate_distance(center_lat, center_lon, feature_lat, feature_lon)
        if distance < 1000:
            lines.append(f"  Avstand: {distance:.0f} m")
        else:
            lines.append(f"  Avstand: {distance/1000:.1f} km")
    
    return "\n".join(lines)


async def services_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle arcgis-services tool call."""
    try:
        client = get_client()
        result = await client.list_services()

        services = result.get("services", [])

        lines = ["# Riksantikvaren ArcGIS Map Services\n"]
        lines.append(f"**Default service:** `{DEFAULT_SERVICE}` (layer {DEFAULT_LAYER})\n")
        
        # Add known services with descriptions
        for name, info in AVAILABLE_SERVICES.items():
            lines.append(f"## {name}")
            lines.append(f"{info['description']}\n")
            lines.append("**Layers:**")
            for layer_id, layer_name in info["layers"].items():
                default_marker = " ⭐" if name == DEFAULT_SERVICE and layer_id == DEFAULT_LAYER else ""
                lines.append(f"  - Layer {layer_id}: {layer_name}{default_marker}")
            lines.append("")
        
        # Add any additional services from API
        additional = [
            svc for svc in services 
            if svc.get("name", "").split("/")[-1] not in AVAILABLE_SERVICES
        ]
        if additional:
            lines.append("## Additional Services")
            for svc in additional:
                svc_name = svc.get("name", "").split("/")[-1]
                svc_type = svc.get("type", "Unknown")
                lines.append(f"- {svc_name} ({svc_type})")

        return [TextContent(text="\n".join(lines))]

    except Exception as e:
        logger.exception("ArcGIS services error")
        return [TextContent(text=f"Error listing services: {str(e)}")]


async def query_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle arcgis-query tool call."""
    service = arguments.get("service", DEFAULT_SERVICE)
    layer_id = arguments.get("layer_id", DEFAULT_LAYER)
    
    # Parse bbox if provided
    bbox = arguments.get("bbox")
    where = arguments.get("where", "1=1")
    limit = arguments.get("limit", 50)

    try:
        client = get_client()
        
        if bbox:
            if isinstance(bbox, str):
                parts = [float(x.strip()) for x in bbox.split(",")]
            else:
                parts = [float(x) for x in bbox]
            
            if len(parts) != 4:
                return [TextContent(text="Error: bbox must have 4 values (min_lon,min_lat,max_lon,max_lat)")]
            
            result = await client.query_bbox(
                service_name=service,
                layer_id=layer_id,
                min_lon=parts[0],
                min_lat=parts[1],
                max_lon=parts[2],
                max_lat=parts[3],
                limit=limit,
            )
        else:
            result = await client.query_layer(
                service_name=service,
                layer_id=layer_id,
                where=where,
                limit=limit,
            )

        features = result.get("features", [])
        if not features:
            return [TextContent(text=f"No features found in {service}/{layer_id}")]

        lines = [f"Found {len(features)} features in {service} (layer {layer_id}):\n"]
        for i, feature in enumerate(features[:20], 1):  # Limit display
            lines.append(f"{i}. {format_feature(feature, i)}")
            lines.append("")

        if len(features) > 20:
            lines.append(f"... and {len(features) - 20} more features")

        return [TextContent(text="\n".join(lines))]

    except Exception as e:
        logger.exception("ArcGIS query error")
        return [TextContent(text=f"Error querying features: {str(e)}")]


async def nearby_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle arcgis-nearby tool call.
    
    This tool queries official cultural heritage sites from Riksantikvaren/Askeladden.
    For user-contributed memories, use riksantikvaren-nearby with dataset='brukerminner'.
    """
    lat = arguments.get("latitude")
    lon = arguments.get("longitude")
    
    if lat is None or lon is None:
        return [TextContent(text="Error: 'latitude' and 'longitude' arguments are required")]

    service = arguments.get("service", DEFAULT_SERVICE)
    layer_id = arguments.get("layer_id", DEFAULT_LAYER)
    distance = arguments.get("distance", 1000)
    limit = arguments.get("limit", 20)

    try:
        client = get_client()
        result = await client.query_nearby(
            service_name=service,
            layer_id=layer_id,
            lat=lat,
            lon=lon,
            distance=distance,
            limit=limit,
        )

        features = result.get("features", [])
        if not features:
            return [TextContent(
                text=f"No official cultural heritage sites found within {distance}m of ({lat}, {lon})"
            )]

        lines = [f"Found {len(features)} official heritage sites within {distance}m of ({lat}, {lon}):\n"]
        for i, feature in enumerate(features, 1):
            # Pass center coordinates for distance calculation
            lines.append(f"{i}. {format_feature(feature, i, center_lat=lat, center_lon=lon)}")
            lines.append("")
        
        lines.append("---")
        lines.append("*Source: Riksantikvaren/Askeladden (official, verified cultural heritage database)*")

        return [TextContent(text="\n".join(lines))]

    except Exception as e:
        logger.exception("ArcGIS nearby error")
        return [TextContent(text=f"Error searching nearby: {str(e)}")]


def register_tools(registry: ToolRegistry) -> None:
    """Register Riksantikvaren ArcGIS tools with the registry."""

    registry.register(
        name="arcgis-services",
        description="List available Riksantikvaren ArcGIS map services and layers. Primary service is Kulturminner20180301 with 17 layers including buildings, monuments, and protection zones.",
        input_schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
        handler=services_handler,
    )

    registry.register(
        name="arcgis-query",
        description="Query cultural heritage features from Riksantikvaren ArcGIS REST API. Returns GeoJSON with detailed attributes including dating, category, protection status, and links to Askeladden.",
        input_schema={
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name (default: Kulturminner20180301)",
                    "default": "Kulturminner20180301",
                },
                "layer_id": {
                    "type": "integer",
                    "description": "Layer ID (default: 6 for Enkeltminner/single monuments)",
                    "default": 6,
                },
                "bbox": {
                    "type": "string",
                    "description": "Bounding box as 'min_lon,min_lat,max_lon,max_lat' (WGS84)",
                },
                "where": {
                    "type": "string",
                    "description": "SQL WHERE clause (e.g., \"kommune='Oslo'\")",
                    "default": "1=1",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum features to return",
                    "default": 50,
                },
            },
            "required": [],
        },
        handler=query_handler,
    )

    registry.register(
        name="arcgis-nearby",
        description="Find OFFICIAL cultural heritage sites near coordinates from Riksantikvaren/Askeladden database. Returns verified heritage sites (Viking finds, churches, burial mounds, rock carvings, etc.) with distances. For user-contributed memories and personal stories, use riksantikvaren-nearby with dataset='brukerminner' instead.",
        input_schema={
            "type": "object",
            "properties": {
                "latitude": {
                    "type": "number",
                    "description": "Latitude in decimal degrees",
                },
                "longitude": {
                    "type": "number",
                    "description": "Longitude in decimal degrees",
                },
                "distance": {
                    "type": "integer",
                    "description": "Search distance in meters (results will include calculated distance from center)",
                    "default": 1000,
                },
                "service": {
                    "type": "string",
                    "description": "Service name",
                    "default": "Kulturminner20180301",
                },
                "layer_id": {
                    "type": "integer",
                    "description": "Layer ID (6=Enkeltminner, 7=Lokaliteter)",
                    "default": 6,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 20,
                },
            },
            "required": ["latitude", "longitude"],
        },
        handler=nearby_handler,
    )

