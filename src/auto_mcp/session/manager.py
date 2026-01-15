"""Session manager for MCP session lifecycle."""

from __future__ import annotations

import asyncio
import logging
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from auto_mcp.session.context import SessionContext, SessionData

logger = logging.getLogger(__name__)


@dataclass
class SessionConfig:
    """Configuration for session management.

    Attributes:
        default_ttl: Default session TTL in seconds (3600 = 1 hour).
            Set to 0 for sessions that never expire (use with caution).
        max_sessions: Maximum concurrent sessions (100)
        auto_cleanup_interval: Seconds between automatic cleanups (60)
        session_id_prefix: Prefix for session handles ("session:")
        handle_length: Deprecated - session IDs now use fixed 128-bit entropy
        max_metadata_keys: Maximum number of metadata keys per session (50)
        max_metadata_value_size: Maximum size of each metadata value in bytes (10000)
    """

    default_ttl: int = 3600
    max_sessions: int = 100
    auto_cleanup_interval: int = 60
    session_id_prefix: str = "session:"
    handle_length: int = 12  # Deprecated: kept for backward compatibility
    max_metadata_keys: int = 50
    max_metadata_value_size: int = 10000


@dataclass
class StoredSession:
    """Internal container for a stored session.

    Attributes:
        context: The SessionContext object
        expires_at: Unix timestamp when session expires (0 = never)
        created_at: Unix timestamp when session was created
    """

    context: SessionContext
    expires_at: float
    created_at: float

    @property
    def is_expired(self) -> bool:
        """Check if this session has expired."""
        if self.expires_at == 0:
            return False
        return time.time() > self.expires_at


