"""
Optimized Agent Runner v2 - Two-Model Architecture

This version uses:
1. gpt-4o-mini for fast tool selection (routing)
2. gpt-4o for high-quality response generation
3. Single tool round (no iterative loops)
4. Streaming throughout for better perceived performance

Performance target: 50% faster than v1
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator

from openai import OpenAI, AzureOpenAI
from pydantic import BaseModel

from src.config.loader import get_settings
from src.mcp.models import TextContent
from src.mcp.registry import get_registry

logger = logging.getLogger(__name__)

# =============================================================================
# Source to Tool Mapping
# =============================================================================

SOURCE_TOOL_MAP = {
    "wikipedia": ["wikipedia-"],
    "snl": ["snl-"],
    "riksantikvaren": ["riksantikvaren-", "arcgis-"],
}

# =============================================================================
# Models
# =============================================================================

class ChatRequest(BaseModel):
    message: str
    sources: list[str] = []
    conversation_history: list[dict[str, str]] = []


class SourceReference(BaseModel):
    title: str
    url: str
    provider: str
    snippet: str | None = None


class ResponseContent(BaseModel):
    text: str
    summary: str | None = None


class ChatResponseMetadata(BaseModel):
    tools_used: list[str] = []
    providers_consulted: list[str] = []
    processing_time_ms: int = 0
    model: str = "gpt-4o"
    router_model: str = "gpt-4o-mini"


class ChatResponse(BaseModel):
    response: ResponseContent
    sources: list[SourceReference] = []
    locations: list[dict] = []
    related_queries: list[str] = []
    metadata: ChatResponseMetadata = ChatResponseMetadata()


# =============================================================================
# SSE Event Types
# =============================================================================

class StatusEvent(BaseModel):
    type: str = "status"
    message: str


class ToolStartEvent(BaseModel):
    type: str = "tool_start"
    tool: str
    arguments: dict[str, Any] = {}


class ToolEndEvent(BaseModel):
    type: str = "tool_end"
    tool: str
    success: bool
    preview: str = ""


class TokenEvent(BaseModel):
    type: str = "token"
    content: str


class DoneEvent(BaseModel):
    type: str = "done"
    response: ChatResponse


class ErrorEvent(BaseModel):
    type: str = "error"
    message: str


SSEEvent = StatusEvent | ToolStartEvent | ToolEndEvent | TokenEvent | DoneEvent | ErrorEvent

# =============================================================================
# System Prompts
# =============================================================================

ROUTER_PROMPT = """You are a tool routing assistant. Your ONLY job is to select which tools to call.

## Instructions
1. Analyze the user's query
2. Select the most appropriate tools to gather information
3. Call multiple tools in parallel for comprehensive coverage
4. DO NOT generate a text response - only make tool calls

## Tool Selection Guidelines
- For Norwegian cultural heritage: prefer SNL + Riksantikvaren
- For general knowledge: use Wikipedia
- For location-based queries: use arcgis-nearby (official sites) or riksantikvaren-nearby (user stories)
- When in doubt, call more tools rather than fewer

Call tools now. Do not explain or respond with text."""

RESPONDER_PROMPT = """You are a knowledgeable and engaging tour guide specializing in Norwegian cultural heritage.

## Your Task
Based on the search results provided, synthesize a helpful response for the user.

## Guidelines
1. **Language**: Always respond in the same language as the user's query
2. **Format**: Use clean markdown with proper headings and lists
3. **Sources**: DO NOT include source links in text - they're handled separately
4. **Accuracy**: Only include information from the search results
5. **Style**: Be informative but engaging, like a knowledgeable guide

