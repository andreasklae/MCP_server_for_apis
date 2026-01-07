"""Wikipedia provider tools."""

import logging
from typing import Any

from src.mcp.models import TextContent
from src.mcp.registry import ToolRegistry
from src.tools.wikipedia.client import get_client

logger = logging.getLogger(__name__)


async def search_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle wikipedia-search tool call."""
    query = arguments.get("query", "")
    if not query:
        return [TextContent(text="Error: 'query' argument is required")]

    language = arguments.get("language", "no")
    limit = arguments.get("limit", 10)

    try:
        client = get_client(language)
        results = await client.search(query, limit=limit)

        if not results:
            return [TextContent(text=f"No Wikipedia articles found for: {query}")]

        lines = [f"Found {len(results)} Wikipedia articles for '{query}':\n"]
        for i, result in enumerate(results, 1):
            title = result.get("title", "Unknown")
            snippet = result.get("snippet", "").replace("<span class=\"searchmatch\">", "").replace("</span>", "")
            lines.append(f"{i}. **{title}**")
            if snippet:
                lines.append(f"   {snippet}...")
            lines.append("")

        return [TextContent(text="\n".join(lines))]

    except Exception as e:
        logger.exception("Wikipedia search error")
        return [TextContent(text=f"Error searching Wikipedia: {str(e)}")]


async def summary_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle wikipedia-summary tool call."""
    title = arguments.get("title", "")
    if not title:
        return [TextContent(text="Error: 'title' argument is required")]

    language = arguments.get("language", "no")

    try:
        client = get_client(language)
        result = await client.get_summary(title)

        if "error" in result:
            return [TextContent(text=f"Article not found: {title}")]

        article_title = result.get("title", title)
        extract = result.get("extract", "No content available")
        url = result.get("fullurl", f"https://{language}.wikipedia.org/wiki/{title.replace(' ', '_')}")

        text = f"# {article_title}\n\n{extract}\n\n**Source:** {url}"
        return [TextContent(text=text)]

    except Exception as e:
        logger.exception("Wikipedia summary error")
        return [TextContent(text=f"Error fetching Wikipedia article: {str(e)}")]


async def geosearch_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle wikipedia-geosearch tool call."""
    lat = arguments.get("latitude")
    lon = arguments.get("longitude")

    if lat is None or lon is None:
        return [TextContent(text="Error: 'latitude' and 'longitude' arguments are required")]

    language = arguments.get("language", "no")
    radius = arguments.get("radius", 1000)
    limit = arguments.get("limit", 10)

    try:
        client = get_client(language)
        results = await client.geosearch(lat, lon, radius=radius, limit=limit)

        if not results:
            return [TextContent(text=f"No Wikipedia articles found within {radius}m of ({lat}, {lon})")]

        lines = [f"Found {len(results)} Wikipedia articles near ({lat}, {lon}):\n"]
        for i, result in enumerate(results, 1):
            title = result.get("title", "Unknown")
            dist = result.get("dist", 0)
            page_id = result.get("pageid", "")
            url = f"https://{language}.wikipedia.org/?curid={page_id}"
            lines.append(f"{i}. **{title}** ({dist:.0f}m away)")
            lines.append(f"   {url}")
            lines.append("")

        return [TextContent(text="\n".join(lines))]

    except Exception as e:
        logger.exception("Wikipedia geosearch error")
        return [TextContent(text=f"Error searching nearby articles: {str(e)}")]


def register_tools(registry: ToolRegistry) -> None:
    """Register Wikipedia tools with the registry."""

    registry.register(
        name="wikipedia-search",
        description="Search Wikipedia for articles matching a query. Returns article titles and snippets.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "language": {
                    "type": "string",
                    "description": "Wikipedia language code (e.g., 'no' for Norwegian, 'en' for English)",
                    "default": "no",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
        handler=search_handler,
    )

    registry.register(
        name="wikipedia-summary",
        description="Get a summary/extract of a Wikipedia article by title.",
        input_schema={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Article title (exact match)",
                },
                "language": {
                    "type": "string",
                    "description": "Wikipedia language code",
                    "default": "no",
                },
            },
            "required": ["title"],
        },
        handler=summary_handler,
    )

    registry.register(
        name="wikipedia-geosearch",
        description="Find Wikipedia articles near geographic coordinates. Useful for finding information about landmarks and places.",
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
                    "description": "Search radius in meters (max 10000)",
                    "default": 1000,
                },
                "language": {
                    "type": "string",
                    "description": "Wikipedia language code",
                    "default": "no",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 10,
                },
            },
            "required": ["latitude", "longitude"],
        },
        handler=geosearch_handler,
    )

