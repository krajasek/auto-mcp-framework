"""Package analyzer for recursive module discovery and analysis."""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from auto_mcp.core.analyzer import MethodMetadata, ModuleAnalyzer


@dataclass
class ModuleInfo:
    """Information about a discovered module.

    Attributes:
        name: Full module name (e.g., "requests.adapters")
        module: The loaded module object
        is_package: Whether this is a package (has submodules)
        is_public: Whether this is part of the public API
        parent: Parent module name, if any
        submodules: Names of direct submodules
    """

    name: str
    module: ModuleType
    is_package: bool
    is_public: bool
    parent: str | None = None
    submodules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict.

        Note: module is stored as its name string since ModuleType
        cannot be JSON serialized.
        """
        return {
            "name": self.name,
            "module_name": self.module.__name__ if self.module else None,
            "is_package": self.is_package,
            "is_public": self.is_public,
            "parent": self.parent,
            "submodules": self.submodules,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModuleInfo":
        """Deserialize from dict.

        Note: module will be None since we can't reconstruct it from a string.
        The module_name is preserved in the data for reference.
        """
        # We can't reconstruct the actual module, so we pass None
        # and store a placeholder. The caller should handle this appropriately.
        return cls(
            name=data["name"],
            module=None,  # type: ignore[arg-type]
            is_package=data.get("is_package", False),
            is_public=data.get("is_public", True),
            parent=data.get("parent"),
            submodules=data.get("submodules", []),
        )


@dataclass
class PackageMetadata:
    """Metadata for an analyzed package.

    Attributes:
        name: Package name
        root_module: The root module object
        modules: All discovered modules
        public_api: List of public API symbols (from __all__)
        methods: All extracted method metadata
        module_graph: Dependency relationships between modules
    """

    name: str
    root_module: ModuleType
    modules: dict[str, ModuleInfo] = field(default_factory=dict)
    public_api: set[str] = field(default_factory=set)
    methods: list[MethodMetadata] = field(default_factory=list)
    module_graph: dict[str, list[str]] = field(default_factory=dict)

    @property
    def module_count(self) -> int:
        """Number of modules in the package."""
        return len(self.modules)

    @property
    def public_module_count(self) -> int:
        """Number of public modules."""
        return sum(1 for m in self.modules.values() if m.is_public)

    @property
    def method_count(self) -> int:
        """Number of methods discovered."""
        return len(self.methods)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict for subprocess communication.

        Note: root_module is stored as its name string since ModuleType
        cannot be JSON serialized. ModuleInfo objects are serialized recursively.
        """
        return {
            "name": self.name,
            "root_module_name": self.root_module.__name__ if self.root_module else None,
            "modules": {k: v.to_dict() for k, v in self.modules.items()},
            "public_api": list(self.public_api),
            "methods": [m.to_dict() for m in self.methods],
            "module_graph": self.module_graph,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PackageMetadata":
        """Deserialize from dict.

        Note: root_module will be None since we can't reconstruct it.
        ModuleInfo objects will have module=None as well.
        """
        modules = {
            k: ModuleInfo.from_dict(v) for k, v in data.get("modules", {}).items()
        }
        methods = [
            MethodMetadata.from_dict(m) for m in data.get("methods", [])
        ]

        return cls(
            name=data["name"],
            root_module=None,  # type: ignore[arg-type]
            modules=modules,
            public_api=set(data.get("public_api", [])),
            methods=methods,
            module_graph=data.get("module_graph", {}),
        )


class PackageAnalyzer:
    """Analyzes Python packages recursively to extract callable metadata.

    This analyzer handles entire packages (like `requests`, `pandas`, etc.)
    by recursively discovering submodules and extracting their callables.

    Example:
        >>> analyzer = PackageAnalyzer()
        >>> metadata = analyzer.analyze_package("requests")
        >>> print(f"Found {metadata.module_count} modules")
        >>> print(f"Found {metadata.method_count} methods")
    """

    def __init__(
        self,
        include_private: bool = False,
        max_depth: int | None = None,
        follow_imports: bool = False,
        include_reexports: bool = False,
    ) -> None:
        """Initialize the package analyzer.

        Args:
            include_private: Whether to include private modules/methods
            max_depth: Maximum recursion depth (None for unlimited)
            follow_imports: Whether to follow imported modules from other packages
            include_reexports: Whether to include functions re-exported in __all__
                              even if defined in other modules
        """
        self.include_private = include_private
        self.max_depth = max_depth
        self.follow_imports = follow_imports
        self.include_reexports = include_reexports
        self._module_analyzer = ModuleAnalyzer(
            include_private=include_private,
            include_reexports=include_reexports,
        )

    def analyze_package(
        self,
        package: str | ModuleType,
        *,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> PackageMetadata:
        """Analyze a package and all its submodules.

        Args:
            package: Package name (string) or module object
            include_patterns: Glob patterns for modules to include
            exclude_patterns: Glob patterns for modules to exclude

        Returns:
            PackageMetadata with all discovered modules and methods
        """
        # Load the package
        root_module = self._load_package(package)
        package_name = root_module.__name__

        # Create metadata container
        metadata = PackageMetadata(
            name=package_name,
            root_module=root_module,
        )

        # Extract public API from __all__
        metadata.public_api = self._extract_public_api(root_module)

        # Discover all modules recursively
        self._discover_modules(
            root_module,
            metadata,
            depth=0,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
        )

        # Build module dependency graph
        metadata.module_graph = self._build_module_graph(metadata.modules)

        # Analyze each module for methods
        for module_info in metadata.modules.values():
            # Only include methods from modules that actually match the pattern
            # (not just modules traversed to reach matching children)
            if not self._module_matches_for_methods(
                module_info.name, include_patterns, exclude_patterns
            ):
                continue

            methods = self._module_analyzer.analyze_module(module_info.module)
            # Tag methods with additional package info
            for method in methods:
                method.mcp_metadata["package_name"] = package_name
                method.mcp_metadata["is_public_api"] = self._is_in_public_api(
                    method, metadata.public_api
                )
            metadata.methods.extend(methods)

        return metadata

    def analyze_package_file(
        self,
        package_path: Path | str,
        *,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> PackageMetadata:
        """Analyze a package from a file path.

        Args:
            package_path: Path to the package directory
            include_patterns: Glob patterns for modules to include
            exclude_patterns: Glob patterns for modules to exclude

        Returns:
            PackageMetadata with all discovered modules and methods
        """
        package_path = Path(package_path)

        if not package_path.is_dir():
            raise ValueError(f"Package path must be a directory: {package_path}")

        init_file = package_path / "__init__.py"
        if not init_file.exists():
            raise ValueError(f"Not a valid Python package (no __init__.py): {package_path}")

        # Add parent to sys.path temporarily
        parent_path = str(package_path.parent)
        if parent_path not in sys.path:
            sys.path.insert(0, parent_path)
            path_added = True
        else:
            path_added = False

        try:
            # Import the package
            package_name = package_path.name
            module = importlib.import_module(package_name)
            return self.analyze_package(
                module,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
            )
        finally:
            if path_added:
                sys.path.remove(parent_path)

    def _load_package(self, package: str | ModuleType) -> ModuleType:
        """Load a package from string name or return module directly.

        Args:
            package: Package name or module object

        Returns:
            The loaded module

        Raises:
            ImportError: If the package cannot be imported
            ValueError: If the module is not a package
        """
        if isinstance(package, str):
            try:
                module = importlib.import_module(package)
            except ImportError as e:
                raise ImportError(f"Cannot import package '{package}': {e}") from e
        else:
            module = package

        # Verify it's a package (has __path__)
        if not hasattr(module, "__path__"):
            raise ValueError(
                f"'{module.__name__}' is a module, not a package. "
                "Use ModuleAnalyzer for single modules."
            )

        return module

    def _extract_public_api(self, module: ModuleType) -> set[str]:
        """Extract public API symbols from __all__.

        This recursively collects __all__ from the module and its submodules
        that are explicitly exported.

        Args:
            module: The module to analyze

        Returns:
            Set of public symbol names (qualified)
        """
        public_api: set[str] = set()
        module_name = module.__name__

        # Get __all__ if defined
        all_symbols = getattr(module, "__all__", None)
        if all_symbols:
            for symbol in all_symbols:
                # Add as qualified name
                public_api.add(f"{module_name}.{symbol}")

                # Check if it's a submodule that might have its own __all__
                submodule = getattr(module, symbol, None)
                if isinstance(submodule, ModuleType):
                    public_api.update(self._extract_public_api(submodule))

        return public_api

    def _discover_modules(
        self,
        module: ModuleType,
        metadata: PackageMetadata,
        depth: int,
        include_patterns: list[str] | None,
        exclude_patterns: list[str] | None,
        parent_name: str | None = None,
    ) -> None:
        """Recursively discover all submodules of a package.

        Args:
            module: The module to analyze
            metadata: PackageMetadata to populate
            depth: Current recursion depth
            include_patterns: Glob patterns for modules to include
            exclude_patterns: Glob patterns for modules to exclude
            parent_name: Name of parent module
        """
        module_name = module.__name__

        # Check depth limit
        if self.max_depth is not None and depth > self.max_depth:
            return

        # Check if module matches patterns
        if not self._matches_patterns(module_name, include_patterns, exclude_patterns):
            return

        # Check if private module should be skipped
        base_name = module_name.split(".")[-1]
        is_private = base_name.startswith("_") and not base_name.startswith("__")
        if is_private and not self.include_private:
            return

        # Determine if this is part of the public API
        is_public = self._is_module_public(module_name, metadata.public_api)

        # Check if it's a package (has submodules)
        is_package = hasattr(module, "__path__")

        # Create module info
        module_info = ModuleInfo(
            name=module_name,
            module=module,
            is_package=is_package,
            is_public=is_public,
            parent=parent_name,
        )

        # Add to metadata
        metadata.modules[module_name] = module_info

        # If it's a package, discover submodules
        if is_package:
            try:
                for _importer, submodule_name, _is_pkg in pkgutil.iter_modules(
                    module.__path__, prefix=f"{module_name}."
                ):
                    # Record submodule relationship
                    module_info.submodules.append(submodule_name)

                    # Try to import and analyze the submodule
                    try:
                        submodule = importlib.import_module(submodule_name)
                        self._discover_modules(
                            submodule,
                            metadata,
                            depth + 1,
                            include_patterns,
                            exclude_patterns,
                            parent_name=module_name,
                        )
                    except ImportError:
                        # Log but continue - some modules may have optional deps
                        pass
                    except Exception:
                        # Other errors (syntax, runtime) - skip module
                        pass
            except Exception:
                # If we can't iterate modules, just skip
                pass

    def _matches_patterns(
        self,
        module_name: str,
        include_patterns: list[str] | None,
        exclude_patterns: list[str] | None,
    ) -> bool:
        """Check if a module name matches the include/exclude patterns.

        Args:
            module_name: The module name to check
            include_patterns: Patterns that must match (if specified)
            exclude_patterns: Patterns that must not match

        Returns:
            True if the module should be included
        """
        import fnmatch

        # Check exclude patterns first
        if exclude_patterns:
            for pattern in exclude_patterns:
                if fnmatch.fnmatch(module_name, pattern):
                    return False

        # Check include patterns
        if include_patterns:
            for pattern in include_patterns:
                # Direct match
                if fnmatch.fnmatch(module_name, pattern):
                    return True
                # Check if this module is a prefix/ancestor of the pattern
                # e.g., module "requests" is a prefix of pattern "requests.api.*"
                # This allows traversal through parent modules to find matches
                pattern_prefix = pattern.rstrip("*").rstrip(".")
                if pattern_prefix.startswith(module_name + ".") or pattern_prefix == module_name:
                    return True
            return False

        return True  # No patterns specified, include by default

    def _module_matches_for_methods(
        self,
        module_name: str,
        include_patterns: list[str] | None,
        exclude_patterns: list[str] | None,
    ) -> bool:
        """Check if a module's methods should be included (stricter than traversal).

        Unlike _matches_patterns which allows traversal through parent modules,
        this method returns True only if the module directly matches a pattern.

        Special case: patterns ending in '.*' also match their parent module.
        e.g., 'requests.api.*' will match both 'requests.api' and 'requests.api.foo'

        Args:
            module_name: The module name to check
            include_patterns: Patterns that must match (if specified)
            exclude_patterns: Patterns that must not match

        Returns:
            True if the module's methods should be included
        """
        import fnmatch

        # Check exclude patterns first
        if exclude_patterns:
            for pattern in exclude_patterns:
                if fnmatch.fnmatch(module_name, pattern):
                    return False

        # Check include patterns
        if include_patterns:
            for pattern in include_patterns:
                # Direct match
                if fnmatch.fnmatch(module_name, pattern):
                    return True
                # Special case: pattern ending in '.*' also matches parent module
                # e.g., 'requests.api.*' also matches 'requests.api'
                if pattern.endswith(".*"):
                    parent_pattern = pattern[:-2]  # Remove '.*'
                    if module_name == parent_pattern:
                        return True
            return False

        return True  # No patterns specified, include by default

    def _is_module_public(self, module_name: str, public_api: set[str]) -> bool:
        """Determine if a module is part of the public API.

        A module is considered public if:
        1. It's explicitly in __all__ of its parent
        2. It doesn't start with underscore
        3. Any of its contents are in the public API

        Args:
            module_name: The module name
            public_api: Set of public API symbols

        Returns:
            True if the module is public
        """
        # Check if any symbol from this module is in public API
        for symbol in public_api:
            if symbol.startswith(f"{module_name}."):
                return True

        # Check if module itself is in public API
        if module_name in public_api:
            return True

        # Check if module name looks private
        parts = module_name.split(".")
        return all(
            not (part.startswith("_") and not part.startswith("__"))
            for part in parts
        )

    def _is_in_public_api(
        self, method: MethodMetadata, public_api: set[str]
    ) -> bool:
        """Check if a method is part of the public API.

        Args:
            method: The method metadata
            public_api: Set of public API symbols

        Returns:
            True if the method is in the public API
        """
        # Check qualified name
        qualified = f"{method.module_name}.{method.qualified_name}"
        if qualified in public_api:
            return True

        # Check just the function name in module
        simple = f"{method.module_name}.{method.name}"
        return simple in public_api

    def _build_module_graph(
        self, modules: dict[str, ModuleInfo]
    ) -> dict[str, list[str]]:
        """Build a dependency graph between modules.

        Args:
            modules: Dictionary of module info

        Returns:
            Dict mapping module names to their submodules
        """
        graph: dict[str, list[str]] = {}

        for name, info in modules.items():
            graph[name] = info.submodules.copy()

        return graph

    def get_public_methods(
        self, metadata: PackageMetadata
    ) -> list[MethodMetadata]:
        """Get only methods that are part of the public API.

        Args:
            metadata: The package metadata

        Returns:
            List of public methods
        """
        return [
            m for m in metadata.methods
            if m.mcp_metadata.get("is_public_api", False)
        ]

    def get_methods_by_module(
        self, metadata: PackageMetadata
    ) -> dict[str, list[MethodMetadata]]:
        """Group methods by their source module.

        Args:
            metadata: The package metadata

        Returns:
            Dict mapping module names to their methods
        """
        by_module: dict[str, list[MethodMetadata]] = {}

        for method in metadata.methods:
            module_name = method.module_name
            if module_name not in by_module:
                by_module[module_name] = []
            by_module[module_name].append(method)

        return by_module


def analyze_installed_package(
    package_name: str,
    *,
    include_private: bool = False,
    max_depth: int | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    include_reexports: bool = False,
) -> PackageMetadata:
    """Convenience function to analyze an installed package.

    Args:
        package_name: Name of the installed package (e.g., "requests")
        include_private: Whether to include private modules/methods
        max_depth: Maximum recursion depth
        include_patterns: Glob patterns for modules to include
        exclude_patterns: Glob patterns for modules to exclude
        include_reexports: Whether to include functions re-exported in __all__
                          even if defined in other modules (useful for packages
                          like pandas, numpy that re-export from submodules)

    Returns:
        PackageMetadata with analysis results

    Example:
        >>> metadata = analyze_installed_package("requests")
        >>> print(f"Found {metadata.method_count} methods")
    """
    analyzer = PackageAnalyzer(
        include_private=include_private,
        max_depth=max_depth,
        include_reexports=include_reexports,
    )
    return analyzer.analyze_package(
        package_name,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
    )
