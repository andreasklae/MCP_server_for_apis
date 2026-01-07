"""Riksantikvaren OGC API provider tools."""

import logging
from typing import Any

from src.mcp.models import TextContent
from src.mcp.registry import ToolRegistry
from src.tools.riksantikvaren_ogc.client import get_client

logger = logging.getLogger(__name__)


def format_feature(feature: dict[str, Any], index: int = 0) -> str:
    """Format a GeoJSON feature for display."""
    props = feature.get("properties", {})
    geometry = feature.get("geometry", {})
    
    # Try to get a name from various possible fields
    name = (
        props.get("navn") or 
        props.get("tittel") or 
        props.get("name") or 
        props.get("lokalitetsnavn") or
        f"Feature {feature.get('id', index)}"
    )
    
    lines = [f"**{name}**"]
    
    # Add key properties
    if props.get("kategori"):
        lines.append(f"  Kategori: {props['kategori']}")
    if props.get("kommune"):
        lines.append(f"  Kommune: {props['kommune']}")
    if props.get("fylke"):
        lines.append(f"  Fylke: {props['fylke']}")
    if props.get("vernestatus"):
        lines.append(f"  Vernestatus: {props['vernestatus']}")
    if props.get("datering"):
        lines.append(f"  Datering: {props['datering']}")
    if props.get("beskrivelse"):
        desc = props["beskrivelse"][:200] + "..." if len(props.get("beskrivelse", "")) > 200 else props.get("beskrivelse", "")
        lines.append(f"  Beskrivelse: {desc}")
    
    # Add coordinates if available
    if geometry.get("type") == "Point" and geometry.get("coordinates"):
        coords = geometry["coordinates"]
        lines.append(f"  Koordinater: {coords[1]:.5f}, {coords[0]:.5f}")
    
    # Add link if available
    if props.get("lenke"):
        lines.append(f"  Lenke: {props['lenke']}")
    
    return "\n".join(lines)


async def collections_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle riksantikvaren-collections tool call."""
    try:
        client = get_client()
        collections = await client.list_collections()

        if not collections:
            return [TextContent(text="No collections found")]

        lines = [f"Available Riksantikvaren data collections ({len(collections)}):\n"]
        for coll in collections:
            coll_id = coll.get("id", "unknown")
            title = coll.get("title", coll_id)
            desc = coll.get("description", "")
            lines.append(f"- **{coll_id}**: {title}")
            if desc:
                lines.append(f"  {desc[:100]}...")
            lines.append("")

        return [TextContent(text="\n".join(lines))]

    except Exception as e:
        logger.exception("Riksantikvaren collections error")
        return [TextContent(text=f"Error listing collections: {str(e)}")]


async def features_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle riksantikvaren-features tool call."""
    collection_id = arguments.get("collection", "kulturminner")
    limit = arguments.get("limit", 20)
    
    # Parse bbox if provided
    bbox = None
    if arguments.get("bbox"):
        try:
            bbox_str = arguments["bbox"]
            if isinstance(bbox_str, str):
                parts = [float(x.strip()) for x in bbox_str.split(",")]
                if len(parts) == 4:
                    bbox = tuple(parts)
            elif isinstance(bbox_str, (list, tuple)) and len(bbox_str) == 4:
                bbox = tuple(float(x) for x in bbox_str)
        except Exception:
            return [TextContent(text="Error: Invalid bbox format. Use 'min_lon,min_lat,max_lon,max_lat'")]

    try:
        client = get_client()
        result = await client.get_features(collection_id, bbox=bbox, limit=limit)

        features = result.get("features", [])
        total = result.get("numberMatched", len(features))

        if not features:
            return [TextContent(text=f"No features found in collection '{collection_id}'")]

        lines = [f"Found {total} features in '{collection_id}' (showing {len(features)}):\n"]
        for i, feature in enumerate(features, 1):
            lines.append(f"{i}. {format_feature(feature, i)}")
            lines.append("")

        return [TextContent(text="\n".join(lines))]

    except Exception as e:
        logger.exception("Riksantikvaren features error")
        return [TextContent(text=f"Error querying features: {str(e)}")]


