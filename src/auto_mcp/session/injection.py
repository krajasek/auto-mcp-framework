"""Session injection utilities for detecting and injecting SessionContext."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, get_type_hints

from auto_mcp.session.context import SessionContext


def needs_session_injection(func: Callable[..., Any]) -> bool:
    """Check if a function declares a SessionContext parameter.

    Args:
        func: The function to check

    Returns:
        True if function has a SessionContext parameter
    """
    return get_session_param_name(func) is not None


def get_session_param_name(func: Callable[..., Any]) -> str | None:
    """Get the name of the SessionContext parameter, if any.

    Args:
        func: The function to inspect

    Returns:
        Parameter name if found, None otherwise
    """
    try:
        hints = get_type_hints(func)
    except Exception:
        # get_type_hints can fail for various reasons
        hints = {}

    # Check type hints first
    for name, type_hint in hints.items():
        if type_hint is SessionContext:
            return name
        # Handle Optional[SessionContext] or SessionContext | None
        if hasattr(type_hint, "__origin__"):
            args = getattr(type_hint, "__args__", ())
            if SessionContext in args:
                return name

    # Fallback: check parameter annotations directly
    sig = inspect.signature(func)
    for name, param in sig.parameters.items():
        if param.annotation is SessionContext:
            return name
        # Check string annotation
        if isinstance(param.annotation, str) and "SessionContext" in param.annotation:
            return name

    return None


def get_non_session_parameters(func: Callable[..., Any]) -> list[str]:
    """Get parameter names excluding SessionContext and self/cls.

    Args:
        func: The function to inspect

    Returns:
        List of parameter names that should be in the tool schema
    """
    session_param = get_session_param_name(func)
    sig = inspect.signature(func)

    return [
        name
        for name in sig.parameters
        if name not in ("self", "cls") and name != session_param
    ]
