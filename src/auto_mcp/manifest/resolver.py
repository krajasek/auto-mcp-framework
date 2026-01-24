"""Pattern resolver for manifest tool specifications.

This module resolves manifest patterns (simple names, dot paths, class names,
method names, globs) to actual callable objects.
"""

from __future__ import annotations

import fnmatch
import inspect
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Callable


@dataclass
class ResolvedTool:
    """A resolved tool with its callable and metadata."""

    callable_obj: Callable[..., Any]
    name: str  # Display name for the tool
    qualified_name: str  # Full qualified name (e.g., "DataFrame.to_csv")
    class_name: str | None = None  # Class name if this is a method
    is_constructor: bool = False  # Whether this is a class constructor
    is_method: bool = False  # Whether this is an instance method
    is_static_method: bool = False  # Whether this is a static method
    is_class_method: bool = False  # Whether this is a class method
    custom_name: str | None = None  # User-provided rename
    custom_description: str | None = None  # User-provided description
    auto_included: bool = False  # Whether this was auto-included for dependencies

    def get_tool_name(self) -> str:
        """Get the final tool name for MCP registration."""
        if self.custom_name:
            return self.custom_name
        # Convert dots to underscores for method names
        return self.name.replace(".", "_").lower()


class PatternResolver:
    """Resolves manifest patterns to actual callables."""

    def __init__(self, module: ModuleType) -> None:
        """Initialize the resolver.

        Args:
            module: The module to resolve patterns against
        """
        self.module = module
        self.module_name = module.__name__

    def resolve(
        self,
        pattern: str,
        custom_name: str | None = None,
        custom_description: str | None = None,
    ) -> list[ResolvedTool]:
        """Resolve a pattern to list of tools.

        Handles:
        - Simple names: 'read_csv' -> module.read_csv
        - Dotted paths: 'pandas.io.sql.read_sql'
        - Class names: 'DataFrame' -> all methods
        - Method names: 'DataFrame.to_csv'
        - Globs: 'DataFrame.to_*', 'pandas.io.*.read_*'

        Args:
            pattern: The pattern to resolve
            custom_name: Optional custom name for the tool
            custom_description: Optional custom description

        Returns:
            List of resolved tools
        """
        pattern = pattern.strip()

        if "*" in pattern:
            return self._resolve_glob(pattern, custom_name, custom_description)

        # Check if pattern refers to a class
        if self._is_class_pattern(pattern):
            return self._resolve_class(pattern, custom_name, custom_description)

        # Check if pattern is a method reference (Class.method)
        if "." in pattern and self._is_method_pattern(pattern):
            return self._resolve_method(pattern, custom_name, custom_description)

        # Otherwise, treat as a function
        return self._resolve_function(pattern, custom_name, custom_description)

    def _is_class_pattern(self, pattern: str) -> bool:
        """Check if pattern refers to a class (not a method)."""
        # If there's no dot, check if it's a class in the module
        if "." not in pattern:
            obj = self._get_attribute(pattern)
            return obj is not None and inspect.isclass(obj)

        # With dots, check the last part
        parts = pattern.rsplit(".", 1)
        if len(parts) == 2:
            parent_name, last_part = parts
            parent = self._get_attribute(parent_name)
            if parent is not None:
                obj = getattr(parent, last_part, None)
                return obj is not None and inspect.isclass(obj)

        return False

    def _is_method_pattern(self, pattern: str) -> bool:
        """Check if pattern refers to a method (Class.method format)."""
        if "." not in pattern:
            return False

        parts = pattern.rsplit(".", 1)
        if len(parts) != 2:
            return False

        class_name, method_name = parts

        # Get the class
        cls = self._get_attribute(class_name)
        if cls is None or not inspect.isclass(cls):
            return False

        # Check if it has this method
        return hasattr(cls, method_name) and callable(getattr(cls, method_name, None))

    def _get_attribute(self, name: str) -> Any | None:
        """Get an attribute from the module by name (supports dotted paths)."""
        parts = name.split(".")
        obj: Any = self.module

        # Skip module prefix if present
        if parts[0] == self.module_name:
            parts = parts[1:]

        for part in parts:
            try:
                obj = getattr(obj, part)
            except AttributeError:
                return None

        return obj

    def _resolve_function(
        self,
        pattern: str,
        custom_name: str | None = None,
        custom_description: str | None = None,
    ) -> list[ResolvedTool]:
        """Resolve a simple function reference."""
        func = self._get_attribute(pattern)

        if func is None:
            return []

        if not callable(func):
            return []

        # Skip if it's a class (classes are handled separately)
        if inspect.isclass(func):
            return []

        return [
            ResolvedTool(
                callable_obj=func,
                name=pattern.rsplit(".", 1)[-1],  # Last part of name
                qualified_name=pattern,
                custom_name=custom_name,
                custom_description=custom_description,
            )
        ]

    def _resolve_class(
        self,
        pattern: str,
        custom_name: str | None = None,
        custom_description: str | None = None,
    ) -> list[ResolvedTool]:
        """Resolve a class pattern - includes constructor and all public methods."""
        cls = self._get_attribute(pattern)

        if cls is None or not inspect.isclass(cls):
            return []

        class_name = pattern.rsplit(".", 1)[-1]
        tools: list[ResolvedTool] = []

        # Add constructor
        tools.append(
            ResolvedTool(
                callable_obj=cls,
                name=class_name,
                qualified_name=pattern,
                class_name=class_name,
                is_constructor=True,
                custom_name=custom_name,
                custom_description=custom_description,
            )
        )

        # Add all public methods
        for method_name in dir(cls):
            if method_name.startswith("_"):
                continue

            method = getattr(cls, method_name, None)
            if method is None:
                continue

            # Skip properties
            if isinstance(inspect.getattr_static(cls, method_name), property):
                continue

            if not callable(method):
                continue

            # Determine method type
            is_static = isinstance(inspect.getattr_static(cls, method_name), staticmethod)
            is_classmethod = isinstance(inspect.getattr_static(cls, method_name), classmethod)

            tools.append(
                ResolvedTool(
                    callable_obj=method,
                    name=f"{class_name}.{method_name}",
                    qualified_name=f"{pattern}.{method_name}",
                    class_name=class_name,
                    is_method=not (is_static or is_classmethod),
                    is_static_method=is_static,
                    is_class_method=is_classmethod,
                )
            )

        return tools

    def _resolve_method(
        self,
        pattern: str,
        custom_name: str | None = None,
        custom_description: str | None = None,
    ) -> list[ResolvedTool]:
        """Resolve a specific method reference (Class.method)."""
        parts = pattern.rsplit(".", 1)
        if len(parts) != 2:
            return []

        class_pattern, method_name = parts
        cls = self._get_attribute(class_pattern)

        if cls is None or not inspect.isclass(cls):
            return []

        method = getattr(cls, method_name, None)
        if method is None or not callable(method):
            return []

        class_name = class_pattern.rsplit(".", 1)[-1]

        # Determine method type
        is_static = isinstance(inspect.getattr_static(cls, method_name), staticmethod)
        is_classmethod = isinstance(inspect.getattr_static(cls, method_name), classmethod)

        return [
            ResolvedTool(
                callable_obj=method,
                name=f"{class_name}.{method_name}",
                qualified_name=pattern,
                class_name=class_name,
                is_method=not (is_static or is_classmethod),
                is_static_method=is_static,
                is_class_method=is_classmethod,
                custom_name=custom_name,
                custom_description=custom_description,
            )
        ]

    def _resolve_glob(
        self,
        pattern: str,
        custom_name: str | None = None,
        custom_description: str | None = None,
    ) -> list[ResolvedTool]:
        """Resolve a glob pattern using fnmatch."""
        tools: list[ResolvedTool] = []

        # Check if pattern is Class.method_pattern (e.g., DataFrame.to_*)
        if "." in pattern:
            parts = pattern.split(".", 1)
            if len(parts) == 2:
                class_pattern, method_pattern = parts

                # Check if class_pattern has wildcard
                if "*" in class_pattern:
                    # Glob across classes - more complex, handle module-level
                    tools.extend(self._resolve_module_glob(pattern))
                else:
                    # Specific class, glob on methods
                    cls = self._get_attribute(class_pattern)
                    if cls is not None and inspect.isclass(cls):
                        tools.extend(
                            self._resolve_class_method_glob(
                                cls, class_pattern, method_pattern
                            )
                        )
        else:
            # Top-level function glob
            tools.extend(self._resolve_module_glob(pattern))

        return tools

    def _resolve_class_method_glob(
        self, cls: type, class_pattern: str, method_pattern: str
    ) -> list[ResolvedTool]:
        """Resolve a glob pattern for methods on a specific class."""
        tools: list[ResolvedTool] = []
        class_name = class_pattern.rsplit(".", 1)[-1]

        for method_name in dir(cls):
            if method_name.startswith("_"):
                continue

            if not fnmatch.fnmatch(method_name, method_pattern):
                continue

            method = getattr(cls, method_name, None)
            if method is None:
                continue

            # Skip properties
            if isinstance(inspect.getattr_static(cls, method_name), property):
                continue

            if not callable(method):
                continue

            is_static = isinstance(inspect.getattr_static(cls, method_name), staticmethod)
            is_classmethod = isinstance(inspect.getattr_static(cls, method_name), classmethod)

            tools.append(
                ResolvedTool(
                    callable_obj=method,
                    name=f"{class_name}.{method_name}",
                    qualified_name=f"{class_pattern}.{method_name}",
                    class_name=class_name,
                    is_method=not (is_static or is_classmethod),
                    is_static_method=is_static,
                    is_class_method=is_classmethod,
                )
            )

        return tools

    def _resolve_module_glob(self, pattern: str) -> list[ResolvedTool]:
        """Resolve a glob pattern at module level."""
        tools: list[ResolvedTool] = []

        for name in dir(self.module):
            if name.startswith("_"):
                continue

            if not fnmatch.fnmatch(name, pattern):
                continue

            obj = getattr(self.module, name, None)
            if obj is None:
                continue

            if inspect.isclass(obj):
                # For class matches, include the class and all methods
                tools.extend(self._resolve_class(name))
            elif callable(obj):
                tools.append(
                    ResolvedTool(
                        callable_obj=obj,
                        name=name,
                        qualified_name=name,
                    )
                )

        return tools


def resolve_all_patterns(
    module: ModuleType,
    patterns: list[tuple[str, str | None, str | None]],
) -> list[ResolvedTool]:
    """Resolve multiple patterns and deduplicate results.

    Args:
        module: The module to resolve against
        patterns: List of (pattern, custom_name, custom_description) tuples

    Returns:
        Deduplicated list of resolved tools
    """
    resolver = PatternResolver(module)
    seen_names: set[str] = set()
    tools: list[ResolvedTool] = []

    for pattern, custom_name, custom_description in patterns:
        resolved = resolver.resolve(pattern, custom_name, custom_description)
        for tool in resolved:
            if tool.qualified_name not in seen_names:
                seen_names.add(tool.qualified_name)
                tools.append(tool)

    return tools
