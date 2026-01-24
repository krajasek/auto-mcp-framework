"""Wrapper generator for C extension modules.

This module generates Python wrappers for C extension modules,
making them introspectable for MCP server generation with proper
named parameters and type annotations.
"""

from __future__ import annotations

import importlib
import inspect
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import BuiltinFunctionType, BuiltinMethodType, ModuleType
from typing import Any

from auto_mcp.wrapper.type_mapper import (
    FunctionSignature,
    ParameterInfo,
    TypeMapper,
    parse_default_value,
)


@dataclass
class CallableInfo:
    """Information about a callable in a module."""

    name: str
    qualified_name: str
    docstring: str | None
    is_method: bool
    class_name: str | None
    is_c_extension: bool
    signature: FunctionSignature | None = None


@dataclass
class ClassInfo:
    """Information about a class in a module."""

    name: str
    docstring: str | None
    methods: list[CallableInfo] = field(default_factory=list)
    is_c_extension: bool = False


class WrapperGenerator:
    """Generates Python wrappers for C extension modules.

    This creates pure Python wrapper functions with proper named parameters,
    type annotations, and JSON schemas suitable for MCP tool generation.
    """

    def __init__(
        self,
        include_private: bool = False,
        include_dunder: bool = False,
        type_mapper: TypeMapper | None = None,
    ) -> None:
        """Initialize the wrapper generator.

        Args:
            include_private: Whether to include private methods (starting with _)
            include_dunder: Whether to include dunder methods (__init__, etc.)
            type_mapper: Custom type mapper for type string conversion
        """
        self.include_private = include_private
        self.include_dunder = include_dunder
        self.type_mapper = type_mapper or TypeMapper()

    def is_c_extension_module(self, module: ModuleType) -> bool:
        """Check if a module is a C extension module or wraps C extensions.

        This includes:
        - Pure C extension modules (.so/.pyd files)
        - Built-in modules (builtins, sys)
        - Python modules that wrap C extensions (like sqlite3 wrapping _sqlite3)

        Args:
            module: The module to check

        Returns:
            True if the module is or wraps a C extension
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

        # Check if module has C extension callables
        # Count functions and class methods that are C extensions
        builtin_func_count = 0
        total_func_count = 0
        class_with_c_methods = False

        for name, obj in inspect.getmembers(module):
            if name.startswith("_"):
                continue

            # Check top-level functions
            if callable(obj) and not inspect.isclass(obj):
                total_func_count += 1
                if self._is_c_extension_callable(obj):
                    builtin_func_count += 1

            # Check classes for C extension methods
            if inspect.isclass(obj):
                for method_name in dir(obj):
                    if method_name.startswith("_"):
                        continue
                    try:
                        method = getattr(obj, method_name)
                        if callable(method) and self._is_c_extension_callable(method):
                            class_with_c_methods = True
                            break
                    except (AttributeError, TypeError):
                        continue
                if class_with_c_methods:
                    break

        # Consider it a C extension module if:
        # 1. More than 30% of functions are C extensions, OR
        # 2. Any class has C extension methods
        has_significant_c_funcs = (
            total_func_count > 0 and builtin_func_count / total_func_count > 0.3
        )
        return has_significant_c_funcs or class_with_c_methods

    def _is_c_extension_callable(self, obj: Any) -> bool:
        """Check if a callable is from a C extension."""
        return (
            isinstance(obj, (BuiltinFunctionType, BuiltinMethodType))
            or inspect.ismethoddescriptor(obj)
            or inspect.isbuiltin(obj)
            or (hasattr(obj, "__objclass__") and not inspect.isfunction(obj))
        )

    def _should_include(self, name: str) -> bool:
        """Check if a name should be included based on filters."""
        if name.startswith("__") and name.endswith("__"):
            return self.include_dunder
        if name.startswith("_"):
            return self.include_private
        return True

    def _parse_signature(
        self, obj: Any, func_name: str
    ) -> FunctionSignature:
        """Parse parameter and return info from a callable.

        Tries multiple sources in order:
        1. __text_signature__ attribute (common for C extensions)
        2. Docstring first line (fallback)

        Args:
            obj: The callable object
            func_name: Name of the function

        Returns:
            FunctionSignature with parsed parameters and return type
        """
        sig = FunctionSignature(name=func_name)

        # Try __text_signature__ first (common for C extensions)
        text_sig = getattr(obj, "__text_signature__", None)
        if text_sig:
            result = self._parse_text_signature(text_sig, func_name)
            if result.parameters:
                return result

        # Fall back to docstring parsing
        docstring = inspect.getdoc(obj)
        return self._parse_docstring_signature(docstring, func_name)

    def _parse_text_signature(
        self, text_sig: str, func_name: str
    ) -> FunctionSignature:
        """Parse a __text_signature__ attribute.

        Args:
            text_sig: The text signature like "($module, /, database, timeout=5.0)"
            func_name: Name of the function

        Returns:
            FunctionSignature with parsed parameters
        """
        sig = FunctionSignature(name=func_name)

        # Clean up multiline signatures
        text_sig = " ".join(text_sig.split())

        # Extract parameters from parentheses
        paren_match = re.search(r"\((.*)\)", text_sig)
        if not paren_match:
            return sig

        params_str = paren_match.group(1)

        # Parse parameters
        for param_str in self._split_params(params_str):
            param_str = param_str.strip()

            # Skip special markers
            if not param_str or param_str in ("...", "/", "*"):
                continue

            # Skip $module, $self, $cls
            if param_str.startswith("$"):
                continue

            # Handle *args
            if param_str.startswith("*") and not param_str.startswith("**"):
                sig.has_var_positional = True
                continue

            # Handle **kwargs
            if param_str.startswith("**"):
                sig.has_var_keyword = True
                continue

            param_info = self._parse_parameter(param_str)
            if param_info and param_info.name not in ("self", "cls"):
                sig.parameters.append(param_info)

        return sig

    def _parse_docstring_signature(
        self, docstring: str | None, func_name: str
    ) -> FunctionSignature:
        """Parse parameter and return info from a docstring.

        Many C extension docstrings include signature info like:
        connect(database, timeout=5.0, ...) -> Connection

        Args:
            docstring: The docstring to parse
            func_name: Name of the function

        Returns:
            FunctionSignature with parsed parameters and return type
        """
        sig = FunctionSignature(name=func_name)

        if not docstring:
            return sig

        # Get first line for signature
        first_line = docstring.split("\n")[0].strip()

        # Match: name(params) -> return_type
        sig_match = re.match(r"^\w+\((.*?)\)(?:\s*->\s*(.+?))?\.?$", first_line)
        if not sig_match:
            return sig

        params_str = sig_match.group(1)
        return_type_str = sig_match.group(2)

        # Parse return type
        if return_type_str:
            return_type_str = return_type_str.strip()
            return_mapping = self.type_mapper.map_type_string(return_type_str)
            sig.return_type_str = self.type_mapper.get_type_str_for_code(return_mapping)
            sig.return_schema = return_mapping.json_schema
            sig.return_is_handle = return_mapping.is_handle
            sig.return_handle_type = return_mapping.handle_type_name

        # Parse parameters
        if params_str:
            for param_str in self._split_params(params_str):
                param_str = param_str.strip()

                # Skip special markers
                if not param_str or param_str in ("...",):
                    continue

                # Handle positional-only marker
                if param_str == "/":
                    continue

                # Handle keyword-only marker
                if param_str == "*":
                    continue

                # Handle *args
                if param_str.startswith("*") and not param_str.startswith("**"):
                    sig.has_var_positional = True
                    continue

                # Handle **kwargs
                if param_str.startswith("**"):
                    sig.has_var_keyword = True
                    continue

                param_info = self._parse_parameter(param_str)
                if param_info and param_info.name not in ("self", "cls"):
                    sig.parameters.append(param_info)

        return sig

    def _split_params(self, params_str: str) -> list[str]:
        """Split parameter string handling nested brackets."""
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

    def _parse_parameter(self, param_str: str) -> ParameterInfo | None:
        """Parse a single parameter string.

        Args:
            param_str: Parameter string like "name: str = 'default'"

        Returns:
            ParameterInfo or None if invalid
        """
        param_str = param_str.strip()
        if not param_str:
            return None

        name = param_str
        type_str = "Any"
        has_default = False
        default_value: Any = None
        default_repr = "None"

        # Check for default value
        if "=" in param_str:
            parts = param_str.split("=", 1)
            name = parts[0].strip()
            default_str = parts[1].strip()
            has_default = True
            default_value, default_repr = parse_default_value(default_str)

        # Check for type annotation
        if ":" in name:
            name_parts = name.split(":", 1)
            name = name_parts[0].strip()
            type_str = name_parts[1].strip()

        # Validate name
        if not name or not name.isidentifier():
            return None

        # Map the type
        type_mapping = self.type_mapper.map_type_string(type_str)
        code_type_str = self.type_mapper.get_type_str_for_code(type_mapping)

        return ParameterInfo(
            name=name,
            type_str=code_type_str,
            json_schema=type_mapping.json_schema,
            has_default=has_default,
            default_value=default_value,
            default_repr=default_repr,
            is_required=not has_default,
            is_handle_param=type_mapping.is_handle,
            handle_type_name=type_mapping.handle_type_name,
        )

    def analyze_module(
        self, module: ModuleType
    ) -> tuple[list[CallableInfo], list[ClassInfo]]:
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

            # Skip if not defined in this module
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
                signature = self._parse_signature(obj, name)

                functions.append(
                    CallableInfo(
                        name=name,
                        qualified_name=name,
                        docstring=docstring,
                        is_method=False,
                        class_name=None,
                        is_c_extension=is_c,
                        signature=signature,
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
            if class_info.methods:
                classes.append(class_info)

        return functions, classes

    def _analyze_class(self, cls: type, module_name: str) -> ClassInfo:
        """Analyze a class and extract method information."""
        methods: list[CallableInfo] = []
        class_name = cls.__name__
        is_c = False

        for name, obj in inspect.getmembers(cls):
            if not self._should_include(name):
                continue

            # Skip inherited from object
            if name in dir(object) and name not in ("__init__", "__new__"):
                continue

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
            signature = self._parse_signature(obj, name)

            methods.append(
                CallableInfo(
                    name=name,
                    qualified_name=f"{class_name}.{name}",
                    docstring=docstring,
                    is_method=True,
                    class_name=class_name,
                    is_c_extension=is_c_method,
                    signature=signature,
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

        lines: list[str] = []

        # Generate header and imports
        lines.extend(self._generate_header(module_name))
        lines.append("")

        # Generate object store helpers
        lines.extend(self._generate_object_store())
        lines.append("")

        # Track generated schemas for module-level export
        schema_names: list[str] = []

        # Generate function wrappers
        for func in functions:
            wrapper_lines, schema_name = self._generate_function_wrapper(func, module_name)
            lines.extend(wrapper_lines)
            lines.append("")
            if schema_name:
                schema_names.append(schema_name)

        # Generate class method wrappers
        for cls_info in classes:
            wrapper_lines, cls_schema_names = self._generate_class_wrappers(
                cls_info, module_name
            )
            lines.extend(wrapper_lines)
            lines.append("")
            schema_names.extend(cls_schema_names)

        # Generate __all__ export
        lines.extend(self._generate_exports(functions, classes))

        code = "\n".join(lines)

        if output_path:
            output_path.write_text(code)

        return code

    def _generate_header(self, module_name: str) -> list[str]:
        """Generate module header with imports."""
        return [
            f'"""Python wrapper for {module_name} module.',
            "",
            "This wrapper provides pure Python functions with explicit named parameters,",
            f"delegating to the original {module_name} module. Generated for MCP server use.",
            '"""',
            "",
            "from __future__ import annotations",
            "",
            f"import {module_name}",
            "from typing import Any",
            "",
        ]

    def _generate_object_store(self) -> list[str]:
        """Generate object store helper functions for handle management."""
        return [
            "# Object store for handle-based type management",
            "_object_store: dict[str, Any] = {}",
            "_handle_counter: int = 0",
            "",
            "",
            "def _store_object(obj: Any, type_name: str) -> str:",
            '    """Store an object and return a handle string."""',
            "    global _handle_counter",
            "    _handle_counter += 1",
            '    handle = f"{type_name}_{_handle_counter}"',
            "    _object_store[handle] = obj",
            "    return handle",
            "",
            "",
            "def _get_object(handle: str) -> Any:",
            '    """Retrieve an object by its handle."""',
            "    obj = _object_store.get(handle)",
            "    if obj is None:",
            '        raise ValueError(f"Invalid or expired handle: {handle}")',
            "    return obj",
            "",
            "",
            "def _release_object(handle: str) -> bool:",
            '    """Release an object by its handle. Returns True if found."""',
            "    return _object_store.pop(handle, None) is not None",
            "",
            "",
            "def _list_handles(type_prefix: str | None = None) -> list[str]:",
            '    """List all active handles, optionally filtered by type prefix."""',
            "    if type_prefix:",
            '        return [h for h in _object_store.keys() if h.startswith(f"{type_prefix}_")]',
            "    return list(_object_store.keys())",
            "",
        ]

    def _generate_function_wrapper(
        self, func: CallableInfo, module_name: str
    ) -> tuple[list[str], str | None]:
        """Generate a wrapper function.

        Returns:
            Tuple of (code lines, schema variable name or None)
        """
        lines: list[str] = []
        sig = func.signature or FunctionSignature(name=func.name)

        # Build parameter string (no *args, **kwargs unless explicit)
        params_str = self._build_params_string(sig.parameters)
        call_args = self._build_call_args(sig.parameters)

        # Handle variadic if explicitly in signature
        if sig.has_var_positional:
            if params_str:
                params_str += ", *args: Any"
            else:
                params_str = "*args: Any"
            call_args = f"{call_args}, *args" if call_args else "*args"

        if sig.has_var_keyword:
            if params_str:
                params_str += ", **kwargs: Any"
            else:
                params_str = "**kwargs: Any"
            call_args = f"{call_args}, **kwargs" if call_args else "**kwargs"

        # Determine return type
        return_type = sig.return_type_str if sig.return_type_str else "Any"
        if sig.return_is_handle:
            return_type = "str"

        # Generate function definition
        lines.append(f"def {func.name}({params_str}) -> {return_type}:")

        # Generate docstring
        self._add_docstring(lines, func.docstring, func.name, module_name)

        # Generate function body
        if sig.return_is_handle and sig.return_handle_type:
            # Store result and return handle
            lines.append(
                f"    _result = {module_name}.{func.name}({call_args})"
            )
            lines.append(
                f'    return _store_object(_result, "{sig.return_handle_type}")'
            )
        else:
            lines.append(f"    return {module_name}.{func.name}({call_args})")

        # Generate schema
        schema_name = f"_{func.name}_schema"
        schema = self._build_json_schema(sig)
        lines.append("")
        lines.append(f"{func.name}.__mcp_schema__ = {repr(schema)}")

        return lines, schema_name

    def _generate_class_wrappers(
        self, cls_info: ClassInfo, module_name: str
    ) -> tuple[list[str], list[str]]:
        """Generate wrapper functions for a class's methods."""
        lines: list[str] = []
        schema_names: list[str] = []
        class_name = cls_info.name

        # Add section comment
        lines.append(f"# ============================================================================")
        lines.append(f"# {class_name} methods")
        lines.append(f"# ============================================================================")
        lines.append("")

        # Register the class as a handle type
        self.type_mapper.add_handle_type(
            class_name, f"{class_name} instance from {module_name}"
        )

        for method in cls_info.methods:
            # Skip __init__, __new__, __del__ for now
            if method.name in ("__init__", "__new__", "__del__"):
                continue

            wrapper_lines, schema_name = self._generate_method_wrapper(
                method, class_name, module_name
            )
            lines.extend(wrapper_lines)
            lines.append("")
            if schema_name:
                schema_names.append(schema_name)

        return lines, schema_names

    def _generate_method_wrapper(
        self, method: CallableInfo, class_name: str, module_name: str
    ) -> tuple[list[str], str | None]:
        """Generate a wrapper function for a class method."""
        lines: list[str] = []
        sig = method.signature or FunctionSignature(name=method.name)

        # Function name: classname_methodname
        func_name = f"{class_name.lower()}_{method.name}"

        # First parameter is the instance handle
        instance_param = f"{class_name.lower()}: str"

        # Build other parameters
        other_params = self._build_params_string(sig.parameters)
        if other_params:
            params_str = f"{instance_param}, {other_params}"
        else:
            params_str = instance_param

        # Handle variadic
        if sig.has_var_positional:
            params_str += ", *args: Any"
        if sig.has_var_keyword:
            params_str += ", **kwargs: Any"

        # Build call args
        call_args = self._build_call_args(sig.parameters)
        if sig.has_var_positional:
            call_args = f"{call_args}, *args" if call_args else "*args"
        if sig.has_var_keyword:
            call_args = f"{call_args}, **kwargs" if call_args else "**kwargs"

        # Determine return type
        return_type = sig.return_type_str if sig.return_type_str else "Any"
        if sig.return_is_handle:
            return_type = "str"

        # Generate function definition
        lines.append(f"def {func_name}({params_str}) -> {return_type}:")

        # Generate docstring
        self._add_method_docstring(
            lines, method.docstring, method.name, class_name, module_name
        )

        # Generate function body
        lines.append(f"    _instance = _get_object({class_name.lower()})")

        if sig.return_is_handle and sig.return_handle_type:
            lines.append(f"    _result = _instance.{method.name}({call_args})")
            lines.append(
                f'    return _store_object(_result, "{sig.return_handle_type}")'
            )
        else:
            lines.append(f"    return _instance.{method.name}({call_args})")

        # Generate schema
        schema = self._build_method_schema(sig, class_name)
        lines.append("")
        lines.append(f"{func_name}.__mcp_schema__ = {repr(schema)}")

        return lines, f"_{func_name}_schema"

    def _build_params_string(self, params: list[ParameterInfo]) -> str:
        """Build parameter string for function signature.

        This generates ONLY explicit named parameters, no *args/**kwargs
        unless they are explicitly part of the parsed signature.
        """
        if not params:
            return ""

        parts: list[str] = []

        # Sort: required params first, then optional params
        sorted_params = sorted(params, key=lambda p: p.has_default)

        for param in sorted_params:
            type_str = param.type_str
            if param.is_handle_param:
                type_str = "str"

            if param.has_default:
                parts.append(f"{param.name}: {type_str} = {param.default_repr}")
            else:
                parts.append(f"{param.name}: {type_str}")

        return ", ".join(parts)

    def _build_call_args(self, params: list[ParameterInfo]) -> str:
        """Build argument string for calling the original function.

        Uses keyword arguments for all parameters to ensure correct passing.
        """
        if not params:
            return ""

        parts: list[str] = []
        for param in params:
            if param.is_handle_param:
                # Retrieve the actual object from handle
                parts.append(f"{param.name}=_get_object({param.name})")
            else:
                parts.append(f"{param.name}={param.name}")

        return ", ".join(parts)

    def _build_json_schema(self, sig: FunctionSignature) -> dict[str, Any]:
        """Build JSON schema for a function."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in sig.parameters:
            prop = dict(param.json_schema)
            if param.is_handle_param:
                prop = {
                    "type": "string",
                    "description": f"{param.handle_type_name or param.name} handle",
                }

            properties[param.name] = prop

            if param.is_required:
                required.append(param.name)

        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }

        if required:
            schema["required"] = required

        # Add return schema if present
        if sig.return_schema or sig.return_is_handle:
            if sig.return_is_handle:
                schema["returns"] = {
                    "type": "string",
                    "description": f"{sig.return_handle_type or 'Result'} handle",
                }
            else:
                schema["returns"] = sig.return_schema

        return schema

    def _build_method_schema(
        self, sig: FunctionSignature, class_name: str
    ) -> dict[str, Any]:
        """Build JSON schema for a method (includes instance parameter)."""
        properties: dict[str, Any] = {
            class_name.lower(): {
                "type": "string",
                "description": f"{class_name} instance handle",
            }
        }
        required: list[str] = [class_name.lower()]

        for param in sig.parameters:
            prop = dict(param.json_schema)
            if param.is_handle_param:
                prop = {
                    "type": "string",
                    "description": f"{param.handle_type_name or param.name} handle",
                }

            properties[param.name] = prop

            if param.is_required:
                required.append(param.name)

        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "required": required,
        }

        if sig.return_schema or sig.return_is_handle:
            if sig.return_is_handle:
                schema["returns"] = {
                    "type": "string",
                    "description": f"{sig.return_handle_type or 'Result'} handle",
                }
            else:
                schema["returns"] = sig.return_schema

        return schema

    def _escape_docstring(self, docstring: str) -> str:
        """Escape a docstring for safe inclusion in generated code.

        Handles backslash sequences that would be interpreted as escape codes.
        """
        # Escape backslashes that could be interpreted as escape sequences
        # We need to be careful to not double-escape already valid escapes
        result = docstring

        # Replace backslashes with escaped backslashes, but preserve newlines/tabs
        # that are already in the string (they're actual newlines, not \n literals)
        # The issue is with literal backslash followed by characters like u, x, etc.
        result = result.replace("\\", "\\\\")

        return result

    def _add_docstring(
        self,
        lines: list[str],
        docstring: str | None,
        func_name: str,
        module_name: str,
    ) -> None:
        """Add docstring to function."""
        if docstring:
            # Escape backslashes to prevent unicode escape errors
            safe_docstring = self._escape_docstring(docstring)
            doc_lines = safe_docstring.split("\n")
            if len(doc_lines) == 1:
                lines.append(f'    """{safe_docstring}"""')
            else:
                lines.append(f'    """{doc_lines[0]}')
                for doc_line in doc_lines[1:]:
                    lines.append(f"    {doc_line}")
                lines.append('    """')
        else:
            lines.append(f'    """Wrapper for {module_name}.{func_name}."""')

    def _add_method_docstring(
        self,
        lines: list[str],
        docstring: str | None,
        method_name: str,
        class_name: str,
        module_name: str,
    ) -> None:
        """Add docstring to method wrapper."""
        if docstring:
            # Escape backslashes and prepend note about instance parameter
            safe_docstring = self._escape_docstring(docstring)
            doc_lines = safe_docstring.split("\n")
            lines.append(f'    """{doc_lines[0]}')
            lines.append("")
            lines.append(f"    Note: {class_name.lower()} is a handle string from a previous call.")
            if len(doc_lines) > 1:
                for doc_line in doc_lines[1:]:
                    lines.append(f"    {doc_line}")
            lines.append('    """')
        else:
            lines.append(
                f'    """Wrapper for {module_name}.{class_name}.{method_name}.'
            )
            lines.append("")
            lines.append(f"    Args:")
            lines.append(f"        {class_name.lower()}: Handle string for {class_name} instance")
            lines.append('    """')

    def _generate_exports(
        self, functions: list[CallableInfo], classes: list[ClassInfo]
    ) -> list[str]:
        """Generate __all__ export list."""
        names = []

        # Add helper functions
        names.extend([
            "_store_object",
            "_get_object",
            "_release_object",
            "_list_handles",
        ])

        # Add function names
        for func in functions:
            names.append(func.name)

        # Add method wrapper names
        for cls_info in classes:
            for method in cls_info.methods:
                if method.name not in ("__init__", "__new__", "__del__"):
                    names.append(f"{cls_info.name.lower()}_{method.name}")

        lines = [
            "",
            "# Exported names",
            f"__all__ = {repr(names)}",
        ]

        return lines


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
    module = importlib.import_module(module_name)

    generator = WrapperGenerator(
        include_private=include_private,
        include_dunder=include_dunder,
    )

    output_path = Path(output_path)
    generator.generate_wrapper(module, output_path)

    return output_path
