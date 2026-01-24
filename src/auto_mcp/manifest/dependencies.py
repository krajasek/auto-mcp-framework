"""Dependency analyzer for auto-including producer functions.

This module analyzes return types of functions and auto-includes
functions that produce types needed by the selected tools.
"""

from __future__ import annotations

import inspect
from types import ModuleType
from typing import Any, Callable, get_type_hints

from auto_mcp.manifest.resolver import PatternResolver, ResolvedTool


class DependencyAnalyzer:
    """Analyzes and resolves tool dependencies.

    When a method like DataFrame.to_csv is selected, it needs a DataFrame
    instance to operate on. This analyzer finds functions like read_csv
    that produce DataFrames and auto-includes them.
    """

    def __init__(self, module: ModuleType) -> None:
        """Initialize the analyzer.

        Args:
            module: The module to analyze
        """
        self.module = module
        self._return_type_map: dict[type, list[Callable[..., Any]]] = {}
        self._class_to_producers: dict[str, list[Callable[..., Any]]] = {}
        self._build_return_type_map()

    def _build_return_type_map(self) -> None:
        """Build a map from return types to functions that produce them."""
        for name in dir(self.module):
            if name.startswith("_"):
                continue

            obj = getattr(self.module, name, None)
            if obj is None:
                continue

            if not callable(obj):
                continue

            # Skip classes themselves (we want functions that return class instances)
            if inspect.isclass(obj):
                continue

            # Try to get return type hints
            try:
                hints = get_type_hints(obj)
                return_type = hints.get("return")
                if return_type is not None:
                    self._return_type_map.setdefault(return_type, []).append(obj)

                    # Also track by class name for easier lookup
                    type_name = self._get_type_name(return_type)
                    if type_name:
                        self._class_to_producers.setdefault(type_name, []).append(obj)
            except Exception:
                # Type hints may fail for various reasons (forward refs, etc.)
                pass

    def _get_type_name(self, type_obj: Any) -> str | None:
        """Get the name of a type for lookup."""
        if isinstance(type_obj, type):
            return type_obj.__name__
        if hasattr(type_obj, "__name__"):
            return type_obj.__name__
        # Handle string type hints
        if isinstance(type_obj, str):
            return type_obj
        return None

    def find_producers(self, target_type: type) -> list[Callable[..., Any]]:
        """Find all functions that produce the target type.

        Args:
            target_type: The type to find producers for

        Returns:
            List of functions that return the target type
        """
        producers: list[Callable[..., Any]] = []

        # Direct match
        if target_type in self._return_type_map:
            producers.extend(self._return_type_map[target_type])

        # Check subclasses
        for ret_type, funcs in self._return_type_map.items():
            if isinstance(ret_type, type) and isinstance(target_type, type):
                try:
                    if issubclass(ret_type, target_type) and ret_type != target_type:
                        producers.extend(funcs)
                except TypeError:
                    pass

        return producers

    def find_producers_by_name(self, class_name: str) -> list[Callable[..., Any]]:
        """Find functions that produce instances of a class by name.

        Args:
            class_name: Name of the class to find producers for

        Returns:
            List of functions that return the class type
        """
        return self._class_to_producers.get(class_name, [])

    def get_required_types(self, tools: list[ResolvedTool]) -> set[str]:
        """Get all class names required as inputs by the tools.

        Args:
            tools: List of resolved tools

        Returns:
            Set of class names that are required as method receivers
        """
        required: set[str] = set()

        for tool in tools:
            if tool.is_method and tool.class_name:
                # Instance methods need an instance of their class
                required.add(tool.class_name)

        return required

    def auto_include(self, tools: list[ResolvedTool]) -> list[ResolvedTool]:
        """Add producer functions for required types.

        For each method that needs an instance of a class, this finds
        functions that return that class type and adds them to the tools list.

        Args:
            tools: Current list of resolved tools

        Returns:
            Extended list including producer functions
        """
        required_types = self.get_required_types(tools)
        existing_names = {t.qualified_name for t in tools}
        resolver = PatternResolver(self.module)

        additional: list[ResolvedTool] = []

        for class_name in required_types:
            # First, check if the class constructor is already included
            if class_name not in existing_names:
                # Try to resolve the class itself as a constructor
                class_tools = resolver.resolve(class_name)
                for tool in class_tools:
                    if tool.is_constructor and tool.qualified_name not in existing_names:
                        tool.auto_included = True
                        additional.append(tool)
                        existing_names.add(tool.qualified_name)

            # Find producer functions for this type
            producers = self.find_producers_by_name(class_name)
            for producer in producers:
                name = producer.__name__
                if name not in existing_names:
                    # Resolve through the resolver to get proper metadata
                    producer_tools = resolver.resolve(name)
                    for prod_tool in producer_tools:
                        if prod_tool.qualified_name not in existing_names:
                            prod_tool.auto_included = True
                            additional.append(prod_tool)
                            existing_names.add(prod_tool.qualified_name)

        return tools + additional


def analyze_and_include_dependencies(
    module: ModuleType, tools: list[ResolvedTool]
) -> list[ResolvedTool]:
    """Analyze tools and auto-include dependency producers.

    This is the main entry point for dependency analysis.

    Args:
        module: The module containing the tools
        tools: List of resolved tools

    Returns:
        Extended list including auto-included producer functions
    """
    analyzer = DependencyAnalyzer(module)
    return analyzer.auto_include(tools)