class SessionManager:
    """Manages MCP session lifecycles.

    The SessionManager handles session creation, retrieval, and cleanup.
    It supports init/cleanup hooks that run when sessions are created/closed.

    Example:
        >>> manager = SessionManager()
        >>>
        >>> # Create a session
        >>> session = await manager.create_session({"user": "test"})
        >>> print(session.session_id)  # "session:abc123def456"
        >>>
        >>> # Retrieve session in a tool
        >>> session = manager.get_session("session:abc123def456")
        >>> session.data.set("counter", 1)
        >>>
        >>> # Close session
        >>> await manager.close_session("session:abc123def456")
    """

    def __init__(
        self,
        config: SessionConfig | None = None,
    ) -> None:
        """Initialize the session manager.

        Args:
            config: Optional session configuration
        """
        self.config = config or SessionConfig()

        self._sessions: dict[str, StoredSession] = {}
        self._lock = threading.RLock()

        # Hooks: list of (order, callable)
        self._init_hooks: list[tuple[int, Callable[..., Any]]] = []
        self._cleanup_hooks: list[tuple[int, Callable[..., Any]]] = []

        self._last_cleanup = time.time()
        self._total_created = 0
        self._total_closed = 0

    def _validate_metadata(
        self,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Validate and sanitize session metadata.

        Args:
            metadata: The metadata to validate

        Returns:
            A validated copy of the metadata

        Raises:
            ValueError: If metadata exceeds size limits
            TypeError: If metadata is not a dict
        """
        if metadata is None:
            return {}

        if not isinstance(metadata, dict):
            raise TypeError(f"Metadata must be a dict, got {type(metadata).__name__}")

        if len(metadata) > self.config.max_metadata_keys:
            raise ValueError(
                f"Metadata exceeds maximum key count "
                f"({len(metadata)} > {self.config.max_metadata_keys})"
            )

        validated = {}
        for key, value in metadata.items():
            if not isinstance(key, str):
                raise TypeError(f"Metadata keys must be strings, got {type(key).__name__}")

            # Check value size (convert to string for size estimation)
            try:
                value_str = str(value)
                if len(value_str) > self.config.max_metadata_value_size:
                    raise ValueError(
                        f"Metadata value for '{key}' exceeds maximum size "
                        f"({len(value_str)} > {self.config.max_metadata_value_size})"
                    )
            except Exception as e:
                if isinstance(e, ValueError):
                    raise
                # If we can't convert to string, it might be too complex
                raise ValueError(
                    f"Metadata value for '{key}' is not serializable: {e}"
                ) from e

            validated[key] = value

        return validated

    async def create_session(
        self,
        metadata: dict[str, Any] | None = None,
        ttl: int | None = None,
    ) -> SessionContext:
        """Create a new session and run init hooks.

        Args:
            metadata: Optional session metadata (immutable after creation)
            ttl: Optional TTL override in seconds

        Returns:
            The created SessionContext

        Raises:
            ValueError: If maximum sessions reached or metadata invalid
            TypeError: If metadata has invalid types
        """
        # Validate metadata before acquiring lock
        validated_metadata = self._validate_metadata(metadata)

        with self._lock:
            # Maybe cleanup expired sessions
            self._maybe_cleanup()

            # Check capacity
            active_count = len(self._sessions)
            if active_count >= self.config.max_sessions:
                raise ValueError(
                    f"Maximum sessions ({self.config.max_sessions}) reached"
                )

            # Generate session ID
            session_id = self._generate_session_id()

            # Calculate expiration
            effective_ttl = ttl if ttl is not None else self.config.default_ttl
            expires_at = time.time() + effective_ttl if effective_ttl > 0 else 0

            # Create context
            context = SessionContext(
                session_id=session_id,
                created_at=time.time(),
                metadata=validated_metadata,
                data=SessionData(),
                _manager=self,
            )

            # Store session
            stored = StoredSession(
                context=context,
                expires_at=expires_at,
                created_at=context.created_at,
            )
            self._sessions[session_id] = stored
            self._total_created += 1

            logger.debug(f"Created session {session_id}")

        # Run init hooks outside lock to avoid deadlock
        sorted_hooks = sorted(self._init_hooks, key=lambda x: x[0])
        for _, hook in sorted_hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(context)
                else:
                    hook(context)
            except Exception as e:
                logger.error(f"Session init hook failed: {e}")

        return context

    async def close_session(self, session_id: str) -> bool:
        """Close a session after running cleanup hooks.

        Args:
            session_id: The session ID to close

        Returns:
            True if session was closed, False if not found
        """
        with self._lock:
            if session_id not in self._sessions:
                return False

            stored = self._sessions[session_id]
            context = stored.context

        # Run cleanup hooks in reverse order (outside lock)
        sorted_hooks = sorted(self._cleanup_hooks, key=lambda x: -x[0])
        for _, hook in sorted_hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(context)
                else:
                    hook(context)
            except Exception as e:
                logger.error(f"Session cleanup hook failed: {e}")

        # Remove session
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                self._total_closed += 1
                logger.debug(f"Closed session {session_id}")

        return True

    def get_session(self, session_id: str) -> SessionContext:
        """Get a session by ID.

        Args:
            session_id: The session ID

        Returns:
            The SessionContext

        Raises:
            KeyError: If session not found
            ValueError: If session has expired
        """
        with self._lock:
            # Trigger periodic cleanup on access to prevent memory leaks
            # in sync apps that don't create many sessions
            self._maybe_cleanup()

            if session_id not in self._sessions:
                raise KeyError(f"Session not found: {session_id}")

            stored = self._sessions[session_id]

            if stored.is_expired:
                # Remove expired session immediately within the lock to prevent
                # race conditions where another thread could access it
                del self._sessions[session_id]
                self._total_closed += 1
                logger.debug(f"Removed expired session {session_id}")
                raise ValueError(f"Session has expired: {session_id}")

            return stored.context

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists and is not expired.

        Args:
            session_id: The session ID

        Returns:
            True if session exists and is valid
        """
        with self._lock:
            if session_id not in self._sessions:
                return False

            stored = self._sessions[session_id]
            return not stored.is_expired

    def list_sessions(self) -> list[str]:
        """List all active session IDs.

        Returns:
            List of session ID strings
        """
        with self._lock:
            self._maybe_cleanup()
            return [
                sid for sid, stored in self._sessions.items()
                if not stored.is_expired
            ]

    def count(self) -> int:
        """Count active sessions.

        Returns:
            Number of active sessions
        """
        return len(self.list_sessions())

    @property
    def session_count(self) -> int:
        """Count active sessions (property alias for count()).

        Returns:
            Number of active sessions
        """
        return self.count()

    def refresh_session(self, session_id: str, ttl: int | None = None) -> bool:
        """Extend a session's TTL.

        Args:
            session_id: The session ID
            ttl: Optional new TTL in seconds (uses default if not specified)

        Returns:
            True if session was refreshed, False if not found
        """
        with self._lock:
            if session_id not in self._sessions:
                return False

            stored = self._sessions[session_id]

            if stored.is_expired:
                return False

            effective_ttl = ttl if ttl is not None else self.config.default_ttl
            stored.expires_at = time.time() + effective_ttl if effective_ttl > 0 else 0

            logger.debug(f"Refreshed session {session_id}")
            return True

    def register_init_hook(
        self,
        hook: Callable[..., Any],
        order: int = 0,
    ) -> None:
        """Register a session initialization hook.

        Hooks are called after session is created, in order (ascending).

        Args:
            hook: Function that receives SessionContext
            order: Execution order (lower runs first)
        """
        self._init_hooks.append((order, hook))
        logger.debug(f"Registered init hook: {hook.__name__} (order={order})")

    def register_cleanup_hook(
        self,
        hook: Callable[..., Any],
        order: int = 0,
    ) -> None:
        """Register a session cleanup hook.

        Hooks are called before session is destroyed, in reverse order (descending).

        Args:
            hook: Function that receives SessionContext
            order: Execution order (higher runs first during cleanup)
        """
        self._cleanup_hooks.append((order, hook))
        logger.debug(f"Registered cleanup hook: {hook.__name__} (order={order})")

    def get_stats(self) -> dict[str, Any]:
        """Get session statistics.

        Returns:
            Dictionary with session stats
        """
        with self._lock:
            active = len([s for s in self._sessions.values() if not s.is_expired])
            expired = len([s for s in self._sessions.values() if s.is_expired])

            return {
                "active_sessions": active,
                "expired_sessions": expired,
                "max_sessions": self.config.max_sessions,
                "total_created": self._total_created,
                "total_closed": self._total_closed,
                "init_hooks": len(self._init_hooks),
                "cleanup_hooks": len(self._cleanup_hooks),
            }

    async def cleanup(self) -> int:
        """Remove all expired sessions (running cleanup hooks).

        Returns:
            Number of sessions removed
        """
        with self._lock:
            expired_ids = [
                sid for sid, stored in self._sessions.items()
                if stored.is_expired
            ]

        count = 0
        for session_id in expired_ids:
            if await self.close_session(session_id):
                count += 1

        self._last_cleanup = time.time()
        if count:
            logger.debug(f"Cleaned up {count} expired sessions")

        return count

    async def clear(self) -> int:
        """Close all sessions.

        Returns:
            Number of sessions closed
        """
        with self._lock:
            session_ids = list(self._sessions.keys())

        count = 0
        for session_id in session_ids:
            if await self.close_session(session_id):
                count += 1

        return count

    def _generate_session_id(self) -> str:
        """Generate a cryptographically secure unique session ID.

        Uses 128 bits of entropy (16 bytes) to ensure collision resistance.
        The resulting ID format is: "{prefix}{random_hex}"

        Returns:
            A unique session ID string with 128 bits of entropy
        """
        # Use 16 bytes (128 bits) of entropy for security
        # This provides collision resistance up to 2^64 sessions
        random_part = secrets.token_hex(16)
        session_id = f"{self.config.session_id_prefix}{random_part}"

        # Ensure uniqueness (extremely unlikely to loop with 128-bit entropy)
        while session_id in self._sessions:
            random_part = secrets.token_hex(16)
            session_id = f"{self.config.session_id_prefix}{random_part}"

        return session_id

    def _maybe_cleanup(self) -> None:
        """Run cleanup if enough time has passed.

        In async contexts, schedules cleanup as a background task.
        In sync contexts, runs synchronous cleanup immediately.
        """
        if time.time() - self._last_cleanup > self.config.auto_cleanup_interval:
            # Schedule async cleanup
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(self.cleanup())
                # Add error handler to log cleanup failures
                task.add_done_callback(self._handle_cleanup_result)
            except RuntimeError:
                # No running loop, do synchronous removal without hooks
                self._sync_cleanup()

    def _handle_cleanup_result(self, task: asyncio.Task[int]) -> None:
        """Handle the result of an async cleanup task.

        Logs any errors that occurred during cleanup.
        """
        try:
            task.result()
        except Exception as e:
            logger.error(f"Async session cleanup failed: {e}")

    def _sync_cleanup(self) -> int:
        """Synchronous cleanup without running hooks (emergency cleanup).

        Returns:
            Number of sessions removed
        """
        with self._lock:
            expired_ids = [
                sid for sid, stored in self._sessions.items()
                if stored.is_expired
            ]

            for session_id in expired_ids:
                del self._sessions[session_id]
                self._total_closed += 1

            self._last_cleanup = time.time()
            return len(expired_ids)



# Global default session manager
_default_manager: SessionManager | None = None


def get_default_session_manager() -> SessionManager:
    """Get the default global session manager.

    Returns:
        The default SessionManager instance
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = SessionManager()
    return _default_manager


def set_default_session_manager(manager: SessionManager) -> None:
    """Set the default global session manager.

    Args:
        manager: The manager to use as default
    """
    global _default_manager
    _default_manager = manager
