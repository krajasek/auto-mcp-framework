"""Wrapper generator for C extension modules.

This module generates Python wrappers for C extension modules,
making them introspectable for MCP server generation.
"""

from __future__ import annotations

import importlib
import inspect
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import BuiltinFunctionType, BuiltinMethodType, ModuleType
from typing import Any


@dataclass
class CallableInfo:
    """Information about a callable in a module."""

    name: str
    qualified_name: str
    docstring: str | None
    is_method: bool
    class_name: str | None
    is_c_extension: bool
    # Parsed signature info (if available from docstring)
    parsed_params: list[dict[str, Any]] = field(default_factory=list)
    parsed_return_type: str | None = None


@dataclass
class ClassInfo:
    """Information about a class in a module."""

    name: str
    docstring: str | None
    methods: list[CallableInfo] = field(default_factory=list)
    is_c_extension: bool = False


class WrapperGenerator:
    """Generates Python wrappers for C extension modules.

    This allows C extension modules to be analyzed and converted
    to MCP servers by creating pure Python wrapper functions.
    """

    def __init__(
        self,
        include_private: bool = False,
        include_dunder: bool = False,
    ) -> None:
        """Initialize the wrapper generator.

        Args:
            include_private: Whether to include private methods (starting with _)
            include_dunder: Whether to include dunder methods (__init__, etc.)
        """
        self.include_private = include_private
        self.include_dunder = include_dunder

    def is_c_extension_module(self, module: ModuleType) -> bool:
        """Check if a module is a C extension module.

        Args:
            module: The module to check

        Returns:
            True if the module is a C extension
        """
        # Check if module has a file attribute and it's a .so/.pyd
        module_file = getattr(module, "__file__", None)
        if module_file and module_file.endswith((".so", ".pyd", ".dylib")):
            return True

        # Check if it's a built-in module
        if module.__name__ in ("builtins", "sys", "_io"):
            return True

        # Check if it has loader info indicating C extension
        loader = getattr(module, "__loader__", None)
        if loader:
            loader_name = type(loader).__name__
            if "ExtensionFileLoader" in loader_name:
                return True

        # Check if most functions are builtins
        builtin_count = 0
        total_count = 0
        for name, obj in inspect.getmembers(module):
            if name.startswith("_"):
                continue
            if callable(obj):
                total_count += 1
                if self._is_c_extension_callable(obj):
                    builtin_count += 1

        return total_count > 0 and builtin_count / total_count > 0.5

    def _is_c_extension_callable(self, obj: Any) -> bool:
        """Check if a callable is from a C extension.

        Args:
            obj: The object to check

        Returns:
            True if it's a C extension callable
        """
        return (
            isinstance(obj, (BuiltinFunctionType, BuiltinMethodType))
            or inspect.ismethoddescriptor(obj)
            or inspect.isbuiltin(obj)
            or (hasattr(obj, "__objclass__") and not inspect.isfunction(obj))
        )

    def _should_include(self, name: str) -> bool:
        """Check if a name should be included based on filters.

        Args:
            name: The callable name

        Returns:
            True if it should be included
        """
        # Check dunder methods
        if name.startswith("__") and name.endswith("__"):
            return self.include_dunder

        # Check private methods
        if name.startswith("_"):
            return self.include_private

        return True

    def _parse_docstring_signature(
        self, docstring: str | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Parse parameter info from a docstring.

        Many C extension docstrings include signature info like:
        connect(database, timeout=5.0, ...) -> Connection

        Args:
            docstring: The docstring to parse

        Returns:
            Tuple of (parameters list, return type string)
        """
        if not docstring:
            return [], None

        params: list[dict[str, Any]] = []
        return_type: str | None = None

        # Try to find signature pattern: func_name(param1, param2=default) -> ReturnType
        first_line = docstring.split("\n")[0].strip()

        # Match: name(params) -> return_type
        sig_match = re.match(r"^\w+\((.*?)\)(?:\s*->\s*(.+))?$", first_line)
        if sig_match:
            params_str = sig_match.group(1)
            return_type = sig_match.group(2)

            if params_str:
                # Parse parameters
                for param in self._split_params(params_str):
                    param = param.strip()
                    if not param or param in ("...", "/", "*"):
                        continue

                    param_info: dict[str, Any] = {"name": param, "has_default": False}

                    # Check for default value
                    if "=" in param:
                        parts = param.split("=", 1)
                        param_info["name"] = parts[0].strip()
                        param_info["default"] = parts[1].strip()
                        param_info["has_default"] = True

                    # Check for type annotation
                    if ":" in param_info["name"]:
                        name_type = param_info["name"].split(":", 1)
                        param_info["name"] = name_type[0].strip()
                        param_info["type"] = name_type[1].strip()

                    # Skip self/cls
                    if param_info["name"] not in ("self", "cls"):
                        params.append(param_info)

        return params, return_type

    def _split_params(self, params_str: str) -> list[str]:
        """Split parameter string handling nested brackets.

        Args:
            params_str: Parameter string like "a, b=1, c=[1,2]"

        Returns:
            List of individual parameters
        """
        params = []
        depth = 0
        current = ""

        for char in params_str:
            if char in "([{":
                depth += 1
                current += char
            elif char in ")]}":
                depth -= 1
                current += char
            elif char == "," and depth == 0:
                params.append(current.strip())
                current = ""
            else:
                current += char

        if current.strip():
            params.append(current.strip())

        return params

    def analyze_module(self, module: ModuleType) -> tuple[list[CallableInfo], list[ClassInfo]]:
        """Analyze a module and extract callable information.

        Args:
            module: The module to analyze

        Returns:
            Tuple of (functions list, classes list)
        """
        functions: list[CallableInfo] = []
        classes: list[ClassInfo] = []
        module_name = module.__name__

        # Get __all__ if defined
        module_all = set(getattr(module, "__all__", []))

        # Analyze top-level functions
        for name, obj in inspect.getmembers(module):
            if not self._should_include(name):
                continue

            # Skip if not defined in this module (for non-C modules)
            # But include if in __all__
            if (
                hasattr(obj, "__module__")
                and obj.__module__ != module_name
                and module_all
                and name not in module_all
            ):
                continue

            if callable(obj) and not inspect.isclass(obj):
                is_c = self._is_c_extension_callable(obj)
                docstring = inspect.getdoc(obj)
                parsed_params, parsed_return = self._parse_docstring_signature(docstring)

                functions.append(
                    CallableInfo(
                        name=name,
                        qualified_name=name,
                        docstring=docstring,
                        is_method=False,
                        class_name=None,
                        is_c_extension=is_c,
                        parsed_params=parsed_params,
                        parsed_return_type=parsed_return,
                    )
                )

        # Analyze classes
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if not self._should_include(name):
                continue

            # Skip if not defined in this module
            if (
                hasattr(cls, "__module__")
                and cls.__module__ != module_name
                and module_all
                and name not in module_all
            ):
                continue

            class_info = self._analyze_class(cls, module_name)
            if class_info.methods:  # Only include classes with methods
                classes.append(class_info)

        return functions, classes

    def _analyze_class(self, cls: type, module_name: str) -> ClassInfo:
        """Analyze a class and extract method information.

        Args:
            cls: The class to analyze
            module_name: Name of the containing module

        Returns:
            ClassInfo with methods
        """
        methods: list[CallableInfo] = []
        class_name = cls.__name__
        is_c = False

        for name, obj in inspect.getmembers(cls):
            if not self._should_include(name):
                continue

            # Skip inherited from object
            if name in dir(object) and name not in ("__init__", "__new__"):
                continue

            # Check if it's a callable method
            is_method_like = (
                inspect.isfunction(obj)
                or inspect.ismethod(obj)
                or isinstance(obj, (staticmethod, classmethod))
                or inspect.ismethoddescriptor(obj)
                or inspect.isbuiltin(obj)
            )

            if not is_method_like:
                continue

            is_c_method = self._is_c_extension_callable(obj)
            if is_c_method:
                is_c = True

            docstring = inspect.getdoc(obj)
            parsed_params, parsed_return = self._parse_docstring_signature(docstring)

            methods.append(
                CallableInfo(
                    name=name,
                    qualified_name=f"{class_name}.{name}",
                    docstring=docstring,
                    is_method=True,
                    class_name=class_name,
                    is_c_extension=is_c_method,
                    parsed_params=parsed_params,
                    parsed_return_type=parsed_return,
                )
            )

        return ClassInfo(
            name=class_name,
            docstring=inspect.getdoc(cls),
            methods=methods,
            is_c_extension=is_c,
        )

    def generate_wrapper(
        self,
        module: ModuleType,
        output_path: Path | None = None,
    ) -> str:
        """Generate a Python wrapper for a module.

        Args:
            module: The module to wrap
            output_path: Optional path to write the wrapper

        Returns:
            The generated wrapper code as a string
        """
        module_name = module.__name__
        functions, classes = self.analyze_module(module)

        # Build the wrapper code
        lines: list[str] = [
            f'"""Python wrapper for {module_name} module.',
            "",
            "This wrapper provides pure Python functions that delegate to the",
            f"original {module_name} module, making them introspectable for",
            "MCP server generation.",
            '"""',
            "",
            f"import {module_name}",
            "",
        ]

        # Add type imports if we have any
        lines.extend([
            "from typing import Any",
            "",
            "",
        ])

        # Generate function wrappers
        for func in functions:
            lines.extend(self._generate_function_wrapper(func, module_name))
            lines.append("")

        # Generate class wrappers
        for cls_info in classes:
            lines.extend(self._generate_class_wrapper(cls_info, module_name))
            lines.append("")

        code = "\n".join(lines)

        if output_path:
            output_path.write_text(code)

        return code

    def _generate_function_wrapper(
        self,
        func: CallableInfo,
        module_name: str,
    ) -> list[str]:
        """Generate a wrapper function.

        Args:
            func: The function info
            module_name: Name of the source module

        Returns:
            List of code lines
        """
        lines: list[str] = []

        # Build signature
        params = self._build_params_string(func.parsed_params)
        return_hint = f" -> {func.parsed_return_type}" if func.parsed_return_type else " -> Any"

        lines.append(f"def {func.name}({params}){return_hint}:")

        # Add docstring
        if func.docstring:
            doc_lines = func.docstring.split("\n")
            if len(doc_lines) == 1:
                lines.append(f'    """{func.docstring}"""')
            else:
                lines.append(f'    """{doc_lines[0]}')
                for doc_line in doc_lines[1:]:
                    lines.append(f"    {doc_line}")
                lines.append('    """')
        else:
            lines.append(f'    """Wrapper for {module_name}.{func.name}."""')

        # Build call arguments
        call_args = self._build_call_args(func.parsed_params)
        lines.append(f"    return {module_name}.{func.name}({call_args})")

        return lines

    def _generate_class_wrapper(
        self,
        cls_info: ClassInfo,
        module_name: str,
    ) -> list[str]:
        """Generate wrapper functions for a class's methods.

        Instead of wrapping the class, we generate standalone functions
        that take an instance as the first argument.

        Args:
            cls_info: The class info
            module_name: Name of the source module

        Returns:
            List of code lines
        """
        lines: list[str] = []
        class_name = cls_info.name

        # Add a comment for the class section
        lines.append(f"# {class_name} methods")
        lines.append("")

        for method in cls_info.methods:
            # Skip __init__ and __new__ for now
            if method.name in ("__init__", "__new__", "__del__"):
                continue

            # Generate a function with instance as first param
            func_name = f"{class_name.lower()}_{method.name}"

            # Build signature with instance as first param
            params = [f"instance: {module_name}.{class_name}"]
            if method.parsed_params:
                params.extend(self._build_params_list(method.parsed_params))
            params_str = ", ".join(params)

            if method.parsed_return_type:
                return_hint = f" -> {method.parsed_return_type}"
            else:
                return_hint = " -> Any"

            lines.append(f"def {func_name}({params_str}){return_hint}:")

            # Add docstring
            if method.docstring:
                doc_lines = method.docstring.split("\n")
                if len(doc_lines) == 1:
                    lines.append(f'    """{method.docstring}"""')
                else:
                    lines.append(f'    """{doc_lines[0]}')
                    for doc_line in doc_lines[1:]:
                        lines.append(f"    {doc_line}")
                    lines.append('    """')
            else:
                lines.append(f'    """Wrapper for {class_name}.{method.name}."""')

            # Build call
            call_args = self._build_call_args(method.parsed_params)
            lines.append(f"    return instance.{method.name}({call_args})")
            lines.append("")

        return lines

    def _build_params_string(self, params: list[dict[str, Any]]) -> str:
        """Build a parameters string for a function signature.

        Args:
            params: List of parameter info dicts

        Returns:
            Parameter string like "a: int, b: str = 'default'"
        """
        if not params:
            return "*args: Any, **kwargs: Any"

        parts: list[str] = []
        for param in params:
            name = param["name"]
            type_hint = param.get("type", "Any")
            has_default = param.get("has_default", False)
            default = param.get("default", "None")

            if has_default:
                parts.append(f"{name}: {type_hint} = {default}")
            else:
                parts.append(f"{name}: {type_hint}")

        # Add *args, **kwargs for flexibility
        parts.append("*args: Any")
        parts.append("**kwargs: Any")

        return ", ".join(parts)

    def _build_params_list(self, params: list[dict[str, Any]]) -> list[str]:
        """Build a list of parameter strings.

        Args:
            params: List of parameter info dicts

        Returns:
            List of parameter strings
        """
        parts: list[str] = []
        for param in params:
            name = param["name"]
            type_hint = param.get("type", "Any")
            has_default = param.get("has_default", False)
            default = param.get("default", "None")

            if has_default:
                parts.append(f"{name}: {type_hint} = {default}")
            else:
                parts.append(f"{name}: {type_hint}")

        parts.append("*args: Any")
        parts.append("**kwargs: Any")

        return parts

    def _build_call_args(self, params: list[dict[str, Any]]) -> str:
        """Build argument string for calling the original function.

        Args:
            params: List of parameter info dicts

        Returns:
            Call argument string like "a, b, *args, **kwargs"
        """
        if not params:
            return "*args, **kwargs"

        parts = [param["name"] for param in params]
        parts.append("*args")
        parts.append("**kwargs")

        return ", ".join(parts)


def generate_wrapper_for_module(
    module_name: str,
    output_path: Path | str,
    include_private: bool = False,
    include_dunder: bool = False,
) -> Path:
    """Generate a Python wrapper for a module by name.

    Args:
        module_name: Name of the module to wrap (e.g., 'sqlite3')
        output_path: Path to write the wrapper file
        include_private: Whether to include private methods
        include_dunder: Whether to include dunder methods

    Returns:
        Path to the generated wrapper file

    Raises:
        ImportError: If the module cannot be imported
    """
    # Import the module
    module = importlib.import_module(module_name)

    # Generate wrapper
    generator = WrapperGenerator(
        include_private=include_private,
        include_dunder=include_dunder,
    )

    output_path = Path(output_path)
    generator.generate_wrapper(module, output_path)

    return output_path
