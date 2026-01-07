"""SNL provider tools."""

import logging
from typing import Any

from src.mcp.models import TextContent
from src.mcp.registry import ToolRegistry
from src.tools.snl.client import get_client

logger = logging.getLogger(__name__)


async def search_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle snl-search tool call."""
    query = arguments.get("query", "")
    if not query:
        return [TextContent(text="Error: 'query' argument is required")]

    limit = arguments.get("limit", 10)

    try:
        client = get_client()
        results = await client.search(query, limit=limit)

        if not results:
            return [TextContent(text=f"No SNL articles found for: {query}")]

        lines = [f"Found {len(results)} articles in Store norske leksikon for '{query}':\n"]
        for i, result in enumerate(results, 1):
            title = result.get("headword") or result.get("title", "Unknown")
            snippet = result.get("snippet") or result.get("first_two_sentences", "")
            url = result.get("article_url") or result.get("permalink", "")

            lines.append(f"{i}. **{title}**")
            if snippet:
                # Clean up HTML if present
                snippet = snippet.replace("<b>", "").replace("</b>", "")
                lines.append(f"   {snippet}")
            if url:
                lines.append(f"   {url}")
            lines.append("")

        return [TextContent(text="\n".join(lines))]

    except Exception as e:
        logger.exception("SNL search error")
        return [TextContent(text=f"Error searching SNL: {str(e)}")]


async def article_handler(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle snl-article tool call."""
    identifier = arguments.get("identifier", "")
    if not identifier:
        return [TextContent(text="Error: 'identifier' argument is required (article ID or slug)")]

    try:
        client = get_client()
        article = await client.get_article(identifier)

        if not article:
            return [TextContent(text=f"Article not found: {identifier}")]

        # Extract article information
        title = article.get("headword", identifier)
        body = article.get("plain_text_body") or article.get("xhtml_body", "No content available")
        
        # Clean HTML from body if it's HTML
        if "<" in body:
            # Simple HTML cleanup - remove common tags
            import re
            body = re.sub(r'<[^>]+>', '', body)
            body = body.replace('&nbsp;', ' ').replace('&amp;', '&')
        
        # Truncate if very long
        if len(body) > 3000:
            body = body[:3000] + "... [truncated]"

        url = article.get("article_url") or article.get("permalink", "")
        authors = article.get("authors", [])
        author_names = ", ".join(a.get("full_name", "") for a in authors if a.get("full_name"))
        license_name = article.get("license_name", "")
        changed_at = article.get("changed_at", "")

        lines = [f"# {title}\n"]
        lines.append(body)
        lines.append("")
        
        if author_names:
            lines.append(f"**Forfatter(e):** {author_names}")
        if changed_at:
            lines.append(f"**Sist oppdatert:** {changed_at[:10]}")
        if license_name:
            lines.append(f"**Lisens:** {license_name}")
        if url:
            lines.append(f"**Kilde:** {url}")

        return [TextContent(text="\n".join(lines))]

    except Exception as e:
        logger.exception("SNL article error")
        return [TextContent(text=f"Error fetching SNL article: {str(e)}")]


def register_tools(registry: ToolRegistry) -> None:
    """Register SNL tools with the registry."""

    registry.register(
        name="snl-search",
        description="Search Store norske leksikon (Norwegian encyclopedia) for articles. Returns titles and previews.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term in Norwegian",
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
        name="snl-article",
        description="Get a full article from Store norske leksikon by ID or URL slug. Provides authoritative Norwegian-language content.",
        input_schema={
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": "Article ID (numeric) or URL slug (e.g., 'Oslo' or 'Edvard_Munch')",
                },
            },
            "required": ["identifier"],
        },
        handler=article_handler,
    )

