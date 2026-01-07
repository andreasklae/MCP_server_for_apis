# Kulturarv MCP Server

A **Model Context Protocol (MCP)** server for Norwegian cultural heritage APIs, designed for integration with **OpenAI Agent Builder**.

This server exposes tools that allow AI agents to query:
- **Wikipedia** — Article search, summaries, and geosearch
- **Store Norske Leksikon (SNL)** — Norwegian encyclopedia
- **Riksantikvaren OGC API** — Cultural heritage sites from `api.ra.no`
- **Riksantikvaren ArcGIS API** — Spatial queries from `kart.ra.no`

## Quick Start

### With Docker

```bash
# Clone and enter the directory
cd MCP_server_for_apis

# Start the server
docker compose up --build

# The server is now available at http://localhost:8000
```

### With Python

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Run the server
python -m src.main

# Or with uvicorn directly
uvicorn src.main:app --reload
```

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Server info and available endpoints |
| `/health` | GET | Health check |
| `/sse` | GET | SSE connection for MCP session |
| `/message` | POST | JSON-RPC message endpoint |
| `/docs` | GET | OpenAPI documentation |

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test file
pytest tests/test_mcp_jsonrpc.py -v
```

### Validate with MCP Inspector

Before connecting to OpenAI Agent Builder, validate your server:

```bash
npx @modelcontextprotocol/inspector
```

Then enter your server URL (e.g., `http://localhost:8000`) and test the tools.

## Configuration

### Environment Variables

Copy `env.example` to `.env` and configure:

```bash
# Authentication (leave empty for open/dev mode)
MCP_AUTH_TOKEN=your-secret-token

# Rate limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### API Providers

Edit `config/apis.yaml` to enable/disable providers:

```yaml
enabled_providers:
  - example
  - wikipedia
  - snl
  - riksantikvaren_ogc
  - riksantikvaren_arcgis
```

## Available Tools

| Tool | Description |
|------|-------------|
| `example-ping` | Test if the server is working |
| `example-echo` | Echo back a message |

*Additional tools are added when you implement the Wikipedia, SNL, and Riksantikvaren providers.*

## Adding a New API Provider

1. **Document the API** in `docs/apis/<provider>.md`

2. **Create the provider module**:
   ```
   src/tools/<provider>/
   ├── __init__.py
   ├── client.py    # HTTP client for the API
   └── tools.py     # Tool definitions
   ```

3. **Implement the client** (`client.py`):
   ```python
   import httpx
   from src.utils.http import create_http_client

   class MyApiClient:
       async def search(self, query: str) -> dict:
           async with create_http_client() as client:
               response = await client.get(f"https://api.example.com/search?q={query}")
               return response.json()
   ```

4. **Define tools** (`tools.py`):
   ```python
   from src.mcp.models import TextContent
   from src.mcp.registry import ToolRegistry

   async def search_handler(arguments: dict) -> list[TextContent]:
       query = arguments.get("query", "")
       # ... call client and format response
       return [TextContent(text=f"Results for: {query}")]

   def register_tools(registry: ToolRegistry) -> None:
       registry.register(
           name="myprovider-search",
           description="Search the API",
           input_schema={
               "type": "object",
               "properties": {
                   "query": {"type": "string", "description": "Search query"}
               },
               "required": ["query"]
           },
           handler=search_handler,
       )
   ```

5. **Enable the provider** in `config/apis.yaml`:
   ```yaml
   enabled_providers:
     - example
     - myprovider
   ```

## Connecting to OpenAI Agent Builder

1. **Deploy the server** to a public URL (e.g., Azure, Railway, Render)

2. **In Agent Builder**, go to your agent's settings

3. **Add MCP Server**:
   - URL: `https://your-server.com`
   - Authentication: Bearer token (if `MCP_AUTH_TOKEN` is set)

4. **Connect and approve tools**

5. **Test** by asking your agent to use the tools

## Example curl Commands

### Health Check
```bash
curl http://localhost:8000/health
```

### Initialize Session (JSON-RPC)
```bash
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {"name": "curl", "version": "1.0"}
    }
  }'
```

### List Tools
```bash
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
  }'
```

### Call a Tool
```bash
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "example-ping",
      "arguments": {}
    }
  }'
```

### Open SSE Stream
```bash
curl -N http://localhost:8000/sse
```

## Limitations

- **In-memory sessions** — Sessions are stored in memory; no horizontal scaling
- **Single instance only** — Not designed for multi-instance deployment
- **No persistence** — Session state is lost on restart
- **Session timeout** — Sessions expire after 30 minutes of inactivity

## Project Structure

```
MCP_server_for_apis/
├── src/
│   ├── main.py                 # FastAPI application
│   ├── mcp/                    # MCP protocol implementation
│   │   ├── models.py           # Pydantic models
│   │   ├── jsonrpc.py          # JSON-RPC processing
│   │   ├── handlers.py         # MCP method handlers
│   │   ├── registry.py         # Tool registry
│   │   └── transport_sse.py    # SSE transport
│   ├── tools/                  # Tool providers
│   │   ├── base.py             # Base tool class
│   │   └── example/            # Example provider
│   ├── config/                 # Configuration loading
│   ├── security/               # Auth, SSRF, rate limiting
│   └── utils/                  # Logging, HTTP client
├── config/
│   └── apis.yaml               # Provider configuration
├── docs/
│   ├── MCP.md                  # Protocol documentation
│   └── apis/                   # API documentation
├── tests/                      # pytest tests
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## License

MIT

## Related

- [MCP Specification](https://modelcontextprotocol.io/specification)
- [OpenAI MCP Documentation](https://platform.openai.com/docs/mcp)
- [Riksantikvaren APIs](https://api.ra.no/)

