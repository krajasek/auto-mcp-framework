"""Session context and data classes for MCP session management."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from auto_mcp.session.manager import SessionManager


@dataclass
class SessionData:
    """Mutable key-value storage for session state.

    Provides a simple dictionary-like interface for storing arbitrary
    session data. Thread-safe for concurrent access.

    Example:
        >>> data = SessionData()
        >>> data.set("user_id", 123)
        >>> data.get("user_id")
        123
        >>> data.delete("user_id")
        True
        >>> data.get("user_id", "default")
        'default'
    """

    _data: dict[str, Any] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from session data.

        Args:
            key: The key to look up
            default: Value to return if key not found

        Returns:
            The stored value or default
        """
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a value in session data.

        Args:
            key: The key to set
            value: The value to store
        """
        with self._lock:
            self._data[key] = value

    def delete(self, key: str) -> bool:
        """Delete a key from session data.

        Args:
            key: The key to delete

        Returns:
            True if key existed and was deleted, False otherwise
        """
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all session data."""
        with self._lock:
            self._data.clear()

    def keys(self) -> list[str]:
        """Get all keys in session data.

        Returns:
            List of all keys
        """
        with self._lock:
            return list(self._data.keys())

    def items(self) -> list[tuple[str, Any]]:
        """Get all key-value pairs in session data.

        Returns:
            List of (key, value) tuples
        """
        with self._lock:
            return list(self._data.items())

    def __contains__(self, key: str) -> bool:
        """Check if key exists in session data."""
        with self._lock:
            return key in self._data

    def contains(self, key: str) -> bool:
        """Check if key exists in session data.

        Args:
            key: The key to check

        Returns:
            True if key exists, False otherwise
        """
        return key in self

    def __len__(self) -> int:
        """Get number of items in session data."""
        with self._lock:
            return len(self._data)


@dataclass
class SessionContext:
    """Context object passed to session-aware tools.

    SessionContext provides access to session state and metadata.
    It is automatically injected into tools that declare a
    `session: SessionContext` parameter.

    Attributes:
        session_id: Unique identifier (handle) for this session
        created_at: Unix timestamp when session was created
        metadata: Immutable session metadata (e.g., client info)
        data: Mutable session data storage

    Example:
        >>> # In a session-aware tool:
        >>> def my_tool(session: SessionContext, arg: str) -> str:
        ...     # Store data in session
        ...     session.data.set("last_arg", arg)
        ...     # Access session info
        ...     print(f"Session {session.session_id} age: {session.age_seconds}s")
        ...     return f"Processed {arg}"
    """

    session_id: str
    created_at: float
    metadata: dict[str, Any] = field(default_factory=dict)
    data: SessionData = field(default_factory=SessionData)
    _manager: SessionManager | None = field(default=None, repr=False, compare=False)

    @property
    def age_seconds(self) -> float:
        """Time since session creation in seconds.

        Returns:
            Number of seconds since session was created
        """
        return time.time() - self.created_at

    def refresh(self) -> bool:
        """Extend session TTL.

        Resets the session's expiration timer to the configured TTL.

        Returns:
            True if session was refreshed, False if no manager or refresh failed
        """
        if self._manager:
            return self._manager.refresh_session(self.session_id)
        return False

    def invalidate(self) -> None:
        """Mark session for closure.

        Schedules the session to be closed. This is a non-blocking operation
        that triggers cleanup hooks asynchronously.
        """
        if self._manager:
            import asyncio

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._manager.close_session(self.session_id))
            except RuntimeError:
                # No running loop, run synchronously
                asyncio.run(self._manager.close_session(self.session_id))
