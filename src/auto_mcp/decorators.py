"""Decorators for customizing MCP exposure behavior."""

from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

# Marker attributes for decorated functions
MCP_TOOL_MARKER = "_auto_mcp_tool"
MCP_EXCLUDE_MARKER = "_auto_mcp_exclude"
MCP_RESOURCE_MARKER = "_auto_mcp_resource"
MCP_PROMPT_MARKER = "_auto_mcp_prompt"

# Re-export session markers for convenience
from auto_mcp.session.decorators import (  # noqa: E402
    MCP_SESSION_CLEANUP_MARKER,
    MCP_SESSION_INIT_MARKER,
)


def mcp_tool(
    name: str | None = None,
    description: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Mark a function as an MCP tool with optional custom name and description.

    Args:
        name: Custom name for the tool (defaults to function name)
        description: Custom description (overrides LLM-generated description)

    Example:
        @mcp_tool(name="add_numbers", description="Add two integers together")
        def add(a: int, b: int) -> int:
            return a + b
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        setattr(func, MCP_TOOL_MARKER, {"name": name, "description": description})
        return func

    return decorator


def mcp_exclude(func: Callable[P, R]) -> Callable[P, R]:
    """Mark a function to be excluded from MCP exposure.

    Use this for helper functions that should not be exposed as tools.

    Example:
        @mcp_exclude
        def internal_helper():
            pass
    """
    setattr(func, MCP_EXCLUDE_MARKER, True)
    return func


def mcp_resource(
    uri: str,
    name: str | None = None,
    description: str | None = None,
    mime_type: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Mark a function as an MCP resource.

    Args:
        uri: URI template for the resource (e.g., "data://mydata/{id}")
        name: Custom name for the resource
        description: Custom description (overrides LLM-generated description)
        mime_type: MIME type of the resource content

    Example:
        @mcp_resource(uri="file://documents/{name}", mime_type="text/plain")
        def read_document(name: str) -> str:
            return f"Content of {name}"
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        setattr(
            func,
            MCP_RESOURCE_MARKER,
            {
                "uri": uri,
                "name": name,
                "description": description,
                "mime_type": mime_type,
            },
        )
        return func

    return decorator


def mcp_prompt(
    name: str | None = None,
    description: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Mark a function as an MCP prompt template.

    The function should return a string that will be used as the prompt template.

    Args:
        name: Custom name for the prompt
        description: Custom description

    Example:
        @mcp_prompt(name="greeting")
        def greeting_prompt(name: str, style: str = "friendly") -> str:
            return f"Please write a {style} greeting for {name}."
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        setattr(func, MCP_PROMPT_MARKER, {"name": name, "description": description})
        return func

    return decorator


def get_mcp_metadata(func: Callable[..., Any]) -> dict[str, Any]:
    """Get MCP metadata from a decorated function.

    Returns:
        Dictionary with keys: is_tool, is_excluded, is_resource, is_prompt,
        session hook info, and their respective metadata.
    """
    return {
        "is_tool": hasattr(func, MCP_TOOL_MARKER),
        "is_excluded": hasattr(func, MCP_EXCLUDE_MARKER),
        "is_resource": hasattr(func, MCP_RESOURCE_MARKER),
        "is_prompt": hasattr(func, MCP_PROMPT_MARKER),
        "is_session_init": hasattr(func, MCP_SESSION_INIT_MARKER),
        "is_session_cleanup": hasattr(func, MCP_SESSION_CLEANUP_MARKER),
        "tool_meta": getattr(func, MCP_TOOL_MARKER, None),
        "resource_meta": getattr(func, MCP_RESOURCE_MARKER, None),
        "prompt_meta": getattr(func, MCP_PROMPT_MARKER, None),
        "session_init_meta": getattr(func, MCP_SESSION_INIT_MARKER, None),
        "session_cleanup_meta": getattr(func, MCP_SESSION_CLEANUP_MARKER, None),
    }
