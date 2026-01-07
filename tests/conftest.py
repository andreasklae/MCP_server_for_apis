"""Pytest configuration and fixtures."""

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from src.main import app
from src.mcp.registry import get_registry, reset_registry
from src.config.loader import get_settings


@pytest.fixture
def client():
    """Synchronous test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
async def async_client():
    """Async test client for FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def reset_global_registry():
    """Reset the global tool registry before each test and reload example tools."""
    reset_registry()
    # Reload the example provider so tools are available
    registry = get_registry()
    registry.load_provider("example")
    yield
    reset_registry()


@pytest.fixture
def registry():
    """Get a fresh tool registry."""
    reset_registry()
    return get_registry()


@pytest.fixture
def settings():
    """Get application settings."""
    return get_settings()


@pytest.fixture
def sample_jsonrpc_request():
    """Sample JSON-RPC request factory."""
    def _make_request(method: str, params: dict = None, id: int = 1):
        return {
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params or {},
        }
    return _make_request

