"""Session lifecycle decorators for MCP tools."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

# Marker attributes for session decorators
MCP_SESSION_INIT_MARKER = "_auto_mcp_session_init"
MCP_SESSION_CLEANUP_MARKER = "_auto_mcp_session_cleanup"


def mcp_session_init(
    order: int = 0,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Mark a function as a session initialization hook.

    Session init hooks are called after a session is created.
    They receive the SessionContext and can set up session state.

    Args:
        order: Execution order (lower numbers run first). Default is 0.

    Returns:
        Decorator function

    Example:
        >>> from auto_mcp import mcp_session_init, SessionContext
        >>>
        >>> @mcp_session_init(order=0)
        ... def init_database(session: SessionContext) -> None:
        ...     '''Initialize database connection for session.'''
        ...     session.data.set("db", create_connection())
        >>>
        >>> @mcp_session_init(order=1)
        ... def init_cache(session: SessionContext) -> None:
        ...     '''Initialize cache after database.'''
        ...     db = session.data.get("db")
        ...     session.data.set("cache", Cache(db))
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        setattr(
            func,
            MCP_SESSION_INIT_MARKER,
            {
                "order": order,
            },
        )
        return func

    return decorator


def mcp_session_cleanup(
    order: int = 0,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Mark a function as a session cleanup hook.

    Session cleanup hooks are called before a session is destroyed.
    They receive the SessionContext and can clean up session resources.

    Note: Cleanup hooks run in reverse order (higher numbers run first).

    Args:
        order: Execution order (higher numbers run first in cleanup). Default is 0.

    Returns:
        Decorator function

    Example:
        >>> from auto_mcp import mcp_session_cleanup, SessionContext
        >>>
        >>> @mcp_session_cleanup(order=0)
        ... def cleanup_database(session: SessionContext) -> None:
        ...     '''Close database connection.'''
        ...     db = session.data.get("db")
        ...     if db:
        ...         db.close()
        >>>
        >>> @mcp_session_cleanup(order=1)
        ... def cleanup_cache(session: SessionContext) -> None:
        ...     '''Flush cache before database closes.'''
        ...     cache = session.data.get("cache")
        ...     if cache:
        ...         cache.flush()
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        setattr(
            func,
            MCP_SESSION_CLEANUP_MARKER,
            {
                "order": order,
            },
        )
        return func

    return decorator


def get_session_hook_metadata(func: Callable[..., Any]) -> dict[str, Any]:
    """Get session hook metadata from a decorated function.

    Args:
        func: The function to inspect

    Returns:
        Dictionary with session hook metadata
    """
    return {
        "is_session_init": hasattr(func, MCP_SESSION_INIT_MARKER),
        "is_session_cleanup": hasattr(func, MCP_SESSION_CLEANUP_MARKER),
        "session_init_meta": getattr(func, MCP_SESSION_INIT_MARKER, None),
        "session_cleanup_meta": getattr(func, MCP_SESSION_CLEANUP_MARKER, None),
    }
