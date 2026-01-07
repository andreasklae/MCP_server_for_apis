# prompt.md — Build a Dockerized FastAPI MCP Server for OpenAI Agent Builder

You are working inside a Git repo. Create a **production-ready** (but minimal) MCP server implemented in **Python + FastAPI**, designed to be used as a **remote MCP server** by **OpenAI Agent Builder**.

The server's job: expose a set of **MCP tools** that proxy/compose calls to external **public APIs that do not require API keys**. These APIs provide access to Norwegian cultural heritage data and encyclopedic knowledge.

I will provide **API documentation** as separate files in this repo (e.g. `docs/apis/*.md`). Your implementation must be structured so I can add/remove APIs without rewriting core MCP plumbing.

---

## Reference Documentation

**Read these before implementing:**
- **OpenAI MCP Docs:** https://platform.openai.com/docs/mcp
- **MCP Specification:** https://modelcontextprotocol.io/specification
- **OpenAI Agents SDK (MCP):** https://openai.github.io/openai-agents-python/mcp/

The MCP protocol uses **JSON-RPC 2.0** over SSE transport. OpenAI Agent Builder expects strict compliance with this spec.

---

## Target APIs to Integrate

The following public APIs should be integrated. All are freely available without API keys.

### 1. Wikipedia (MediaWiki API)
- **Base URL:** `https://en.wikipedia.org/w/api.php` (or language-specific variants like `no.wikipedia.org`)
- **Use cases:** Article summaries, search, page content, geosearch for nearby articles
- **Docs:** https://www.mediawiki.org/wiki/API:Main_page
- **Key endpoints:**
  - `action=query&prop=extracts` — get article summaries
  - `action=query&list=search` — search articles
  - `action=query&list=geosearch` — find articles near coordinates
  - `action=parse` — get parsed article content

### 2. Store Norske Leksikon (SNL)
- **Base URL:** `https://snl.no/api/v1/`
- **Use cases:** Norwegian encyclopedia articles, search, authoritative Norwegian-language content
- **Docs:** https://snl.no/api/dokumentasjon
- **Key endpoints:**
  - `/search?query=<term>` — search articles
  - `/article/<id>` — get article by ID
  - Articles also accessible via URL slug

### 3. Riksantikvaren — Cultural Heritage APIs

Data from Riksantikvaren (Norwegian Directorate for Cultural Heritage) is licensed under NLOD and CC licenses.

#### 3a. OGC API (api.ra.no)
- **Base URL:** `https://api.ra.no/`
- **Use cases:** Cultural heritage sites, protected monuments, user-contributed "Brukeminner"
- **Docs:** OGC API Features standard
- **Key collections:**
  - `/collections/askeladden` — official cultural heritage register
  - `/collections/brukeminner` — user-contributed cultural memories
- **Features:**
  - Supports `bbox` for geographic filtering
  - Returns GeoJSON
  - Pagination via `limit` and `offset`

#### 3b. ArcGIS REST API (kart.ra.no)
- **Base URL:** `https://kart.ra.no/arcgis/rest/services/Distribusjon`
- **Use cases:** Map services, spatial queries, richer querying capabilities
- **Features:**
  - Feature layers for various cultural heritage categories
  - Supports spatial queries (point, envelope, polygon)
  - Returns JSON/GeoJSON

#### 3c. GeoNorge Datasets
- **Portal:** https://kartkatalog.geonorge.no/?organizations=Riksantikvaren
- **Use cases:** Bulk downloads, WMS/WFS services
- **Note:** Consider adding tools to query/download specific datasets

---

## Requirements

### Core
- Use **Python 3.12+** (prefer latest stable).
- Use **FastAPI** for the web server.
- Implement **MCP protocol with JSON-RPC 2.0** format (required for OpenAI Agent Builder).
  - Implement **SSE transport** for streaming (`/sse` endpoint).
  - Implement **message endpoint** for JSON-RPC requests (`/message`).
- Expose:
  - `GET /health` → `{ "status": "ok" }`
  - `GET /` → basic info + links to docs endpoints
- Provide **tool discovery** and **tool invocation** via MCP:
  - A tool has: `name`, `description`, `inputSchema` (JSON schema), and a callable handler.
  - Tools must return content in MCP-compatible format.

### API Tooling
- There will be multiple APIs (public, no keys required).
- Tools should be grouped by API provider.
- Implement a **plug-in style registry**:
  - `src/tools/<provider>/` contains provider tools.
  - Each provider has:
    - a `client.py` responsible for HTTP calls
    - one or more tool definitions in `tools.py`
