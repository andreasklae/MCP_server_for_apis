"""Agent runner that uses OpenAI with MCP tools - with SSE streaming support."""

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator

from openai import OpenAI, AzureOpenAI
from pydantic import BaseModel, Field

from src.mcp.registry import get_registry
from src.config.loader import get_settings

logger = logging.getLogger(__name__)


# =============================================================================
# Request/Response Models
# =============================================================================


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    
    message: str = Field(..., description="User message")
    sources: list[str] = Field(
        default=["wikipedia", "snl", "riksantikvaren"],
        description="Enabled sources: wikipedia, snl, riksantikvaren"
    )
    conversation_history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Previous messages in the conversation"
    )


class SourceReference(BaseModel):
    """A reference to a source used in the response."""
    
    title: str = Field(..., description="Title of the source")
    url: str = Field(..., description="URL to the source")
    provider: str = Field(..., description="Provider name: wikipedia, snl, riksantikvaren")
    snippet: str | None = Field(None, description="Short preview of the content")


class Location(BaseModel):
    """A geographic location mentioned in the response."""
    
    name: str = Field(..., description="Name of the location")
    lat: float = Field(..., description="Latitude")
    lng: float = Field(..., description="Longitude")
    type: str = Field(default="heritage_site", description="Type of location")


class ResponseContent(BaseModel):
    """The main response content."""
    
    text: str = Field(..., description="Main response text in Markdown format")
    summary: str | None = Field(None, description="One-sentence summary")


class ChatResponseMetadata(BaseModel):
    """Metadata about the chat response."""
    
    tools_used: list[str] = Field(default_factory=list)
    providers_consulted: list[str] = Field(default_factory=list)
    processing_time_ms: int = Field(default=0)
    model: str = Field(default="gpt-4o")


class ChatResponse(BaseModel):
    """Structured response model for chat endpoint."""
    
    response: ResponseContent
    sources: list[SourceReference] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    related_queries: list[str] = Field(default_factory=list)
    metadata: ChatResponseMetadata = Field(default_factory=ChatResponseMetadata)


# =============================================================================
# SSE Event Models
# =============================================================================


class SSEEvent(BaseModel):
    """Base class for SSE events."""
    type: str


class StatusEvent(SSEEvent):
    """Status update event."""
    type: str = "status"
    message: str


class ToolStartEvent(SSEEvent):
    """Tool execution started."""
    type: str = "tool_start"
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolEndEvent(SSEEvent):
    """Tool execution completed."""
    type: str = "tool_end"
    tool: str
    success: bool
    preview: str | None = None


class TokenEvent(SSEEvent):
    """Token from streaming response."""
    type: str = "token"
    content: str


class DoneEvent(SSEEvent):
    """Final response with full structured data."""
    type: str = "done"
    response: ChatResponse


class ErrorEvent(SSEEvent):
    """Error event."""
    type: str = "error"
    message: str


# =============================================================================
# Configuration
# =============================================================================


# Map source names to tool prefixes
SOURCE_TOOL_MAP = {
    "wikipedia": ["wikipedia-"],
    "snl": ["snl-"],
    "riksantikvaren": ["riksantikvaren-", "arcgis-"],
}