## Markdown Rules
- Use numbered lists as: "1. **Title**: Description"
- Use only ## headers (not ### or ####)
- Single blank lines between paragraphs
- No nested bullet points"""

# =============================================================================
# Agent Runner V2
# =============================================================================

class AgentRunnerV2:
    """
    Two-model architecture agent:
    - gpt-4o-mini for fast tool routing
    - gpt-4o for quality response generation
    """
    
    def __init__(self, api_key: str):
        """Initialize with OpenAI API key (works with both OpenAI and Azure OpenAI)."""
        settings = get_settings()
        
        if settings.use_azure_openai:
            logger.info(f"Using Azure OpenAI: {settings.azure_openai_endpoint}")
            self.client = AzureOpenAI(
                api_key=api_key,
                api_version=settings.azure_openai_api_version,
                azure_endpoint=settings.azure_openai_endpoint,
            )
            main_deployment = settings.azure_openai_deployment
            
            # Check if explicit router deployment is set
            if settings.azure_openai_deployment_router:
                self.router_model = settings.azure_openai_deployment_router
                logger.info(f"Router deployment: {self.router_model} (from AZURE_OPENAI_DEPLOYMENT_ROUTER)")
            elif "gpt-4o" in main_deployment and "mini" not in main_deployment:
                # Try to derive mini deployment name (e.g., "gpt-4o" -> "gpt-4o-mini")
                self.router_model = main_deployment.replace("gpt-4o", "gpt-4o-mini")
                logger.info(f"Router deployment: {self.router_model} (derived from {main_deployment})")
            else:
                # If deployment name doesn't match pattern or already contains "mini",
                # use the same deployment for both (works if you only have one deployment)
                self.router_model = main_deployment
                logger.info(f"Using same deployment for router: {self.router_model}")
            
            self.responder_model = main_deployment
            logger.info(f"Responder deployment: {self.responder_model}")
        else:
            logger.info("Using OpenAI direct API")
            self.client = OpenAI(api_key=api_key)
            self.router_model = "gpt-4o-mini"
            self.responder_model = "gpt-4o"
        
        self.registry = get_registry()
    
    def _get_enabled_tools(self, sources: list[str]) -> list[dict]:
        """Get OpenAI tool definitions for enabled sources."""
        tools = []
        enabled_prefixes = set()
        
        for source in sources:
            if source in SOURCE_TOOL_MAP:
                enabled_prefixes.update(SOURCE_TOOL_MAP[source])
        
        # If no sources specified, enable all
        if not enabled_prefixes:
            enabled_prefixes = {p for prefixes in SOURCE_TOOL_MAP.values() for p in prefixes}
        
        for tool in self.registry.list_tools():
            if any(tool.name.startswith(prefix) for prefix in enabled_prefixes):
                tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema,
                    }
                })
        
        return tools
    
    async def _execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool and return the result as a string."""
        tool = self.registry.get(tool_name)
        if not tool:
            return f"Tool not found: {tool_name}"
        
        try:
            result = await tool.handler(arguments)
            
            # Handle different result types
            if isinstance(result, TextContent):
                return result.text
            elif hasattr(result, 'text'):
                return result.text
            elif isinstance(result, list):
                return json.dumps([
                    r.text if isinstance(r, TextContent) else str(r) 
                    for r in result
                ], ensure_ascii=False)
            else:
                return str(result)
                
        except Exception as e:
            logger.error(f"Tool execution error: {tool_name}", exc_info=True)
            return f"Error executing {tool_name}: {str(e)}"
    
    def _extract_sources_from_results(
        self, tool_results: list[tuple[str, str, dict]], response_text: str
    ) -> list[SourceReference]:
        """Extract source references from tool results."""
        import re
        from urllib.parse import unquote
        
        sources = []
        seen_urls = set()
        response_lower = response_text.lower()
        
        for tool_name, result_text, arguments in tool_results:
            # Determine provider
            provider = "riksantikvaren"
            if tool_name.startswith("wikipedia-"):
                provider = "wikipedia"
            elif tool_name.startswith("snl-"):
                provider = "snl"
            
            # Find URLs in result
            url_pattern = r'https?://[^\s<>"{}|\\^`\[\])]+[^\s<>"{}|\\^`\[\].,)]'
            urls = re.findall(url_pattern, result_text)
            
            for url in urls[:3]:
                url = url.rstrip('.,;:)')
                
                if url not in seen_urls:
                    seen_urls.add(url)
                    
                    # Determine title from URL
                    if "kulturminnesok.no" in url:
                        title = "Kulturminnesøk"
                        provider = "riksantikvaren"
                    elif "snl.no" in url:
                        url_match = re.search(r'snl\.no/([^?#]+)', url)
                        if url_match:
                            article_name = unquote(url_match.group(1)).replace('_', ' ')
                            title = f"{article_name} – Store norske leksikon"
                        else:
                            title = "Store norske leksikon"
                        provider = "snl"
                    elif "wikipedia.org" in url:
                        url_match = re.search(r'wikipedia\.org/wiki/([^?#]+)', url)
                        if url_match:
                            article_name = unquote(url_match.group(1)).replace('_', ' ')
                            title = f"{article_name} – Wikipedia"
                        else:
                            title = "Wikipedia"
                        provider = "wikipedia"
                    else:
                        title = arguments.get("query", "Kilde")
                    
                    sources.append(SourceReference(
                        title=title,
                        url=url,
                        provider=provider,
                        snippet=None
                    ))
        
        return sources[:10]
    
    async def chat_stream(self, request: ChatRequest) -> AsyncGenerator[SSEEvent, None]:
        """
        Process a chat request with streaming events.
        
        Flow:
        1. Route query through gpt-4o-mini to select tools (fast)
        2. Execute selected tools in parallel
        3. Generate response with gpt-4o using tool results (streaming)
        """
        start_time = time.time()
        tools_used: list[str] = []
        tool_results: list[tuple[str, str, dict]] = []
        full_response_text = ""
        
        yield StatusEvent(message="Velger kilder...")
        
        # Get available tools
        tools = self._get_enabled_tools(request.sources)
        
        if not tools:
            yield ErrorEvent(message="Ingen kilder tilgjengelig")
            return
        
        try:
            # =================================================================
            # PHASE 1: Fast tool selection with gpt-4o-mini
            # =================================================================
            
            router_messages = [
                {"role": "system", "content": ROUTER_PROMPT},
                {"role": "user", "content": request.message}
            ]
            
            router_response = self.client.chat.completions.create(
                model=self.router_model,
                messages=router_messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=150,
                parallel_tool_calls=True,
            )
            
            tool_calls = router_response.choices[0].message.tool_calls or []
            
            if not tool_calls:
                # No tools selected - generate direct response
                yield StatusEvent(message="Genererer svar...")
                
                stream = self.client.chat.completions.create(
                    model=self.responder_model,
                    messages=[
                        {"role": "system", "content": RESPONDER_PROMPT},
                        {"role": "user", "content": request.message}
                    ],
                    max_tokens=1500,
                    stream=True,
                )
                
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        token = chunk.choices[0].delta.content
                        full_response_text += token
                        yield TokenEvent(content=token)
            
            else:
                # =============================================================
                # PHASE 2: Execute tools in parallel
                # =============================================================
                
                yield StatusEvent(message=f"Søker i {len(tool_calls)} kilder...")
                
                # Prepare tool calls
                tool_call_info = []
                for tc in tool_calls:
                    tool_name = tc.function.name
                    tools_used.append(tool_name)
                    
                    try:
                        arguments = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                    
                    tool_call_info.append((tool_name, arguments))
                    yield ToolStartEvent(tool=tool_name, arguments=arguments)
                
                # Execute all tools in parallel
                async def execute_with_context(name: str, args: dict) -> tuple[str, str, dict]:
                    result = await self._execute_tool(name, args)
                    return (name, result, args)
                
                parallel_results = await asyncio.gather(*[
                    execute_with_context(name, args) 
                    for name, args in tool_call_info
                ])
                
                # Process results
                for name, result, args in parallel_results:
                    tool_results.append((name, result, args))
                    preview = result[:150] + "..." if len(result) > 150 else result
                    yield ToolEndEvent(tool=name, success=True, preview=preview)
                
                # =============================================================
                # PHASE 3: Generate response with gpt-4o
                # =============================================================
                
                yield StatusEvent(message="Genererer svar...")
                
                # Build context from tool results
                context_parts = []
                for name, result, _ in tool_results:
                    # Truncate large results
                    truncated = result[:2000] if len(result) > 2000 else result
                    context_parts.append(f"## {name}\n{truncated}")
                
                context = "\n\n---\n\n".join(context_parts)
                
                responder_messages = [
                    {"role": "system", "content": RESPONDER_PROMPT},
                    {"role": "user", "content": request.message},
                    {"role": "assistant", "content": "I've searched the sources. Here's what I found:"},
                    {"role": "user", "content": f"Search results:\n\n{context}\n\nPlease synthesize this into a helpful response."}
                ]
                
                # Add conversation history if present
                if request.conversation_history:
                    # Insert history before current message
                    for msg in request.conversation_history[-4:]:  # Last 4 messages
                        responder_messages.insert(2, msg)
                
                stream = self.client.chat.completions.create(
                    model=self.responder_model,
                    messages=responder_messages,
                    max_tokens=1500,
                    temperature=0.7,
                    stream=True,
                )
                
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        token = chunk.choices[0].delta.content
                        full_response_text += token
                        yield TokenEvent(content=token)
        
        except Exception as e:
            logger.error("Error in chat_stream", exc_info=True)
            yield ErrorEvent(message=str(e))
            return
        
        # Build final response
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        # Extract sources
        sources = self._extract_sources_from_results(tool_results, full_response_text)
        
        # Determine providers consulted
        providers = set()
        for tool_name in tools_used:
            for source, prefixes in SOURCE_TOOL_MAP.items():
                if any(tool_name.startswith(p) for p in prefixes):
                    providers.add(source)
        
        final_response = ChatResponse(
            response=ResponseContent(text=full_response_text.strip()),
            sources=sources,
            locations=[],
            related_queries=[],
            metadata=ChatResponseMetadata(
                tools_used=tools_used,
                providers_consulted=list(providers),
                processing_time_ms=processing_time_ms,
                model=self.responder_model,
                router_model=self.router_model,
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
                    metadata=ChatResponseMetadata(
                        model=self.responder_model,
                        router_model=self.router_model,
                    ),
                )
        
        if final_response is None:
            return ChatResponse(
                response=ResponseContent(text="No response generated."),
                metadata=ChatResponseMetadata(
                    model=self.responder_model,
                    router_model=self.router_model,
                ),
            )
        
        return final_response
