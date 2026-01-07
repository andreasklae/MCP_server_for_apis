"""Example provider client - no external API calls needed."""

# This is a placeholder to demonstrate the provider pattern.
# Real providers would have HTTP client code here.


class ExampleClient:
    """Client for the example provider (no external calls)."""
    
    async def ping(self) -> dict:
        """Return a pong response."""
        return {"pong": True}
    
    async def echo(self, message: str) -> dict:
        """Echo back a message."""
        return {"echo": message}


# Singleton client instance
_client: ExampleClient | None = None


def get_client() -> ExampleClient:
    """Get the example client instance."""
    global _client
    if _client is None:
        _client = ExampleClient()
    return _client