# System prompt for the agent - instructs to use Markdown (sources/related questions handled separately)
SYSTEM_PROMPT = """
You are a knowledgeable tour guide. You help users discover and learn about historical sites, monuments, buildings, and cultural landmarks.

## Available Data Sources

- **Wikipedia**: General encyclopedic knowledge in Norwegian and English
- **Store norske leksikon (SNL)**: Authoritative Norwegian encyclopedia
- **Riksantikvaren/Askeladden**: Official Norwegian cultural heritage database with 600,000+ registered sites
- **Brukerminner**: User-contributed personal memories and stories (not officially verified)

## Tool Usage Strategy

**IMPORTANT: Gather MORE data than you think you need!**

Tools run in parallel, so calling multiple tools is fast. When in doubt:
- Call multiple sources simultaneously (SNL + Wikipedia + Riksantikvaren)
- You may use the same tool more than once (with different parameters) if the answer is not satisfactory.
- Use broader search parameters initially
- It's better to have too much information than too little

After gathering data, you can decide what's relevant for your response. Not all gathered information needs to be included - only use what's actually helpful for answering the user's question.

## Tool Selection Guide

**Always use multiple tools** - they run in parallel so there's no performance cost:
- **SNL + Wikipedia**: Essential for general knowledge about landmarks, buildings, castles, etc.
- **arcgis-nearby**: For officially registered heritage sites (kulturminner) in Riksantikvaren database
- **riksantikvaren-nearby**: For user-contributed memories (brukerminner) - use larger radius (2000-5000m) as data is sparse

**Important**: Not all historical buildings are in Riksantikvaren. Famous landmarks like the Royal Palace, Akershus Fortress, etc. may NOT be registered as "kulturminner" but are well documented in SNL and Wikipedia.

For location-based queries about landmarks, castles, or historical buildings:
1. **ALWAYS** search SNL and Wikipedia first for general information
2. **Then** use arcgis-nearby to check for nearby registered heritage sites
3. Synthesize all results - don't just report what's in Riksantikvaren

## Response Guidelines

1. **Gather broadly, synthesize smartly**: Call multiple tools (SNL + Wikipedia + Riksantikvaren), then combine the best information into a coherent answer
2. **Prioritize informative content**: If SNL/Wikipedia have good information, use it! Don't dismiss results just because they're not from Riksantikvaren
3. **Never say "I found nothing" if any source has information**: If Wikipedia or SNL has relevant content, that IS useful information
4. Prefer Norwegian sources (SNL, Riksantikvaren) for Norwegian cultural heritage when available
5. Only mention source distinctions when actually relevant - focus on answering the user's question

## Markdown Formatting Rules

Format all responses as clean markdown following these rules:

1. **NUMBERED LISTS**: Always use flat format. Write each item on a single line like "1. **Title**: Description text". Never use nested bullet points within numbered lists.
   - GOOD: `1. **Urnes stavkirke**: Urnes stavkirke er den eldste stavkirken i Norge...`
   - BAD: `1. **Urnes stavkirke**\n   - Urnes stavkirke er den eldste...`

2. **SOURCE LINKS**: Do NOT include source links or URLs in the response text. Sources are provided separately in the API response. Never write "[Les mer](url)" or similar.

3. **BULLET LISTS**: Keep bullet lists flat. Avoid nested bullets. If you need to add detail to a bullet point, include it on the same line after a colon.

4. **PARAGRAPHS**: Use single blank lines between paragraphs. Do not use multiple consecutive blank lines.

5. **HEADERS**: Use headers sparingly. When needed, use only ## level headers for section titles. Do not mix multiple header levels (avoid ###, ####) in one response.

## Language

**Always respond in the same language as the user's question**, regardless of what language the source material is in. Translate and synthesize information from sources as needed.

## Values

1. Being creative and entertaining for the user
2. Basing your answers on the sources you have access to
3. Being honest about the validity and reliability of your sources
"""


# =============================================================================
# Agent Runner
# =============================================================================


