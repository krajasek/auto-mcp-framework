"""Module analyzer for extracting callable metadata from Python modules."""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, get_type_hints

from auto_mcp.decorators import (
    MCP_EXCLUDE_MARKER,
    MCP_PROMPT_MARKER,
    MCP_RESOURCE_MARKER,
    MCP_SESSION_CLEANUP_MARKER,
    MCP_SESSION_INIT_MARKER,
    MCP_TOOL_MARKER,
)
from auto_mcp.session.injection import get_session_param_name, needs_session_injection


@dataclass
class MethodMetadata:
    """Metadata extracted from a callable (function or method).

    Attributes:
        name: The function/method name
        qualified_name: Fully qualified name including class (e.g., "Calculator.add")
        module_name: Name of the module containing the callable
        signature: The inspect.Signature object
        docstring: The function's docstring, if any
        type_hints: Dictionary of parameter names to type annotations
        return_type: The return type annotation, if any
        is_async: Whether this is an async function
        is_method: Whether this is a method (bound to a class)
        is_classmethod: Whether this is a @classmethod
        is_staticmethod: Whether this is a @staticmethod
        source_code: The source code of the function
        decorators: List of decorator names applied to the function
        parameters: List of parameter info dicts
        mcp_metadata: MCP-specific metadata from decorators
    """

    name: str
    qualified_name: str
    module_name: str
    signature: inspect.Signature
    docstring: str | None
    type_hints: dict[str, Any]
    return_type: Any
    is_async: bool
    is_method: bool
    is_classmethod: bool
    is_staticmethod: bool
    source_code: str
    decorators: list[str]
    parameters: list[dict[str, Any]] = field(default_factory=list)
    mcp_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_private(self) -> bool:
        """Check if this is a private method (starts with underscore)."""
        return self.name.startswith("_")

    @property
    def is_dunder(self) -> bool:
        """Check if this is a dunder method (e.g., __init__)."""
        return self.name.startswith("__") and self.name.endswith("__")

    @property
    def is_excluded(self) -> bool:
        """Check if this method is marked for exclusion."""
        return bool(self.mcp_metadata.get("is_excluded", False))

    @property
    def is_tool(self) -> bool:
        """Check if this method is explicitly marked as a tool."""
        return bool(self.mcp_metadata.get("is_tool", False))

    @property
    def is_resource(self) -> bool:
        """Check if this method is marked as a resource."""
        return bool(self.mcp_metadata.get("is_resource", False))

    @property
    def is_prompt(self) -> bool:
        """Check if this method is marked as a prompt."""
        return bool(self.mcp_metadata.get("is_prompt", False))

    @property
    def is_session_init(self) -> bool:
        """Check if this method is a session initialization hook."""
        return bool(self.mcp_metadata.get("is_session_init", False))

    @property
    def is_session_cleanup(self) -> bool:
        """Check if this method is a session cleanup hook."""
        return bool(self.mcp_metadata.get("is_session_cleanup", False))

    @property
    def needs_session(self) -> bool:
        """Check if this method needs session injection."""
        return bool(self.mcp_metadata.get("needs_session", False))

    @property
    def session_param_name(self) -> str | None:
        """Get the name of the SessionContext parameter, if any."""
        return self.mcp_metadata.get("session_param_name")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict for subprocess communication.

        Note: inspect.Signature is converted to string representation.
        Type hints are converted to string representations.
        """
        # Convert type hints to strings (they may contain type objects)
        type_hints_str = {}
        for k, v in self.type_hints.items():
            try:
                if hasattr(v, "__name__"):
                    type_hints_str[k] = v.__name__
                elif hasattr(v, "__origin__"):
                    # Handle generic types like list[str], Optional[int]
                    type_hints_str[k] = str(v)
                else:
                    type_hints_str[k] = str(v)
            except Exception:
                type_hints_str[k] = "Any"

        # Convert return type to string
        return_type_str: str | None = None
        if self.return_type is not None:
            try:
                if hasattr(self.return_type, "__name__"):
                    return_type_str = self.return_type.__name__
                else:
                    return_type_str = str(self.return_type)
            except Exception:
                return_type_str = "Any"

        # Serialize parameters, converting non-JSON-serializable defaults
        serialized_params = []
        for param in self.parameters:
            param_copy = param.copy()
            default = param_copy.get("default")
            if default is not None:
                # Check if it's a simple JSON-serializable type
                if not isinstance(default, (str, int, float, bool, type(None), list, dict)):
                    # Convert to string representation
                    param_copy["default"] = repr(default)
                    param_copy["default_is_repr"] = True
            # Also handle type field which may not be serializable
            if param_copy.get("type") is not None:
                param_copy["type"] = str(param_copy["type"])
            serialized_params.append(param_copy)

        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "module_name": self.module_name,
            "signature": str(self.signature),
            "docstring": self.docstring,
            "type_hints": type_hints_str,
            "return_type": return_type_str,
            "is_async": self.is_async,
            "is_method": self.is_method,
            "is_classmethod": self.is_classmethod,
            "is_staticmethod": self.is_staticmethod,
            "source_code": self.source_code,
            "decorators": self.decorators,
            "parameters": serialized_params,
            "mcp_metadata": self.mcp_metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MethodMetadata":
        """Deserialize from dict.

        Note: signature will be stored as a string, not inspect.Signature.
        Type hints will be strings, not actual type objects.
        """
        # Create a placeholder signature from the string
        # We use a simple Parameter to hold the string representation
        sig_str = data.get("signature", "()")

        # Create a minimal signature object that str() will work on
        # Since we can't reconstruct the full Signature, we store it as-is
        # and the signature field will hold a "fake" signature
        placeholder_sig = inspect.Signature()

        instance = cls(
            name=data["name"],
            qualified_name=data["qualified_name"],
            module_name=data["module_name"],
            signature=placeholder_sig,
            docstring=data.get("docstring"),
            type_hints=data.get("type_hints", {}),
            return_type=data.get("return_type"),
            is_async=data.get("is_async", False),
            is_method=data.get("is_method", False),
            is_classmethod=data.get("is_classmethod", False),
            is_staticmethod=data.get("is_staticmethod", False),
            source_code=data.get("source_code", ""),
            decorators=data.get("decorators", []),
            parameters=data.get("parameters", []),
            mcp_metadata=data.get("mcp_metadata", {}),
        )

        # Store the original signature string in mcp_metadata for reference
        instance.mcp_metadata["_serialized_signature"] = sig_str

        return instance


@dataclass
class ClassMetadata:
    """Metadata for a class in a module.

    Attributes:
        name: The class name
        module_name: Name of the module containing the class
        docstring: The class docstring
        methods: List of MethodMetadata for the class methods
    """

    name: str
    module_name: str
    docstring: str | None
    methods: list[MethodMetadata] = field(default_factory=list)


class ModuleAnalyzer:
    """Analyzes Python modules to extract callable metadata.

    This analyzer inspects Python modules and extracts metadata about
    functions and methods that can be exposed as MCP tools, resources,
    or prompts.
    """

    def __init__(
        self,
        include_private: bool = False,
        include_reexports: bool = False,
    ) -> None:
        """Initialize the analyzer.

        Args:
            include_private: Whether to include private methods (starting with _)
            include_reexports: Whether to include functions re-exported in __all__
                              even if defined in other modules (common in packages
                              like pandas, numpy, etc.)
        """
        self.include_private = include_private
        self.include_reexports = include_reexports

    def analyze_module(self, module: ModuleType) -> list[MethodMetadata]:
        """Analyze a module and extract all exposable callables.

        Args:
            module: The Python module to analyze

        Returns:
            List of MethodMetadata for all exposable functions and methods
        """
        results: list[MethodMetadata] = []

        # Get module name
        module_name = module.__name__

        # Get __all__ for re-export checking
        module_all = set(getattr(module, "__all__", []))

        # Analyze top-level functions
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            # Check if function should be included
            defined_here = obj.__module__ == module_name
            is_reexport = self.include_reexports and name in module_all

            if not (defined_here or is_reexport):
                continue

            metadata = self._analyze_callable(obj, module_name)
            if metadata and self.should_expose(metadata):
                # Mark re-exports with their original module
                if is_reexport and not defined_here:
                    metadata.mcp_metadata["original_module"] = obj.__module__
                    metadata.mcp_metadata["is_reexport"] = True
                results.append(metadata)

        # Analyze classes and their methods
        for name, cls in inspect.getmembers(module, inspect.isclass):
            # Check if class should be included
            defined_here = cls.__module__ == module_name
            is_reexport = self.include_reexports and name in module_all

            if not (defined_here or is_reexport):
                continue

            class_methods = self._analyze_class(cls, module_name)
            for method in class_methods:
                if self.should_expose(method):
                    # Mark re-exports with their original module
                    if is_reexport and not defined_here:
                        method.mcp_metadata["original_module"] = cls.__module__
                        method.mcp_metadata["is_reexport"] = True
                    results.append(method)

        return results

    def analyze_file(self, file_path: Path | str) -> list[MethodMetadata]:
        """Analyze a Python file and extract all exposable callables.

        Args:
            file_path: Path to the Python file

        Returns:
            List of MethodMetadata for all exposable functions and methods
        """
        import importlib.util

        file_path = Path(file_path)

        # Load module from file
        spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Could not load module from {file_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        return self.analyze_module(module)

    def should_expose(self, metadata: MethodMetadata) -> bool:
        """Determine if a callable should be exposed as an MCP tool.

        Args:
            metadata: The method metadata to check

        Returns:
            True if the method should be exposed
        """
        # Always exclude if marked with @mcp_exclude
        if metadata.is_excluded:
            return False

        # Session hooks are handled separately, not exposed as tools
        if metadata.is_session_init or metadata.is_session_cleanup:
            return False

        # Always include if explicitly marked as tool, resource, or prompt
        if metadata.is_tool or metadata.is_resource or metadata.is_prompt:
            return True

        # Exclude dunder methods
        if metadata.is_dunder:
            return False

        # Handle private methods based on setting
        return not (metadata.is_private and not self.include_private)

    def _analyze_callable(
        self,
        func: Callable[..., Any],
        module_name: str,
        class_name: str | None = None,
    ) -> MethodMetadata | None:
        """Analyze a single callable and extract its metadata.

        Args:
            func: The function or method to analyze
            module_name: Name of the containing module
            class_name: Name of the containing class, if any

        Returns:
            MethodMetadata or None if analysis failed
        """
        try:
            name = func.__name__
            qualified_name = f"{class_name}.{name}" if class_name else name

            # Get signature
            try:
                signature = inspect.signature(func)
            except (ValueError, TypeError):
                return None

            # Get docstring
            docstring = inspect.getdoc(func)

            # Get type hints
            try:
                hints = get_type_hints(func)
            except Exception:
                hints = {}

            # Extract return type
            return_type = hints.pop("return", None)

            # Check if async
            is_async = inspect.iscoroutinefunction(func)

            # Check method types
            is_method = class_name is not None
            is_classmethod = isinstance(
                inspect.getattr_static(func, "__func__", None), classmethod
            ) or hasattr(func, "__self__")
            is_staticmethod = isinstance(
                inspect.getattr_static(func, "__func__", None), staticmethod
            )

            # Get source code
            try:
                source_code = textwrap.dedent(inspect.getsource(func))
            except (OSError, TypeError):
                source_code = ""

            # Get decorators from source
            decorators = self._extract_decorators(func)

            # Build parameter info
            parameters = self._extract_parameters(signature, hints)

            # Get MCP metadata from decorators
            mcp_metadata = self._extract_mcp_metadata(func)

            return MethodMetadata(
                name=name,
                qualified_name=qualified_name,
                module_name=module_name,
                signature=signature,
                docstring=docstring,
                type_hints=hints,
                return_type=return_type,
                is_async=is_async,
                is_method=is_method,
                is_classmethod=is_classmethod,
                is_staticmethod=is_staticmethod,
                source_code=source_code,
                decorators=decorators,
                parameters=parameters,
                mcp_metadata=mcp_metadata,
            )

        except Exception:
            return None

    def _analyze_class(
        self,
        cls: type,
        module_name: str,
    ) -> list[MethodMetadata]:
        """Analyze a class and extract method metadata.

        Args:
            cls: The class to analyze
            module_name: Name of the containing module

        Returns:
            List of MethodMetadata for class methods
        """
        results: list[MethodMetadata] = []
        class_name = cls.__name__

        for name, method in inspect.getmembers(cls, predicate=self._is_method_like):
            # Skip inherited methods from object
            if name in dir(object) and not name.startswith("__"):
                continue

            # Get the actual function from the method
            func = method
            if isinstance(method, (staticmethod, classmethod)) or hasattr(method, "__func__"):
                func = method.__func__

            # Skip if defined in a parent class (not this class)
            if hasattr(func, "__qualname__") and not func.__qualname__.startswith(f"{class_name}."):
                continue

            metadata = self._analyze_callable(func, module_name, class_name)
            if metadata:
                results.append(metadata)

        return results

    def _is_method_like(self, obj: Any) -> bool:
        """Check if an object is a method-like callable."""
        return (
            inspect.isfunction(obj)
            or inspect.ismethod(obj)
            or isinstance(obj, (staticmethod, classmethod))
        )

    def _extract_decorators(self, func: Callable[..., Any]) -> list[str]:
        """Extract decorator names from a function's source code.

        Args:
            func: The function to analyze

        Returns:
            List of decorator names
        """
        decorators: list[str] = []

        try:
            source = inspect.getsource(func)
            tree = ast.parse(textwrap.dedent(source))

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for decorator in node.decorator_list:
                        if isinstance(decorator, ast.Name):
                            decorators.append(decorator.id)
                        elif isinstance(decorator, ast.Call):
                            if isinstance(decorator.func, ast.Name):
                                decorators.append(decorator.func.id)
                            elif isinstance(decorator.func, ast.Attribute):
                                decorators.append(decorator.func.attr)
                        elif isinstance(decorator, ast.Attribute):
                            decorators.append(decorator.attr)
                    break  # Only process the first function definition

        except Exception:
            pass

        return decorators

    def _extract_parameters(
        self,
        signature: inspect.Signature,
        type_hints: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Extract parameter information from a signature.

        Args:
            signature: The function signature
            type_hints: Type hints for parameters

        Returns:
            List of parameter info dictionaries
        """
        parameters: list[dict[str, Any]] = []

        for name, param in signature.parameters.items():
            # Skip self/cls parameters
            if name in ("self", "cls"):
                continue

            param_info: dict[str, Any] = {
                "name": name,
                "kind": str(param.kind.name),
                "has_default": param.default is not inspect.Parameter.empty,
                "default": (
                    param.default if param.default is not inspect.Parameter.empty else None
                ),
                "type": type_hints.get(name),
                "type_str": self._type_to_string(type_hints.get(name)),
            }
            parameters.append(param_info)

        return parameters

    def _type_to_string(self, type_annotation: Any) -> str:
        """Convert a type annotation to a string representation.

        Args:
            type_annotation: The type annotation

        Returns:
            String representation of the type
        """
        if type_annotation is None:
            return "Any"

        if hasattr(type_annotation, "__name__"):
            return str(type_annotation.__name__)

        return str(type_annotation).replace("typing.", "")

    def _extract_mcp_metadata(self, func: Callable[..., Any]) -> dict[str, Any]:
        """Extract MCP-specific metadata from a function's decorators.

        Args:
            func: The function to analyze

        Returns:
            Dictionary of MCP metadata
        """
        metadata: dict[str, Any] = {
            "is_tool": hasattr(func, MCP_TOOL_MARKER),
            "is_excluded": hasattr(func, MCP_EXCLUDE_MARKER),
            "is_resource": hasattr(func, MCP_RESOURCE_MARKER),
            "is_prompt": hasattr(func, MCP_PROMPT_MARKER),
            "is_session_init": hasattr(func, MCP_SESSION_INIT_MARKER),
            "is_session_cleanup": hasattr(func, MCP_SESSION_CLEANUP_MARKER),
        }

        # Get tool metadata
        if metadata["is_tool"]:
            tool_meta = getattr(func, MCP_TOOL_MARKER, {})
            metadata["tool_name"] = tool_meta.get("name")
            metadata["tool_description"] = tool_meta.get("description")

        # Get resource metadata
        if metadata["is_resource"]:
            resource_meta = getattr(func, MCP_RESOURCE_MARKER, {})
            metadata["resource_uri"] = resource_meta.get("uri")
            metadata["resource_name"] = resource_meta.get("name")
            metadata["resource_description"] = resource_meta.get("description")
            metadata["resource_mime_type"] = resource_meta.get("mime_type")

        # Get prompt metadata
        if metadata["is_prompt"]:
            prompt_meta = getattr(func, MCP_PROMPT_MARKER, {})
            metadata["prompt_name"] = prompt_meta.get("name")
            metadata["prompt_description"] = prompt_meta.get("description")

        # Get session init hook metadata
        if metadata["is_session_init"]:
            init_meta = getattr(func, MCP_SESSION_INIT_MARKER, {})
            metadata["session_init_order"] = init_meta.get("order", 0)

        # Get session cleanup hook metadata
        if metadata["is_session_cleanup"]:
            cleanup_meta = getattr(func, MCP_SESSION_CLEANUP_MARKER, {})
            metadata["session_cleanup_order"] = cleanup_meta.get("order", 0)

        # Check if function needs session injection
        metadata["needs_session"] = needs_session_injection(func)
        metadata["session_param_name"] = get_session_param_name(func)

        return metadata