async def feature_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle riksantikvaren-feature tool call."""
    collection_id = arguments.get("collection", "kulturminner")
    feature_id = arguments.get("feature_id", "")
    
    if not feature_id:
        return [TextContent(text="Error: 'feature_id' argument is required")]

    try:
        client = get_client()
        feature = await client.get_feature(collection_id, feature_id)

        if not feature:
            return [TextContent(text=f"Feature not found: {feature_id}")]

        # Format the feature with all properties
        props = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        
        name = props.get("navn") or props.get("tittel") or f"Feature {feature_id}"
        lines = [f"# {name}\n"]
        
        # Add all properties
        for key, value in props.items():
            if value and key not in ["id"]:
                lines.append(f"**{key}:** {value}")
        
        # Add geometry info
        if geometry:
            lines.append(f"\n**Geometry type:** {geometry.get('type', 'Unknown')}")
            if geometry.get("type") == "Point" and geometry.get("coordinates"):
                coords = geometry["coordinates"]
                lines.append(f"**Coordinates:** {coords[1]:.6f}, {coords[0]:.6f}")

        return [TextContent(text="\n".join(lines))]

    except Exception as e:
        logger.exception("Riksantikvaren feature error")
        return [TextContent(text=f"Error fetching feature: {str(e)}")]


async def nearby_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle riksantikvaren-nearby tool call."""
    lat = arguments.get("latitude")
    lon = arguments.get("longitude")
    
    if lat is None or lon is None:
        return [TextContent(text="Error: 'latitude' and 'longitude' arguments are required")]

    collection_id = arguments.get("collection", "kulturminner")
    radius = arguments.get("radius", 1000)  # meters
    limit = arguments.get("limit", 20)
    
    # Convert radius in meters to approximate degrees
    # At 60°N latitude: 1 degree ≈ 55.8 km longitude, 111 km latitude
    radius_deg = radius / 111000  # rough approximation

    try:
        client = get_client()
        result = await client.search_nearby(
            lat, lon, radius_deg=radius_deg, 
            collection_id=collection_id, limit=limit
        )

        features = result.get("features", [])

        if not features:
            return [TextContent(
                text=f"No cultural heritage sites found within {radius}m of ({lat}, {lon})"
            )]

        lines = [f"Found {len(features)} cultural heritage sites near ({lat}, {lon}):\n"]
        for i, feature in enumerate(features, 1):
            lines.append(f"{i}. {format_feature(feature, i)}")
            lines.append("")

        return [TextContent(text="\n".join(lines))]

    except Exception as e:
        logger.exception("Riksantikvaren nearby error")
        return [TextContent(text=f"Error searching nearby: {str(e)}")]


def register_tools(registry: ToolRegistry) -> None:
    """Register Riksantikvaren OGC tools with the registry."""

    registry.register(
        name="riksantikvaren-collections",
        description="List available data collections from Riksantikvaren (Norwegian cultural heritage). Collections include 'kulturminner' (heritage sites) and 'brukeminner' (user-contributed).",
        input_schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
        handler=collections_handler,
    )

    registry.register(
        name="riksantikvaren-features",
        description="Query cultural heritage features from Riksantikvaren. Can filter by bounding box.",
        input_schema={
            "type": "object",
            "properties": {
                "collection": {
                    "type": "string",
                    "description": "Collection ID (e.g., 'kulturminner', 'brukeminner')",
                    "default": "kulturminner",
                },
                "bbox": {
                    "type": "string",
                    "description": "Bounding box as 'min_lon,min_lat,max_lon,max_lat' (WGS84)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum features to return",
                    "default": 20,
                },
            },
            "required": [],
        },
        handler=features_handler,
    )

    registry.register(
        name="riksantikvaren-feature",
        description="Get detailed information about a specific cultural heritage feature by ID.",
        input_schema={
            "type": "object",
            "properties": {
                "feature_id": {
                    "type": "string",
                    "description": "Feature ID",
                },
                "collection": {
                    "type": "string",
                    "description": "Collection ID",
                    "default": "kulturminner",
                },
            },
            "required": ["feature_id"],
        },
        handler=feature_handler,
    )

    registry.register(
        name="riksantikvaren-nearby",
        description="Find cultural heritage sites near geographic coordinates. Returns sites from Riksantikvaren's Askeladden database.",
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
                "radius": {
                    "type": "integer",
                    "description": "Search radius in meters",
                    "default": 1000,
                },
                "collection": {
                    "type": "string",
                    "description": "Collection ID",
                    "default": "kulturminner",
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