- Use `httpx` for outgoing HTTP calls with:
  - configurable timeouts (default 30s)
  - retries with exponential backoff (3 attempts)
  - sane error handling (HTTP errors, JSON decode, network errors)

### Geo-spatial Considerations
Since Riksantikvaren APIs return GeoJSON, include utilities for:
- Validating bounding boxes (bbox)
- Formatting coordinates (lat/lon vs lon/lat — be explicit about conventions)
- Optionally simplifying geometries for large responses

### Configuration
- Create `config/apis.yaml` where I can list which API providers/tools are enabled.
- Structure:

```yaml
# Which providers to load on startup
enabled_providers:
  - wikipedia
  - snl
  - riksantikvaren_ogc
  - riksantikvaren_arcgis

# Provider-specific settings (optional overrides)
providers:
  wikipedia:
    default_language: "no"  # Norwegian Wikipedia by default
    timeout: 30
  snl:
    timeout: 30
  riksantikvaren_ogc:
    base_url: "https://api.ra.no/"
    timeout: 60  # geo queries can be slow
  riksantikvaren_arcgis:
    base_url: "https://kart.ra.no/arcgis/rest/services/Distribusjon"
    timeout: 60
```

### API Documentation Inputs
- Assume I will place docs under `docs/apis/`.
- Create a convention: each provider has a doc file named like:
  - `docs/apis/<provider>.md`
- Your code must not hardcode specific APIs beyond the example provider; it should be easy to add new providers based on those docs.

### Example Provider (Minimal)
Implement exactly one **example provider** to demonstrate the pattern end-to-end.
- Provider name: `example`
- Tools:
  - `example-ping` — returns `{ "pong": true }`
  - `example-echo` — echoes back input arguments
- This provider serves as a template for implementing real providers.

### SSRF Protection
For any tool that accepts URLs as input (if any), implement strict SSRF checks:
- Only allow `http` and `https` schemes
  - Block `localhost`, `127.0.0.1`, `0.0.0.0`, `::1`
  - Block private network ranges (10/8, 172.16/12, 192.168/16)
  - Block link-local and metadata IPs (169.254/16, 100.64/10)
  - If hostname resolves to a blocked IP → deny
  - Keep this logic in `src/security/ssrf.py` with tests

### Observability
- Structured logging (JSON format) with:
  - `request_id`
  - `tool_name`
  - `duration_ms`
  - `status` (ok/error)
  - `upstream_url` (for debugging)
- Add a middleware that injects a request ID (use UUID4).
- Log all upstream API calls with timing.

### Security (Baseline)
- No API keys required for upstream APIs, but we still want basic hygiene:
  - Optional `MCP_AUTH_TOKEN` env var:
    - if set, require `Authorization: Bearer <token>` on MCP endpoints
    - if not set, run in open mode (dev)
- Rate limiting:
  - Lightweight in-memory limiter (per-IP, per-minute).
  - Toggle via env var `RATE_LIMIT_ENABLED=true|false`.
  - Default limit configurable via `RATE_LIMIT_PER_MINUTE`.

---

## Repo Layout to Create

```
.
├── src/
│   ├── main.py                    # FastAPI app entrypoint
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── jsonrpc.py             # JSON-RPC 2.0 message handling
│   │   ├── transport_sse.py       # SSE streaming transport
│   │   ├── handlers.py            # MCP method handlers
│   │   ├── registry.py            # Tool registry
│   │   ├── models.py              # Pydantic models for MCP/JSON-RPC
│   │   └── errors.py              # JSON-RPC error codes
│   ├── tools/
│   │   ├── __init__.py            # Auto-registration logic
│   │   ├── base.py                # Base tool class/protocol
│   │   └── example/
│   │       ├── __init__.py
│   │       ├── client.py
│   │       └── tools.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── loader.py              # YAML config loading
│   ├── security/
│   │   ├── __init__.py
│   │   ├── auth.py                # Bearer token auth
│   │   └── ssrf.py                # SSRF protection
│   └── utils/
│       ├── __init__.py
│       ├── logging.py             # Structured logging setup
│       ├── http.py                # httpx client factory
│       └── rate_limit.py          # Rate limiter
├── config/
│   └── apis.yaml                  # Provider configuration
├── docs/
│   ├── MCP.md                     # MCP protocol documentation
│   └── apis/
│       ├── example.md
│       ├── wikipedia.md
│       ├── snl.md
│       ├── riksantikvaren_ogc.md
│       └── riksantikvaren_arcgis.md
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # pytest fixtures
│   ├── test_health.py
│   ├── test_ssrf.py
│   ├── test_mcp_jsonrpc.py        # JSON-RPC protocol tests
│   └── test_tools_example.py
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── .env.example
├── .dockerignore
├── .gitignore
└── README.md
```

