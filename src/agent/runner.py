"""Agent runner that uses OpenAI with MCP tools."""

import json
import logging
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field

from src.mcp.registry import get_registry

logger = logging.getLogger(__name__)


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


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    
    response: str = Field(..., description="Agent response")
    tools_used: list[str] = Field(default_factory=list, description="Tools that were called")
    sources_consulted: list[str] = Field(default_factory=list, description="Data sources used")


# Map source names to tool prefixes
SOURCE_TOOL_MAP = {
    "wikipedia": ["wikipedia-"],
    "snl": ["snl-"],
    "riksantikvaren": ["riksantikvaren-", "arcgis-"],
}

# System prompt for the agent
SYSTEM_PROMPT = """You are a knowledgeable guide to Norwegian cultural heritage. You help users discover and learn about historical sites, monuments, buildings, and cultural landmarks in Norway.

You have access to several data sources:
- **Wikipedia**: General encyclopedic knowledge in Norwegian and English
- **Store norske leksikon (SNL)**: Authoritative Norwegian encyclopedia
- **Riksantikvaren/Askeladden**: Official Norwegian cultural heritage database with 600,000+ registered sites

When answering questions:
1. Use the appropriate tools to find accurate information
2. Prefer Norwegian sources (SNL, Riksantikvaren) for Norwegian cultural heritage
3. Use Wikipedia for broader context or international comparisons
4. Always cite your sources
5. If you can't find information, say so honestly
6. For location-based queries, use geosearch tools when coordinates are available

Respond in the same language as the user's question (Norwegian or English)."""


class AgentRunner:
    """Runs the chat agent with tool calling."""
    
    def __init__(self, openai_api_key: str):
        """Initialize with OpenAI API key."""
        self.client = OpenAI(api_key=openai_api_key)
        self.registry = get_registry()
    
    def _get_enabled_tools(self, sources: list[str]) -> list[dict[str, Any]]:
        """Get OpenAI tool definitions for enabled sources."""
        tools = []
        enabled_prefixes = []
        
        for source in sources:
            if source in SOURCE_TOOL_MAP:
                enabled_prefixes.extend(SOURCE_TOOL_MAP[source])
        
        # Get all tools from registry and filter by prefix
        for mcp_tool in self.registry.list_tools():
            if any(mcp_tool.name.startswith(prefix) for prefix in enabled_prefixes):
                # Convert MCP tool schema to OpenAI function format
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
            
            # Handle different result types
            if isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False, indent=2)
            elif isinstance(result, list):
                return json.dumps(result, ensure_ascii=False, indent=2)
            else:
                return str(result)
                
        except Exception as e:
            logger.error(f"Tool execution error: {tool_name}", exc_info=True)
            return json.dumps({"error": str(e)})
    
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Process a chat request and return response."""
        tools_used = []
        sources_consulted = set()
        
        # Build messages
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        # Add conversation history
        for msg in request.conversation_history:
            messages.append(msg)
        
        # Add current user message
        messages.append({"role": "user", "content": request.message})
        
        # Get enabled tools
        tools = self._get_enabled_tools(request.sources)
        
        # Call OpenAI with tools
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",  # Using gpt-4o for good balance of quality and cost
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                max_tokens=2048,
                temperature=0.7,
            )
        except Exception as e:
            logger.error("OpenAI API error", exc_info=True)
            return ChatResponse(
                response=f"Error communicating with AI service: {str(e)}",
                tools_used=[],
                sources_consulted=[],
            )
        
        # Process response and handle tool calls
        message = response.choices[0].message
        
        # If there are tool calls, execute them and get final response
        while message.tool_calls:
            # Add assistant message with tool calls
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
            
            # Execute each tool call
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tools_used.append(tool_name)
                
                # Track which sources were used
                for source, prefixes in SOURCE_TOOL_MAP.items():
                    if any(tool_name.startswith(p) for p in prefixes):
                        sources_consulted.add(source)
                
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}
                
                logger.info(f"Executing tool: {tool_name}", extra={"arguments": arguments})
                result = await self._execute_tool(tool_name, arguments)
                
                # Add tool result
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
            
            # Get next response
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    tools=tools if tools else None,
                    tool_choice="auto" if tools else None,
                    max_tokens=2048,
                    temperature=0.7,
                )
                message = response.choices[0].message
            except Exception as e:
                logger.error("OpenAI API error during tool loop", exc_info=True)
                return ChatResponse(
                    response=f"Error during tool execution: {str(e)}",
                    tools_used=tools_used,
                    sources_consulted=list(sources_consulted),
                )
        
        return ChatResponse(
            response=message.content or "I couldn't generate a response.",
            tools_used=tools_used,
            sources_consulted=list(sources_consulted),
        )
