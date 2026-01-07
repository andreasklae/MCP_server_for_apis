"""SSE (Server-Sent Events) transport for MCP."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator

from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

# Session timeout (30 minutes)
SESSION_TIMEOUT = timedelta(minutes=30)


class Session:
    """An MCP session with SSE event queue."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._closed = False

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.utcnow()

    def is_expired(self) -> bool:
        """Check if the session has expired."""
        return datetime.utcnow() - self.last_activity > SESSION_TIMEOUT

    async def send_event(self, event_type: str, data: Any) -> None:
        """Queue an event to be sent to the client."""
        if not self._closed:
            await self.queue.put({"event": event_type, "data": data})

    def close(self) -> None:
        """Mark the session as closed."""
        self._closed = True


class SessionManager:
    """Manages MCP sessions."""

    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._cleanup_task: asyncio.Task | None = None

    def create_session(self) -> Session:
        """Create a new session."""
        session_id = str(uuid.uuid4())
        session = Session(session_id)
        self._sessions[session_id] = session
        logger.info(f"Created session: {session_id}")
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        session = self._sessions.get(session_id)
        if session is not None:
            if session.is_expired():
                self.remove_session(session_id)
                return None
            session.touch()
        return session

    def remove_session(self, session_id: str) -> None:
        """Remove a session."""
        session = self._sessions.pop(session_id, None)
        if session:
            session.close()
            logger.info(f"Removed session: {session_id}")

    async def cleanup_expired(self) -> None:
        """Remove expired sessions."""
        expired = [
            sid for sid, session in self._sessions.items() if session.is_expired()
        ]
        for sid in expired:
            self.remove_session(sid)
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")

    async def start_cleanup_task(self) -> None:
        """Start background task to clean up expired sessions."""
        async def cleanup_loop():
            while True:
                await asyncio.sleep(60)  # Check every minute
                await self.cleanup_expired()

        self._cleanup_task = asyncio.create_task(cleanup_loop())

    def stop_cleanup_task(self) -> None:
        """Stop the cleanup background task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None

    @property
    def session_count(self) -> int:
        """Return the number of active sessions."""
        return len(self._sessions)


# Global session manager
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Get the global session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


async def create_sse_response(
    session: Session, message_endpoint: str
) -> EventSourceResponse:
    """Create an SSE response for a session."""

    async def event_generator() -> AsyncGenerator[dict[str, Any], None]:
        # Send initial endpoint event
        yield {
            "event": "endpoint",
            "data": f"{message_endpoint}?session_id={session.session_id}",
        }

        # Stream events from session queue
        try:
            while not session._closed:
                try:
                    event = await asyncio.wait_for(
                        session.queue.get(), timeout=30.0
                    )
                    yield event
                except asyncio.TimeoutError:
                    # Send keepalive ping
                    yield {"event": "ping", "data": ""}
        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled for session {session.session_id}")
        finally:
            session.close()

    return EventSourceResponse(event_generator())

