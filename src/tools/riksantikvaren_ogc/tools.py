"""Riksantikvaren OGC API provider tools."""

import logging
import math
from typing import Any

from src.mcp.models import TextContent
from src.mcp.registry import ToolRegistry
from src.tools.riksantikvaren_ogc.client import get_client, AVAILABLE_DATASETS

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
    props = feature.get("properties", {}) or {}
    geometry = feature.get("geometry", {}) or {}
    
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
    if props.get("kulturminneKategori"):
        lines.append(f"  Kategori: {props['kulturminneKategori']}")
    if props.get("enkeltminnekategori"):
        lines.append(f"  Kategori: {props['enkeltminnekategori']}")
    if props.get("kommune"):
        lines.append(f"  Kommune: {props['kommune']}")
    if props.get("fylke"):
        lines.append(f"  Fylke: {props['fylke']}")
    if props.get("vernestatus"):
        lines.append(f"  Vernestatus: {props['vernestatus']}")
    if props.get("vernetype"):
        lines.append(f"  Vernetype: {props['vernetype']}")
    if props.get("datering"):
        lines.append(f"  Datering: {props['datering']}")
    if props.get("kulturminneDatering"):
        lines.append(f"  Datering: {props['kulturminneDatering']}")
    if props.get("beskrivelse"):
        desc = props["beskrivelse"][:200] + "..." if len(props.get("beskrivelse", "")) > 200 else props.get("beskrivelse", "")
        lines.append(f"  Beskrivelse: {desc}")
    
    # Get feature ID - try multiple property names (API uses different casings)
    feature_id = feature.get("id")
    if feature_id:
        lines.append(f"  ID: {feature_id}")
    
    # Get lokalitet ID - API uses 'lokalitetid' (lowercase)
    lokalitet_id = props.get("lokalitetid") or props.get("lokalitetId") or props.get("lokalId")
    
    # Get link to kulturminnesøk - API uses Norwegian 'ø' character!
    # kulturminner: "linkKulturminnesøk" (with ø)
    # brukerminner: "linkkulturminnesok" (all lowercase, no ø)
    link = (
        props.get("linkKulturminnesøk") or  # kulturminner (with Norwegian ø)
        props.get("linkKulturminnesok") or  # fallback without ø
        props.get("linkkulturminnesok") or  # brukerminner (all lowercase)
        props.get("lenke")
    )
    
    if link:
        # Normalize HTTP to HTTPS
        if link.startswith("http://"):
            link = "https://" + link[7:]
        lines.append(f"  Lenke: {link}")
    elif lokalitet_id:
        # Fallback: construct URL using /ra/lokalitet/ format (redirects correctly)
        lines.append(f"  Lenke: https://kulturminnesok.no/ra/lokalitet/{lokalitet_id}")
    elif feature_id:
        # Last resort: use feature_id directly (works for brukerminner UUIDs)
        lines.append(f"  Lenke: https://www.kulturminnesok.no/kart/?id={feature_id}")
    
    # Add coordinates and distance if available
    feature_lat, feature_lon = None, None
    
    if geometry.get("type") == "Point" and geometry.get("coordinates"):
        coords = geometry["coordinates"]
        if coords and len(coords) >= 2:
            feature_lon, feature_lat = coords[0], coords[1]
            lines.append(f"  Koordinater: {feature_lat:.5f}, {feature_lon:.5f}")
    # Also check for gpsposisjon property (brukerminner uses this)
    elif props.get("gpsposisjon"):
        gps = props["gpsposisjon"]
        lines.append(f"  Koordinater: {gps}")
        # Parse gpsposisjon format: "lat, lon"
        try:
            parts = [float(x.strip()) for x in gps.split(",")]
            if len(parts) == 2:
                feature_lat, feature_lon = parts[0], parts[1]
        except (ValueError, AttributeError):
            pass
    
    # Calculate and add distance from center point if provided
    if center_lat is not None and center_lon is not None and feature_lat is not None and feature_lon is not None:
        distance = _calculate_distance(center_lat, center_lon, feature_lat, feature_lon)
        if distance < 1000:
            lines.append(f"  Avstand: {distance:.0f} m")
        else:
            lines.append(f"  Avstand: {distance/1000:.1f} km")
    
    return "\n".join(lines)