---

## MCP Protocol Implementation (JSON-RPC 2.0)

The MCP protocol uses **JSON-RPC 2.0** over HTTP with SSE. Implement the following:

### Transport Endpoints

#### `GET /sse`
Establish an SSE connection for the MCP session.

On connection:
1. Generate a unique `session_id`
2. Send an `endpoint` event with the message URL:
```
event: endpoint
data: /message?session_id=<session_id>
```

The client will then POST JSON-RPC messages to this endpoint.

#### `POST /message`
Accept JSON-RPC 2.0 messages. Query param `session_id` identifies the session.

### JSON-RPC 2.0 Message Format

All requests follow this structure:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "method_name",
  "params": { }
}
```

All responses follow this structure:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": { }
}
```

Or for errors:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32600,
    "message": "Invalid Request",
    "data": { }
  }
}
```

### Required MCP Methods

#### `initialize`
Client sends this first to initialize the session.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "roots": { "listChanged": true }
    },
    "clientInfo": {
      "name": "OpenAI Agent Builder",
      "version": "1.0.0"
    }
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {}
    },
    "serverInfo": {
      "name": "kulturarv-mcp-server",
      "version": "1.0.0"
    }
  }
}
```

#### `notifications/initialized`
Client sends this after receiving initialize response (no response needed).

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/initialized"
}
```

#### `tools/list`
List all available tools.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "wikipedia-search",
        "description": "Search Wikipedia for articles matching a query",
        "inputSchema": {
          "type": "object",
          "properties": {
            "query": {
              "type": "string",
              "description": "Search query"
            },
            "language": {
              "type": "string",
              "description": "Wikipedia language code (e.g., 'en', 'no')",
              "default": "no"
            },
            "limit": {
              "type": "integer",
              "description": "Maximum results to return",
              "default": 10
            }
          },
          "required": ["query"]
        }
      }
    ]
  }
}
```

#### `tools/call`
Invoke a tool.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "wikipedia-search",
    "arguments": {
      "query": "Oslo",
      "language": "no",
      "limit": 5
    }
  }
}
```

**Response (success):**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Found 5 articles matching 'Oslo':\n\n1. Oslo - Capital of Norway..."
      }
    ],
    "isError": false
  }
}
```

**Response (tool error):**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Error: Unable to connect to Wikipedia API"
      }
    ],
    "isError": true
  }
}
```

### JSON-RPC Error Codes

Use standard JSON-RPC 2.0 error codes:
- `-32700` — Parse error (invalid JSON)
- `-32600` — Invalid Request (not valid JSON-RPC)
- `-32601` — Method not found
- `-32602` — Invalid params
- `-32603` — Internal error

### SSE Event Streaming

For long-running tool calls, stream progress via SSE:
```
event: message
data: {"jsonrpc":"2.0","id":3,"result":{"content":[...],"isError":false}}
```

Also push results to SSE if client has active session.

---

## Tool Model

A tool definition must include:
- `name` (string, lowercase with hyphens, e.g., `wikipedia-search`)
- `description` (string, clear enough for an LLM to understand when to use it)
- `inputSchema` (JSON Schema object — note camelCase per MCP spec)
- `handler(arguments: dict) -> list[Content]` (async)

The registry must:
- Auto-discover and register tools from enabled providers (based on `config/apis.yaml`)
- Support async handlers
- Fail gracefully if a provider module is missing (log warning + skip)
- Validate input arguments against schema before calling handler

### Content Types

Tool responses return a list of content items:
```python
@dataclass
class TextContent:
    type: Literal["text"] = "text"
    text: str

@dataclass  
class ImageContent:
    type: Literal["image"] = "image"
    data: str  # base64 encoded
    mimeType: str

# Tools return list of these
Content = TextContent | ImageContent
```

---

## Tool Specifications

### Wikipedia Tools
- `wikipedia-search` — Search for articles matching a query
- `wikipedia-summary` — Get a summary/extract of an article
- `wikipedia-geosearch` — Find articles near given coordinates
- `wikipedia-content` — Get full article content (consider truncation for very long articles)

### SNL Tools
- `snl-search` — Search the Norwegian encyclopedia
- `snl-article` — Get a specific article by ID or slug

### Riksantikvaren OGC Tools
- `riksantikvaren-collections` — List available data collections
- `riksantikvaren-features` — Query features from a collection with optional bbox
- `riksantikvaren-feature` — Get a single feature by ID
- `riksantikvaren-nearby` — Find cultural heritage sites near coordinates

### Riksantikvaren ArcGIS Tools
- `arcgis-services` — List available map services
- `arcgis-query` — Query a feature layer with spatial or attribute filters
- `arcgis-identify` — Identify features at a point across layers

---

## Docker + Local Dev

### Dockerfile
- Use multi-stage build for smaller image.
- Base image: `python:3.12-slim`
- Run with `uvicorn` on port `8000`.
- `EXPOSE 8000`
- Include healthcheck.

### docker-compose.yml
- Define service `mcp-server`
- Map `8000:8000`
- Load env from `.env`
- Set restart policy

### .env.example
```bash
# Authentication (leave empty for open/dev mode)
MCP_AUTH_TOKEN=

