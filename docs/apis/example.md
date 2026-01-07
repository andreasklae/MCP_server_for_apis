# Example Provider

## Overview
This is a minimal example provider demonstrating the tool implementation pattern. It does not call any external APIs.

## Tools

### example.ping
Returns a simple pong response.

**Input:** None

**Output:**
```json
{
  "pong": true
}
```

### example.echo
Echoes back the provided input.

**Input:**
```json
{
  "message": "Hello, world!"
}
```

**Output:**
```json
{
  "echo": "Hello, world!"
}
```

## Purpose
This provider serves as a template for implementing real API providers. Use it to:
1. Verify the MCP server is working
2. Understand the tool implementation pattern
3. Test the tool registry and invocation flow