async def datasets_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle riksantikvaren-datasets tool call."""
    try:
        client = get_client()
        datasets = await client.list_datasets()

        if not datasets:
            return [TextContent(text="No datasets found")]

        lines = ["# Available Riksantikvaren Datasets\n"]
        lines.append("The Riksantikvaren OGC API provides several datasets:\n")
        
        for ds in datasets:
            ds_id = ds.get("id", "unknown")
            title = ds.get("title", ds_id)
            lines.append(f"## {title}")
            lines.append(f"- **ID:** `{ds_id}`")
            lines.append(f"- **URL:** {ds.get('landingPageUri', 'N/A')}")
            lines.append("")

        lines.append("\nUse `riksantikvaren-collections` with a dataset to see its collections.")
        return [TextContent(text="\n".join(lines))]

    except Exception as e:
        logger.exception("Riksantikvaren datasets error")
        return [TextContent(text=f"Error listing datasets: {str(e)}")]


async def collections_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle riksantikvaren-collections tool call."""
    dataset_id = arguments.get("dataset", "kulturminner")
    
    try:
        client = get_client()
        collections = await client.list_collections(dataset_id=dataset_id)

        if not collections:
            return [TextContent(text=f"No collections found in dataset '{dataset_id}'")]

        lines = [f"# Collections in '{dataset_id}' ({len(collections)}):\n"]
        for coll in collections:
            coll_id = coll.get("id", "unknown")
            title = coll.get("title", coll_id)
            desc = coll.get("description", "")
            lines.append(f"## {title}")
            lines.append(f"- **ID:** `{coll_id}`")
            if desc:
                lines.append(f"- **Description:** {desc[:200]}...")
            lines.append("")

        return [TextContent(text="\n".join(lines))]

    except Exception as e:
        logger.exception("Riksantikvaren collections error")
        return [TextContent(text=f"Error listing collections: {str(e)}")]


async def features_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle riksantikvaren-features tool call."""
    dataset_id = arguments.get("dataset", "kulturminner")
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
        result = await client.get_features(
            dataset_id=dataset_id,
            collection_id=collection_id,
            bbox=bbox,
            limit=limit,
        )

        features = result.get("features", [])
        total = result.get("numberMatched", len(features))

        if not features:
            return [TextContent(text=f"No features found in '{dataset_id}/{collection_id}'")]

        lines = [f"Found {total} cultural heritage sites in '{collection_id}' (showing {len(features)}):\n"]
        for i, feature in enumerate(features, 1):
            lines.append(f"{i}. {format_feature(feature, i)}")
            lines.append("")

        return [TextContent(text="\n".join(lines))]

    except Exception as e:
        logger.exception("Riksantikvaren features error")
        return [TextContent(text=f"Error querying features: {str(e)}")]


async def feature_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle riksantikvaren-feature tool call."""
    dataset_id = arguments.get("dataset", "kulturminner")
    collection_id = arguments.get("collection", "kulturminner")
    feature_id = arguments.get("feature_id", "")
    
    if not feature_id:
        return [TextContent(text="Error: 'feature_id' argument is required")]

    try:
        client = get_client()
        feature = await client.get_feature(
            feature_id=feature_id,
            dataset_id=dataset_id,
            collection_id=collection_id,
        )

        if not feature:
            return [TextContent(text=f"Feature not found: {feature_id}")]

        # Format the feature with all properties
        props = feature.get("properties", {}) or {}
        geometry = feature.get("geometry", {}) or {}
        
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
                if coords and len(coords) >= 2:
                    lines.append(f"**Coordinates:** {coords[1]:.6f}, {coords[0]:.6f}")

        return [TextContent(text="\n".join(lines))]

    except Exception as e:
        logger.exception("Riksantikvaren feature error")
        return [TextContent(text=f"Error fetching feature: {str(e)}")]


