"""Tests for health and info endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient):
    """Test that health endpoint returns ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_endpoint(client: TestClient):
    """Test that root endpoint returns server info."""
    response = client.get("/")
    assert response.status_code == 200
    
    data = response.json()
    assert "name" in data
    assert "version" in data
    assert "endpoints" in data
    assert data["endpoints"]["health"] == "/health"
    assert data["endpoints"]["sse"] == "/sse"
    assert data["endpoints"]["message"] == "/message"


def test_root_endpoint_has_mcp_version(client: TestClient):
    """Test that root endpoint includes MCP protocol version."""
    response = client.get("/")
    data = response.json()
    assert "mcp_protocol_version" in data
    assert data["mcp_protocol_version"] == "2024-11-05"

