"""Session lifecycle support for MCP servers.

This module provides session management capabilities for auto-mcp,
allowing tools to maintain state across multiple requests.

Example:
    >>> from auto_mcp import AutoMCP, SessionContext, mcp_session_init
    >>>
    >>> @mcp_session_init()
    ... def init_session(session: SessionContext) -> None:
    ...     session.data.set("counter", 0)
    >>>
    >>> def increment(session: SessionContext, amount: int = 1) -> int:
    ...     '''Increment the session counter.'''
    ...     current = session.data.get("counter", 0)
    ...     session.data.set("counter", current + amount)
    ...     return session.data.get("counter")
    >>>
    >>> # Generate server with sessions enabled
    >>> auto = AutoMCP(enable_sessions=True)
    >>> server = auto.create_server([my_module])
"""

from auto_mcp.session.context import SessionContext, SessionData
from auto_mcp.session.decorators import (
    MCP_SESSION_CLEANUP_MARKER,
    MCP_SESSION_INIT_MARKER,
    get_session_hook_metadata,
    mcp_session_cleanup,
    mcp_session_init,
)
from auto_mcp.session.injection import (
    get_non_session_parameters,
    get_session_param_name,
    needs_session_injection,
)
from auto_mcp.session.manager import (
    SessionConfig,
    SessionManager,
    get_default_session_manager,
    set_default_session_manager,
)

__all__ = [
    # Context
    "SessionContext",
    "SessionData",
    # Manager
    "SessionConfig",
    "SessionManager",
    "get_default_session_manager",
    "set_default_session_manager",
    # Decorators
    "mcp_session_init",
    "mcp_session_cleanup",
    "get_session_hook_metadata",
    "MCP_SESSION_INIT_MARKER",
    "MCP_SESSION_CLEANUP_MARKER",
    # Injection utilities
    "needs_session_injection",
    "get_session_param_name",
    "get_non_session_parameters",
]