async def nearby_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle riksantikvaren-nearby tool call.
    
    NOTE: This tool only works reliably for 'brukerminner' dataset.
    For 'kulturminner', use the ArcGIS 'arcgis-nearby' tool instead.
    """
    lat = arguments.get("latitude")
    lon = arguments.get("longitude")
    
    if lat is None or lon is None:
        return [TextContent(text="Error: 'latitude' and 'longitude' arguments are required")]

    dataset_id = arguments.get("dataset", "brukerminner")  # Default to brukerminner
    collection_id = arguments.get("collection", dataset_id)  # Match collection to dataset
    radius = arguments.get("radius", 2000)  # Default 2000m for brukerminner (sparse data)
    limit = arguments.get("limit", 20)
    
    # Warn if using kulturminner (bbox doesn't work for this dataset)
    if dataset_id == "kulturminner":
        logger.warning("riksantikvaren-nearby called for kulturminner - bbox filtering may not work. Use arcgis-nearby instead.")
    
    # Convert radius in meters to approximate degrees
    # At 60°N latitude: 1 degree ≈ 55.8 km longitude, 111 km latitude
    radius_deg = radius / 111000  # rough approximation

    try:
        client = get_client()
        result = await client.search_nearby(
            lat=lat,
            lon=lon,
            radius_deg=radius_deg, 
            dataset_id=dataset_id,
            collection_id=collection_id,
            limit=limit,
        )

        features = result.get("features", [])

        if not features:
            return [TextContent(
                text=f"No {'user memories' if dataset_id == 'brukerminner' else 'sites'} found within {radius}m of ({lat}, {lon})"
            )]

        source_type = "user memories (brukerminner)" if dataset_id == "brukerminner" else "cultural heritage sites"
        lines = [f"Found {len(features)} {source_type} near ({lat}, {lon}):\n"]
        
        for i, feature in enumerate(features, 1):
            # Pass center coordinates for distance calculation
            lines.append(f"{i}. {format_feature(feature, i, center_lat=lat, center_lon=lon)}")
            lines.append("")
        
        # Add source attribution
        if dataset_id == "brukerminner":
            lines.append("---")
            lines.append("*Source: Brukerminner (user-contributed memories, not officially verified)*")

        return [TextContent(text="\n".join(lines))]

    except Exception as e:
        logger.exception("Riksantikvaren nearby error")
        return [TextContent(text=f"Error searching nearby: {str(e)}")]


def register_tools(registry: ToolRegistry) -> None:
    """Register Riksantikvaren OGC tools with the registry."""

    registry.register(
        name="riksantikvaren-datasets",
        description="List available datasets from Riksantikvaren OGC API. Datasets include kulturminner (heritage sites), kulturmiljoer (environments), brukerminner (user memories), and more.",
        input_schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
        handler=datasets_handler,
    )

    registry.register(
        name="riksantikvaren-collections",
        description="List collections within a Riksantikvaren dataset. Default dataset is 'kulturminner'.",
        input_schema={
            "type": "object",
            "properties": {
                "dataset": {
                    "type": "string",
                    "description": "Dataset ID (e.g., 'kulturminner', 'kulturmiljoer', 'brukerminner')",
                    "default": "kulturminner",
                },
            },
            "required": [],
        },
        handler=collections_handler,
    )

    registry.register(
        name="riksantikvaren-features",
        description="Query cultural heritage features from Riksantikvaren. Supports: 'kulturminner' (official heritage sites from Askeladden database), 'brukerminner' (user-contributed personal memories - NOT officially verified), 'kulturmiljoer' (protected environments). NOTE: bbox filtering only works for 'brukerminner'. For location-based kulturminner queries, use 'arcgis-nearby' instead.",
        input_schema={
            "type": "object",
            "properties": {
                "dataset": {
                    "type": "string",
                    "description": "Dataset: 'kulturminner' (official, verified sites), 'brukerminner' (user memories - unverified), 'kulturmiljoer' (environments)",
                    "default": "kulturminner",
                },
                "collection": {
                    "type": "string",
                    "description": "Collection ID within the dataset",
                    "default": "kulturminner",
                },
                "bbox": {
                    "type": "string",
                    "description": "Bounding box as 'min_lon,min_lat,max_lon,max_lat' (WGS84). NOTE: Only works for brukerminner!",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum features to return (max 100)",
                    "default": 20,
                },
            },
            "required": [],
        },
        handler=features_handler,
    )

    registry.register(
        name="riksantikvaren-feature",
        description="Get detailed information about a specific cultural heritage site by its ID.",
        input_schema={
            "type": "object",
            "properties": {
                "feature_id": {
                    "type": "string",
                    "description": "Feature ID",
                },
                "dataset": {
                    "type": "string",
                    "description": "Dataset ID",
                    "default": "kulturminner",
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
        description="Find user-contributed memories (brukerminner) near coordinates. Returns personal stories and memories from the public (NOT officially verified data). For official cultural heritage sites, use 'arcgis-nearby' instead. Use radius 2000-5000m as brukerminner data is sparse.",
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
                    "description": "Search radius in meters. Use 2000-5000m for brukerminner (sparse data)",
                    "default": 2000,
                },
                "dataset": {
                    "type": "string",
                    "description": "Dataset: 'brukerminner' (user memories - RECOMMENDED), 'kulturminner' (broken spatial filter - use arcgis-nearby instead)",
                    "default": "brukerminner",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (max 100)",
                    "default": 20,
                },
            },
            "required": ["latitude", "longitude"],
        },
        handler=nearby_handler,
    )