class AgentRunner:
    """Runs the chat agent with tool calling and streaming support."""
    
    def __init__(self, openai_api_key: str):
        """Initialize with OpenAI API key (works with both OpenAI and Azure OpenAI)."""
        settings = get_settings()
        
        if settings.use_azure_openai:
            logger.info(f"Using Azure OpenAI: {settings.azure_openai_endpoint}")
            self.client = AzureOpenAI(
                api_key=openai_api_key,
                api_version=settings.azure_openai_api_version,
                azure_endpoint=settings.azure_openai_endpoint,
            )
            self.model = settings.azure_openai_deployment
        else:
            logger.info("Using OpenAI direct API")
            self.client = OpenAI(api_key=openai_api_key)
            self.model = "gpt-4o"
        
        self.registry = get_registry()
    
    def _get_enabled_tools(self, sources: list[str]) -> list[dict[str, Any]]:
        """Get OpenAI tool definitions for enabled sources."""
        tools = []
        enabled_prefixes = []
        
        for source in sources:
            if source in SOURCE_TOOL_MAP:
                enabled_prefixes.extend(SOURCE_TOOL_MAP[source])
        
        for mcp_tool in self.registry.list_tools():
            if any(mcp_tool.name.startswith(prefix) for prefix in enabled_prefixes):
                tools.append({
                    "type": "function",
                    "function": {
                        "name": mcp_tool.name,
                        "description": mcp_tool.description,
                        "parameters": mcp_tool.inputSchema,
                    }
                })
        
        return tools
    
    async def _execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool and return the result as a string."""
        try:
            tool = self.registry.get(tool_name)
            if not tool:
                return json.dumps({"error": f"Tool '{tool_name}' not found"})
            
            result = await tool.handler(arguments)
            
            if isinstance(result, list):
                texts = []
                for item in result:
                    if hasattr(item, 'text'):
                        texts.append(item.text)
                    elif hasattr(item, 'model_dump'):
                        texts.append(json.dumps(item.model_dump(), ensure_ascii=False))
                    else:
                        texts.append(str(item))
                return "\n".join(texts)
            elif hasattr(result, 'text'):
                return result.text
            elif hasattr(result, 'model_dump'):
                return json.dumps(result.model_dump(), ensure_ascii=False, indent=2)
            elif isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False, indent=2)
            else:
                return str(result)
                
        except Exception as e:
            logger.error(f"Tool execution error: {tool_name}", exc_info=True)
            return json.dumps({"error": str(e)})
    
    def _extract_sources_from_tool_results(
        self, 
        tool_results: list[tuple[str, str, dict[str, Any]]],
        response_text: str
    ) -> list[SourceReference]:
        """Extract source references from tool results that are actually used in the response.
        
        Only includes sources whose content appears to be referenced in the AI's response.
        This prevents listing sources that were consulted but not used.
        """
        import re
        
        # Normalize response text for matching
        response_lower = response_text.lower()
        
        sources = []
        seen_urls = set()
        
        for tool_name, result_text, arguments in tool_results:
            # Determine provider
            provider = "riksantikvaren"
            if tool_name.startswith("wikipedia-"):
                provider = "wikipedia"
            elif tool_name.startswith("snl-"):
                provider = "snl"
            
            # Check if this tool's content was actually used in the response
            # We look for key terms from the tool result appearing in the response
            if not self._is_source_used_in_response(result_text, response_text):
                continue  # Skip sources not used in the response
            
            # Look for URLs in the result (including kulturminnesok.no links)
            url_pattern = r'https?://[^\s<>"{}|\\^`\[\])]+[^\s<>"{}|\\^`\[\].,)]'
            urls = re.findall(url_pattern, result_text)
            
            for url in urls[:3]:  # Limit to 3 URLs per tool (reduced from 5)
                # Clean up URL (remove trailing punctuation)
                url = url.rstrip('.,;:)')
                
                if url not in seen_urls:
                    seen_urls.add(url)
                    
                    # Determine title based on URL and provider
                    if "kulturminnesok.no" in url:
                        # Try to extract the kulturminne name from the result text
                        name_match = re.search(
                            r'\*\*([^*]+)\*\*[^*]*?' + re.escape(url),
                            result_text,
                            re.DOTALL
                        )
                        if name_match:
                            title = f"{name_match.group(1).strip()} – Kulturminnesøk"
                        else:
                            id_match = re.search(r'[?&]id=([a-f0-9-]+)', url)
                            if id_match:
                                title = f"Kulturminne – Kulturminnesøk"
                            else:
                                title = "Kulturminnesøk"
                        provider = "riksantikvaren"
                    elif "snl.no" in url:
                        # Extract article name from URL path
                        # URLs like: https://snl.no/Djengis_Khan or https://lille.snl.no/Djengis_Khan
                        from urllib.parse import unquote
                        url_match = re.search(r'snl\.no/([^?#]+)', url)
                        if url_match:
                            article_slug = url_match.group(1)
                            # Convert URL encoding and underscores to readable title
                            article_name = unquote(article_slug).replace('_', ' ')
                            title = f"{article_name} – Store norske leksikon"
                        else:
                            title = arguments.get("query", "Artikkel") + " – Store norske leksikon"
                        provider = "snl"
                    elif "wikipedia.org" in url:
                        # Extract article name from URL path
                        # URLs like: https://en.wikipedia.org/wiki/Genghis_Khan
                        from urllib.parse import unquote
                        url_match = re.search(r'wikipedia\.org/wiki/([^?#]+)', url)
                        if url_match:
                            article_slug = url_match.group(1)
                            article_name = unquote(article_slug).replace('_', ' ')
                            title = f"{article_name} – Wikipedia"
                        else:
                            # Handle curid URLs like https://en.wikipedia.org/?curid=12345
                            curid_match = re.search(r'curid=(\d+)', url)
                            if curid_match:
                                title = f"Wikipedia artikkel #{curid_match.group(1)}"
                            else:
                                title = arguments.get("query", "Artikkel") + " – Wikipedia"
                        provider = "wikipedia"
                    else:
                        title = arguments.get("query", arguments.get("identifier", "Kilde"))
                    
                    sources.append(SourceReference(
                        title=title,
                        url=url,
                        provider=provider,
                        snippet=None
                    ))
        
        return sources[:10]  # Limit total sources
    
    def _is_source_used_in_response(self, tool_result: str, response_text: str) -> bool:
        """Check if content from a tool result appears to be used in the response.
        
        Uses multiple heuristics to determine relevance:
        1. Key names/titles from the tool result appear in the response
        2. Specific facts/numbers from the tool result appear in the response
        3. The query term appears in both
        """
        import re
        
        response_lower = response_text.lower()
        result_lower = tool_result.lower()
        
        # Extract key terms from tool result (bold text, names, etc.)
        bold_terms = re.findall(r'\*\*([^*]+)\*\*', tool_result)
        
        # Check if any bold terms (names, titles) appear in response
        for term in bold_terms:
            # Clean and check term (minimum 3 chars to avoid false positives)
            term_clean = term.strip().lower()
            if len(term_clean) >= 3 and term_clean in response_lower:
                return True
        
        # Extract numbers/dates that might be facts
        numbers = re.findall(r'\b(1[0-9]{3}|20[0-2][0-9])\b', tool_result)  # Years
        for num in numbers:
            if num in response_text:
                return True
        
        # Check for kommune/location names
        kommune_match = re.search(r'Kommune:\s*(\w+)', tool_result)
        if kommune_match:
            kommune = kommune_match.group(1).lower()
            if kommune in response_lower:
                return True
        
        # Check for kategori/type
        kategori_match = re.search(r'Kategori:\s*([^\n]+)', tool_result)
        if kategori_match:
            kategori = kategori_match.group(1).strip().lower()
            if len(kategori) >= 4 and kategori in response_lower:
                return True
        
        # Fallback: check for significant word overlap (at least 3 significant words)
        # Extract words longer than 5 chars from result
        result_words = set(re.findall(r'\b[a-zA-ZæøåÆØÅ]{6,}\b', result_lower))
        response_words = set(re.findall(r'\b[a-zA-ZæøåÆØÅ]{6,}\b', response_lower))
        
        overlap = result_words & response_words
        # Filter out common words
        common_words = {'kulturminner', 'kulturminne', 'riksantikvaren', 'norway', 'norwegian', 
                       'wikipedia', 'artikkel', 'source', 'kilder', 'beskrivelse'}
        meaningful_overlap = overlap - common_words
        
        if len(meaningful_overlap) >= 2:
            return True
        
        return False
    
    def _extract_related_queries(self, response_text: str) -> list[str]:
        """Extract related queries from the response."""
        queries = []
        
        # Look for the related questions section
        import re
        patterns = [
            r'\*\*Relaterte spørsmål:\*\*\s*\n((?:[-*]\s*.+\n?)+)',
            r'\*\*Related questions:\*\*\s*\n((?:[-*]\s*.+\n?)+)',
            r'## Relaterte spørsmål\s*\n((?:[-*]\s*.+\n?)+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                items = re.findall(r'[-*]\s*(.+?)(?:\?|\n|$)', match.group(1))
                queries = [q.strip() + ("?" if not q.strip().endswith("?") else "") for q in items if q.strip()]
                break
        
        return queries[:5]
    
    def _clean_response_text(self, response_text: str) -> str:
        """Remove sources and related questions sections from response text.
        
        These are extracted into structured fields, so we don't want them duplicated
        in the main response text.
        """
        import re
        
        cleaned = response_text
        
        # Remove "## Kilder" / "## Sources" / "## Kilder" section and everything after it
        # This catches everything from the sources heading to the end
        kilder_patterns = [
            r'\n+##\s*Kilder\s*\n[\s\S]*$',
            r'\n+##\s*Kilder\s*\n[\s\S]*$',  # Common typo
            r'\n+##\s*Sources\s*\n[\s\S]*$',
            r'\n+##\s*Referanser\s*\n[\s\S]*$',
        ]
        for pattern in kilder_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove "**Relaterte spørsmål:**" section (standalone or after ---)
        related_patterns = [
            r'\n+---\s*\n+\*\*Relaterte spørsmål[:\*]*\*\*\s*\n[\s\S]*$',
            r'\n+---\s*\n+\*\*Related questions[:\*]*\*\*\s*\n[\s\S]*$',
            r'\n+\*\*Relaterte spørsmål[:\*]*\*\*\s*\n(?:[-*]\s*.+\n?)+',
            r'\n+\*\*Related questions[:\*]*\*\*\s*\n(?:[-*]\s*.+\n?)+',
            r'\n+##\s*Relaterte spørsmål\s*\n[\s\S]*$',
            r'\n+##\s*Related questions\s*\n[\s\S]*$',
        ]
        for pattern in related_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove trailing horizontal rules and whitespace
        cleaned = re.sub(r'\n+---\s*$', '', cleaned)
        cleaned = cleaned.rstrip()
        
        return cleaned
    
    async def chat_stream(self, request: ChatRequest) -> AsyncGenerator[SSEEvent, None]:
        """Process a chat request with streaming events."""
        start_time = time.time()
        tools_used: list[str] = []
        sources_consulted: set[str] = set()
        tool_results: list[tuple[str, str, dict[str, Any]]] = []
        full_response_text = ""
        
        yield StatusEvent(message="Analyserer spørsmål...")
        
        # Build messages
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in request.conversation_history:
            messages.append(msg)
        messages.append({"role": "user", "content": request.message})
        
        # Get enabled tools
        tools = self._get_enabled_tools(request.sources)
        
        try:
            # First call to check for tool use (non-streaming)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                max_tokens=2048,
                temperature=0.7,
            )
            message = response.choices[0].message
            
            # Handle tool calls
            while message.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                        }
                        for tc in message.tool_calls
                    ]
                })
                
                # Prepare all tool calls for parallel execution
                tool_call_info = []
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tools_used.append(tool_name)
                    
                    # Track sources
                    for source, prefixes in SOURCE_TOOL_MAP.items():
                        if any(tool_name.startswith(p) for p in prefixes):
                            sources_consulted.add(source)
                    
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                    
                    tool_call_info.append((tool_call.id, tool_name, arguments))
                
                # Emit all tool start events
                for _, tool_name, arguments in tool_call_info:
                    yield ToolStartEvent(tool=tool_name, arguments=arguments)
                
                # Execute all tools in PARALLEL using asyncio.gather
                if len(tool_call_info) > 1:
                    logger.info(f"Executing {len(tool_call_info)} tools in parallel")
                
                async def execute_with_context(tool_name: str, arguments: dict) -> tuple[str, str, dict]:
                    result = await self._execute_tool(tool_name, arguments)
                    return (tool_name, result, arguments)
                
                parallel_results = await asyncio.gather(*[
                    execute_with_context(tool_name, arguments)
                    for _, tool_name, arguments in tool_call_info
                ])
                
                # Process results and emit end events
                for i, (tool_call_id, tool_name, arguments) in enumerate(tool_call_info):
                    _, result, _ = parallel_results[i]
                    tool_results.append((tool_name, result, arguments))
                    
                    # Emit tool end event
                    preview = result[:150] + "..." if len(result) > 150 else result
                    yield ToolEndEvent(tool=tool_name, success=True, preview=preview)
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result,
                    })
                
                # Get next response (non-streaming for tool loop)
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools if tools else None,
                    tool_choice="auto" if tools else None,
                    max_tokens=2048,
                    temperature=0.7,
                )
                message = response.choices[0].message
            
            # Now stream the final response
            yield StatusEvent(message="Genererer svar...")
            
            # Make a streaming call for the final response
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
                stream=True,
            )
            
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_response_text += token
                    yield TokenEvent(content=token)
            
            # If no streaming response, use the previous response
            if not full_response_text and message.content:
                full_response_text = message.content
                # Emit all tokens at once
                yield TokenEvent(content=full_response_text)
            
        except Exception as e:
            logger.error("Error in chat_stream", exc_info=True)
            yield ErrorEvent(message=str(e))
            return
        
        # Build final structured response
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        # Extract sources from tool results (only those actually used in response)
        extracted_sources = self._extract_sources_from_tool_results(tool_results, full_response_text)
        
        # Extract related queries from response (before cleaning)
        related_queries = self._extract_related_queries(full_response_text)
        
        # Clean the response text to remove sources/related queries sections
        # (these are now in structured fields, so we don't want duplicates)
        cleaned_response_text = self._clean_response_text(full_response_text)
        
        final_response = ChatResponse(
            response=ResponseContent(
                text=cleaned_response_text,
                summary=None,  # Could add a summarization step here
            ),
            sources=extracted_sources,
            locations=[],  # Could extract from riksantikvaren results
            related_queries=related_queries,
            metadata=ChatResponseMetadata(
                tools_used=tools_used,
                providers_consulted=list(sources_consulted),
                processing_time_ms=processing_time_ms,
                model=self.model,
            ),
        )
        
        yield DoneEvent(response=final_response)
    
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Process a chat request and return structured response (non-streaming)."""
        final_response = None
        
        async for event in self.chat_stream(request):
            if isinstance(event, DoneEvent):
                final_response = event.response
            elif isinstance(event, ErrorEvent):
                return ChatResponse(
                    response=ResponseContent(text=f"Error: {event.message}"),
                    metadata=ChatResponseMetadata(model=self.model),
                )
        
        if final_response is None:
            return ChatResponse(
                response=ResponseContent(text="No response generated."),
                metadata=ChatResponseMetadata(model=self.model),
            )
        
        return final_response