# Rate limiting
RATE_LIMIT_ENABLED=false
RATE_LIMIT_PER_MINUTE=60

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Timeouts (seconds)
DEFAULT_TIMEOUT=30
GEO_API_TIMEOUT=60

# Server info
SERVER_NAME=kulturarv-mcp-server
SERVER_VERSION=1.0.0
```

---

## README.md must include

1. **What this is** — MCP server for Norwegian cultural heritage APIs
2. **Quick start** — docker compose up
3. **Local development** — python setup with uv or pip
4. **Running tests** — pytest command
5. **Validating with MCP Inspector** — how to test the server
6. **How to add a new API provider:**
   1. Create `docs/apis/<provider>.md` with API documentation
   2. Create `src/tools/<provider>/client.py` and `tools.py`
   3. Add provider to `config/apis.yaml`
7. **Connecting to OpenAI Agent Builder:**
   - Deploy the server (e.g., to Azure, Railway, etc.)
   - In Agent Builder, add MCP Server with your URL
   - Configure authentication if `MCP_AUTH_TOKEN` is set
   - Connect and approve tools
8. **Available tools** — table of all tools with descriptions
9. **Limitations:**
   - In-memory sessions (no horizontal scaling)
   - Single instance only
   - No persistence
   - Session timeout after 30 minutes

---

## docs/MCP.md must include

- Overview of MCP protocol and JSON-RPC 2.0
- The endpoints (`/sse`, `/message`)
- Full example payloads for:
  - `initialize`
  - `tools/list`
  - `tools/call`
- SSE event format
- Error codes and their meanings
- Debugging tips

---

## Validation & Testing

### MCP Inspector
Before connecting to OpenAI Agent Builder, validate using **MCP Inspector**:
```bash
npx @modelcontextprotocol/inspector
```

This tool allows you to:
- Connect to your MCP server
- List available tools
- Test tool invocations
- Debug protocol issues

Include instructions in README for using the inspector.

### pytest Tests

Write tests using `pytest` with `pytest-asyncio`:

#### Core tests
- Health endpoint returns ok
- Root endpoint returns service info
- SSRF blocking works for localhost, private ranges, allows public URLs

#### JSON-RPC protocol tests
- Invalid JSON returns parse error (-32700)
- Missing jsonrpc field returns invalid request (-32600)
- Unknown method returns method not found (-32601)
- Invalid params returns invalid params (-32602)
- `initialize` returns correct capabilities
- `tools/list` returns valid tool definitions with correct schema
- `tools/call` with valid arguments succeeds
- `tools/call` with missing required arguments returns error

#### SSE transport tests
- SSE connection returns endpoint event
- Session ID is generated correctly
- Messages are pushed to correct session

#### Tool tests (mocked HTTP)
Use `respx` or `pytest-httpx` to mock upstream APIs:
- Example tools work correctly
- HTTP errors are handled gracefully
- Timeout handling works
- Response parsing handles malformed JSON

---

## GitHub Actions

Add `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      - name: Run tests
        run: pytest -v --cov=src
      - name: Build Docker image
        run: docker build -t mcp-server .
```

---

## Implementation Notes / Quality Bar

- Keep code clean and modular.
- Use type hints everywhere.
- No unnecessary frameworks or dependencies.
- **Strict JSON-RPC 2.0 compliance** — Agent Builder is picky about this.
- Make error responses consistent and include proper error codes.
- Prefer explicitness over cleverness.
- Use async/await consistently for I/O operations.
- Do not include any fake API integrations beyond the example provider.
- Ensure everything runs end-to-end with `docker compose up` and `pytest`.
- Follow Python best practices (PEP 8, etc.).

---

## Deliverable

Create all files above with full working code and docs.

After generating the repo, output:

1. **Checklist** of what was created
2. **Commands to run locally:**
   - With Docker
   - With Python directly
3. **Example curl commands for:**
   - Health check
   - Initialize session (JSON-RPC)
   - List tools (JSON-RPC)
   - Call a tool (JSON-RPC)
4. **MCP Inspector validation command**
5. **Next steps** — what I need to do to add the real API providers
