# MCP Protocol Documentation

This document describes the Model Context Protocol (MCP) implementation in this server.

## Overview

MCP uses **JSON-RPC 2.0** over HTTP with **Server-Sent Events (SSE)** for streaming. This server implements the remote MCP transport suitable for OpenAI Agent Builder.

**Protocol Version:** `2024-11-05`

## Endpoints

### `GET /sse`

Establishes an SSE connection for the MCP session.

**Response:** SSE stream with events:

```
event: endpoint
data: /message?session_id=abc123-def456

event: ping
data: 

event: message
data: {"jsonrpc":"2.0","id":1,"result":{...}}
```

The `endpoint` event tells the client where to send JSON-RPC messages.

### `POST /message`

Receives JSON-RPC 2.0 messages.

**Query Parameters:**
- `session_id` (optional) — If provided, also pushes response to SSE stream

**Headers:**
- `Content-Type: application/json`
- `Authorization: Bearer <token>` (if auth is enabled)

## JSON-RPC 2.0 Format

### Request

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "method_name",
  "params": {}
}
```

- `jsonrpc` — Must be `"2.0"`
- `id` — Request identifier (omit for notifications)
- `method` — Method name
- `params` — Method parameters (optional, defaults to `{}`)

### Response (Success)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": { ... }
}
```

### Response (Error)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32600,
    "message": "Invalid Request",
    "data": { ... }
  }
}
```

## MCP Methods

### `initialize`

Initialize the MCP session. Should be called first.

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

### `notifications/initialized`

Sent by client after receiving `initialize` response. This is a notification (no `id`), so no response is returned.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "notifications/initialized"
}
```

**Response:** HTTP 202 Accepted (no JSON-RPC response)

### `tools/list`

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
        "name": "example-ping",
        "description": "Returns a simple pong response",
        "inputSchema": {
          "type": "object",
          "properties": {},
          "required": []
        }
      },
      {
        "name": "example-echo",
        "description": "Echoes back the provided message",
        "inputSchema": {
          "type": "object",
          "properties": {
            "message": {
              "type": "string",
              "description": "The message to echo back"
            }
          },
          "required": ["message"]
        }
      }
    ]
  }
}
```

### `tools/call`

Invoke a tool.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "example-echo",
    "arguments": {
      "message": "Hello, World!"
    }
  }
}
```

**Response (Success):**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Echo: Hello, World!"
      }
    ],
    "isError": false
  }
}
```

**Response (Tool Error):**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Error: Could not connect to API"
      }
    ],
    "isError": true
  }
}
```

Note: Tool errors return `isError: true` in the result, not a JSON-RPC error. JSON-RPC errors are for protocol-level issues.

## Error Codes

### Standard JSON-RPC 2.0 Errors

| Code | Message | Description |
|------|---------|-------------|
| -32700 | Parse error | Invalid JSON |
| -32600 | Invalid Request | Not a valid JSON-RPC request |
| -32601 | Method not found | Unknown method |
| -32602 | Invalid params | Invalid method parameters |
| -32603 | Internal error | Server internal error |

### Custom Errors (Server-Defined)

| Code | Message | Description |
|------|---------|-------------|
| -32000 | Tool execution error | Tool failed during execution |
| -32001 | Authentication required | Missing or invalid auth token |
| -32002 | Rate limit exceeded | Too many requests |

## SSE Events

### `endpoint`

Sent immediately after SSE connection is established:

```
event: endpoint
data: /message?session_id=abc123-def456
```

### `message`

JSON-RPC response pushed to the stream:

```
event: message
data: {"jsonrpc":"2.0","id":3,"result":{...}}
```

### `ping`

Keepalive event (every 30 seconds):

```
event: ping
data: 
```

### `error`

Error notification:

```
event: error
data: {"code":-32603,"message":"Internal error"}
```

## Content Types

Tool responses return content in these formats:

### TextContent

```json
{
  "type": "text",
  "text": "The content as plain text"
}
```

### ImageContent

```json
{
  "type": "image",
  "data": "base64-encoded-image-data",
  "mimeType": "image/png"
}
```

## Debugging

### curl Examples

**Initialize:**
```bash
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

**List Tools:**
```bash
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

**Call Tool:**
```bash
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"example-ping","arguments":{}}}'
```

**SSE Stream:**
```bash
curl -N http://localhost:8000/sse
```

### MCP Inspector

Use the official MCP Inspector to test your server:

```bash
npx @modelcontextprotocol/inspector
```

Enter your server URL and interactively test tools.

## References

- [MCP Specification](https://modelcontextprotocol.io/specification)
- [JSON-RPC 2.0 Specification](https://www.jsonrpc.org/specification)
- [OpenAI MCP Documentation](https://platform.openai.com/docs/mcp)

