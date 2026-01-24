"""MCP server generator from manifest.

This module generates MCP server code from a manifest specification,
integrating with the wrapper generator for C extension signature parsing.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import ModuleType
from typing import Any

from auto_mcp.manifest.dependencies import analyze_and_include_dependencies
from auto_mcp.manifest.resolver import PatternResolver, ResolvedTool
from auto_mcp.manifest.schema import Manifest
from auto_mcp.wrapper.generator import WrapperGenerator
from auto_mcp.wrapper.type_mapper import (
    FunctionSignature,
    ParameterInfo,
    TypeMapper,
)


class ManifestGenerator:
    """Generate MCP server from manifest.

    This generator uses the wrapper generator's signature parsing for
    C extensions and handles complex types with handle-based storage.
    """

    def __init__(self) -> None:
        """Initialize the generator."""
        self.wrapper_gen = WrapperGenerator()
        self.type_mapper = TypeMapper()

    def generate(
        self,
        module: ModuleType,
        manifest: Manifest,
        output_path: Path,
        module_name_override: str | None = None,
    ) -> str:
        """Generate MCP server code from manifest.

        Args:
            module: The module to generate tools from
            manifest: Manifest specifying which tools to expose
            output_path: Path to write the generated server
            module_name_override: Override module name for imports

        Returns:
            The generated server code as a string
        """
        module_name = module_name_override or manifest.get_module_name(module.__name__)

        # Resolve all patterns to tools
        tools = self._resolve_patterns(module, manifest)

        # Auto-include dependencies if enabled
        if manifest.auto_include_dependencies:
            tools = analyze_and_include_dependencies(module, tools)

        # IMPORTANT: Register handle types BEFORE generating code
        # This ensures the type mapper knows about DataFrame, Series, etc.
        # when parsing method signatures that reference these types
        self._register_handle_types_from_tools(tools)

        # Generate MCP server code
        code = self._generate_server_code(manifest, tools, module_name)

        # Write to file
        output_path.write_text(code)

        return code

    def _resolve_patterns(
        self, module: ModuleType, manifest: Manifest
    ) -> list[ResolvedTool]:
        """Resolve all manifest patterns to tools."""
        resolver = PatternResolver(module)
        tools: list[ResolvedTool] = []
        seen: set[str] = set()

        for entry in manifest.get_tool_entries():
            resolved = resolver.resolve(
                entry.function,
                entry.name,
                entry.description,
            )
            for tool in resolved:
                if tool.qualified_name not in seen:
                    seen.add(tool.qualified_name)
                    tools.append(tool)

        return tools

    def _register_handle_types_from_tools(self, tools: list[ResolvedTool]) -> None:
        """Pre-register handle types from tools before parsing signatures.

        This must be called BEFORE generating tool code so that the type mapper
        knows about class types (DataFrame, Series, Connection, etc.) when
        parsing method signatures that reference these types as parameters.

        For example, DataFrame.merge(right: DataFrame) needs to know that
        DataFrame is a handle type so 'right' is properly resolved.
        """
        # Built-in types that should NEVER be handle types
        # These can appear as class_name for accessors (e.g., Series.str.contains has class_name='str')
        builtin_types = {
            'str', 'int', 'float', 'bool', 'list', 'dict', 'set', 'tuple',
            'bytes', 'type', 'object', 'None', 'complex', 'frozenset',
        }

        for tool in tools:
            # Register class names from methods
            if tool.is_method and tool.class_name:
                if tool.class_name not in builtin_types:
                    self.type_mapper.add_handle_type(
                        tool.class_name,
                        f"{tool.class_name} instance handle"
                    )
            # Register class names from constructors
            elif tool.is_constructor:
                class_name = tool.class_name or tool.name
                if class_name not in builtin_types:
                    self.type_mapper.add_handle_type(
                        class_name,
                        f"{class_name} instance handle"
                    )

    def _get_signature(self, tool: ResolvedTool) -> FunctionSignature:
        """Get signature for a tool, using wrapper generator for C extensions."""
        obj = tool.callable_obj

        # Check if this is a C extension callable
        if self.wrapper_gen._is_c_extension_callable(obj):
            return self.wrapper_gen._parse_signature(obj, tool.name.split(".")[-1])

        # For pure Python, use standard inspect
        return self._parse_python_signature(obj, tool.name)

    def _parse_python_signature(
        self, obj: Any, name: str
    ) -> FunctionSignature:
        """Parse signature from a pure Python callable."""
        sig = FunctionSignature(name=name)

        try:
            python_sig = inspect.signature(obj)
        except (ValueError, TypeError):
            # Can't get signature, return empty
            return sig

        for param_name, param in python_sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            if param.kind == param.VAR_POSITIONAL:
                sig.has_var_positional = True
                continue

            if param.kind == param.VAR_KEYWORD:
                sig.has_var_keyword = True
                continue

            # Get type annotation
            type_str = "Any"
            if param.annotation != param.empty:
                type_str = self._annotation_to_str(param.annotation)

            # Get default value
            has_default = param.default != param.empty
            default_value = param.default if has_default else None
            default_repr = repr(default_value) if has_default else "None"

            # Handle special float values (nan, inf) that can't be used without imports
            if has_default and isinstance(default_value, float):
                import math
                if math.isnan(default_value) or math.isinf(default_value):
                    default_value = None
                    default_repr = "None"

            # Handle sentinel values that aren't valid Python (e.g., pandas' <no_default>)
            # These should be treated as having no default or use None
            if has_default and ("<" in default_repr or ">" in default_repr):
                # Check if it's a sentinel type by checking the class name
                type_name = type(default_value).__name__
                if "NoDefault" in type_name or "Sentinel" in type_name or default_repr.startswith("<"):
                    # Treat as optional with None default
                    has_default = True
                    default_value = None
                    default_repr = "None"

            # Map the type
            type_mapping = self.type_mapper.map_type_string(type_str)

            sig.parameters.append(
                ParameterInfo(
                    name=param_name,
                    type_str=self.type_mapper.get_type_str_for_code(type_mapping),
                    json_schema=type_mapping.json_schema,
                    has_default=has_default,
                    default_value=default_value,
                    default_repr=default_repr,
                    is_required=not has_default,
                    is_handle_param=type_mapping.is_handle,
                    handle_type_name=type_mapping.handle_type_name,
                )
            )

        # Get return type
        if python_sig.return_annotation != inspect.Parameter.empty:
            return_str = self._annotation_to_str(python_sig.return_annotation)
            return_mapping = self.type_mapper.map_type_string(return_str)
            sig.return_type_str = self.type_mapper.get_type_str_for_code(return_mapping)
            sig.return_schema = return_mapping.json_schema
            sig.return_is_handle = return_mapping.is_handle
            sig.return_handle_type = return_mapping.handle_type_name

        return sig

    def _annotation_to_str(self, annotation: Any) -> str:
        """Convert a type annotation to a string."""
        if isinstance(annotation, str):
            return annotation
        if hasattr(annotation, "__name__"):
            return annotation.__name__
        if hasattr(annotation, "__origin__"):
            # Generic type like list[str], dict[str, int]
            origin = getattr(annotation, "__origin__", None)
            args = getattr(annotation, "__args__", ())
            if origin is not None:
                origin_name = getattr(origin, "__name__", str(origin))
                if args:
                    args_str = ", ".join(self._annotation_to_str(a) for a in args)
                    return f"{origin_name}[{args_str}]"
                return origin_name
        return str(annotation)

    def _generate_server_code(
        self,
        manifest: Manifest,
        tools: list[ResolvedTool],
        module_name: str,
    ) -> str:
        """Generate the MCP server Python code."""
        server_name = manifest.get_server_name()

        lines = [
            '"""Auto-generated MCP server from manifest.',
            "",
            f"Module: {module_name}",
            f"Server: {server_name}",
            '"""',
            "",
            "from typing import Any",
            "",
            "from mcp.server.fastmcp import FastMCP",
            "",
            f"import {module_name}",
            "",
        ]

        # Generate object store helpers
        lines.extend(self._generate_object_store())

        # Generate FastMCP instance
        lines.append(f'mcp = FastMCP(name="{server_name}")')
        lines.append("")

        # Pre-scan to collect all class names from methods
        # These will be registered as handle types
        registered_handle_types: set[str] = set()
        for tool in tools:
            if tool.is_method and tool.class_name:
                registered_handle_types.add(tool.class_name)
            elif tool.is_constructor:
                class_name = tool.class_name or tool.name
                registered_handle_types.add(class_name)

        # Build factory function inference map
        # Maps lowercase function names to class names they likely return
        factory_return_types = self._build_factory_inference_map(registered_handle_types)

        # Build method return type inference map
        # Maps method names to class names they likely return
        method_return_types = self._build_method_return_inference(registered_handle_types)

        # Collect factory-produced types to skip bare constructors for them
        # If we have a factory function that returns Connection, skip the Connection() constructor
        factory_produced_types = set(factory_return_types.values())

        # Generate tool registrations
        for tool in tools:
            # Skip auto-included constructors if we have a factory function for that type
            if tool.is_constructor and tool.auto_included:
                class_name = tool.class_name or tool.name
                if class_name in factory_produced_types:
                    # We have a factory function (e.g., connect) that produces this type
                    # Skip the bare constructor as it likely can't be instantiated directly
                    continue

            tool_lines = self._generate_tool(
                tool, module_name, registered_handle_types,
                factory_return_types, method_return_types
            )
            lines.extend(tool_lines)
            lines.append("")

        # Generate main entry point
        lines.extend([
            "",
            'if __name__ == "__main__":',
            "    mcp.run()",
        ])

        return "\n".join(lines)

    def _build_factory_inference_map(
        self, handle_types: set[str]
    ) -> dict[str, str]:
        """Build a map of function names to their likely return types.

        This infers return types for factory functions based on naming conventions.
        For example, 'connect' -> 'Connection', 'cursor' -> 'Cursor'.

        Args:
            handle_types: Set of known class names that are handle types

        Returns:
            Dict mapping lowercase function names to class names
        """
        factory_map: dict[str, str] = {}

        for class_name in handle_types:
            # Common patterns:
            # - connect -> Connection
            # - cursor -> Cursor
            # - open -> Open (less common)

            lower_name = class_name.lower()

            # Pattern: function + "ion" = class (e.g., connect -> Connection)
            # connection -> connect (remove "ion")
            if lower_name.endswith("ion"):
                base = lower_name[:-3]  # Remove 'ion' -> "connect"
                factory_map[base] = class_name

            # Pattern: function + "or" = class (e.g., curs + or = cursor)
            # cursor -> curs? This doesn't work well, so just use direct match
            if lower_name.endswith("or"):
                # cursor is both the class name and function name pattern
                factory_map[lower_name] = class_name

            # Direct match: class name as function (e.g., cursor() -> Cursor)
            factory_map[lower_name] = class_name

        return factory_map

    def _build_method_return_inference(
        self, handle_types: set[str]
    ) -> dict[str, str]:
        """Build a map of method names to their likely return types.

        This infers return types for methods that return handle types.
        For example, 'execute' on Connection returns Cursor.

        Args:
            handle_types: Set of known class names that are handle types

        Returns:
            Dict mapping method names to class names they return
        """
        method_map: dict[str, str] = {}

        # Build lowercase lookup for handle types
        handle_types_lower = {ht.lower(): ht for ht in handle_types}

        # Known method patterns that return handle types
        # These are common patterns across many libraries
        known_methods = {
            # Database patterns
            "execute": "Cursor",
            "executemany": "Cursor",
            "executescript": "Cursor",
            "cursor": "Cursor",
            # File patterns
            "open": "File",
            # Iterator patterns
            "iter": "Iterator",
            "__iter__": "Iterator",
        }

        for method_name, return_type in known_methods.items():
            # Only add if the return type is in our handle types
            if return_type.lower() in handle_types_lower:
                method_map[method_name] = handle_types_lower[return_type.lower()]

        return method_map

    def _generate_object_store(self) -> list[str]:
        """Generate object store helper functions."""
        return [
            "# Object store for handle-based types",
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
        ]

    def _generate_tool(
        self,
        tool: ResolvedTool,
        module_name: str,
        registered_handle_types: set[str],
        factory_return_types: dict[str, str] | None = None,
        method_return_types: dict[str, str] | None = None,
    ) -> list[str]:
        """Generate a tool registration."""
        lines: list[str] = []
        factory_return_types = factory_return_types or {}
        method_return_types = method_return_types or {}

        # Get signature
        sig = self._get_signature(tool)

        # Determine tool name
        tool_name = tool.get_tool_name()

        # Build parameters
        if tool.is_constructor:
            # Constructor - no self parameter
            params_str = self._build_params_string(sig.parameters)
            call_args = self._build_call_args(sig.parameters)
            call_target = f"{module_name}.{tool.name}"

            # Register class as handle type
            class_name = tool.class_name or tool.name
            registered_handle_types.add(class_name)

            # Constructor returns a handle
            return_type = "str"
            returns_handle = True
            handle_type = class_name

        elif tool.is_method:
            # Instance method - first param is instance handle
            class_name = tool.class_name or ""
            instance_param = f"{class_name.lower()}: str"

            other_params = self._build_params_string(sig.parameters)
            if other_params:
                params_str = f"{instance_param}, {other_params}"
            else:
                params_str = instance_param

            call_args = self._build_call_args(sig.parameters)
            call_target = None  # Will use instance.method()

            # Check if return type needs handle
            return_type = sig.return_type_str or "Any"
            returns_handle = sig.return_is_handle
            handle_type = sig.return_handle_type

            # Infer return type for methods if not already detected
            if not returns_handle:
                method_name = tool.name.split(".")[-1].lower()
                if method_name in method_return_types:
                    returns_handle = True
                    handle_type = method_return_types[method_name]

        else:
            # Regular function
            params_str = self._build_params_string(sig.parameters)
            call_args = self._build_call_args(sig.parameters)
            call_target = f"{module_name}.{tool.qualified_name}"

            return_type = sig.return_type_str or "Any"
            returns_handle = sig.return_is_handle
            handle_type = sig.return_handle_type

            # Infer return type for factory functions if not already detected
            if not returns_handle:
                func_name = tool.name.split(".")[-1].lower()
                if func_name in factory_return_types:
                    returns_handle = True
                    handle_type = factory_return_types[func_name]

        if returns_handle:
            return_type = "str"

        # Handle variadic parameters
        if sig.has_var_positional:
            params_str = f"{params_str}, *args: Any" if params_str else "*args: Any"
            call_args = f"{call_args}, *args" if call_args else "*args"

        if sig.has_var_keyword:
            params_str = f"{params_str}, **kwargs: Any" if params_str else "**kwargs: Any"
            call_args = f"{call_args}, **kwargs" if call_args else "**kwargs"

        # Generate decorator
        lines.append(f'@mcp.tool(name="{tool_name}")')

        # Generate function definition
        lines.append(f"def {self._safe_function_name(tool_name)}({params_str}) -> {return_type}:")

        # Generate docstring
        docstring = tool.custom_description or self._get_docstring(tool)
        if docstring:
            # Escape and format docstring
            safe_doc = self._escape_docstring(docstring)
            doc_lines = safe_doc.split("\n")
            if len(doc_lines) == 1:
                lines.append(f'    """{safe_doc}"""')
            else:
                lines.append(f'    """{doc_lines[0]}')
                for doc_line in doc_lines[1:]:
                    lines.append(f"    {doc_line}")
                lines.append('    """')
        else:
            lines.append(f'    """Tool: {tool_name}."""')

        # Generate body
        # Check if we need kwargs-based calling (for params with None defaults)
        # Note: C extension methods don't support kwargs, so we must use special handling
        is_c_extension = self._is_c_extension_callable(tool.callable_obj)
        has_none_defaults = self._has_none_default_params(sig.parameters)
        use_kwargs = has_none_defaults and not is_c_extension

        if tool.is_constructor:
            # Constructor call
            if is_c_extension and has_none_defaults:
                # C extension with None defaults - use dynamic args list
                lines.extend(self._generate_c_extension_call_body(
                    sig.parameters, call_target, True, handle_type
                ))
            elif use_kwargs:
                lines.extend(self._generate_kwargs_body(
                    sig.parameters, call_target, True, handle_type
                ))
            else:
                lines.append(f"    result = {call_target}({call_args})")
                lines.append(f'    return _store_object(result, "{handle_type}")')

        elif tool.is_method:
            # Method call
            class_name = tool.class_name or ""
            lines.append(f"    _instance = _get_object({class_name.lower()})")
            method_name = tool.name.split(".")[-1]

            # For C extension methods, use special handling for optional params
            if is_c_extension and has_none_defaults:
                lines.extend(self._generate_c_extension_method_body(
                    sig.parameters, method_name, returns_handle, handle_type
                ))
            elif use_kwargs:
                lines.extend(self._generate_method_kwargs_body(
                    sig.parameters, method_name, returns_handle, handle_type
                ))
            elif returns_handle:
                lines.append(f"    result = _instance.{method_name}({call_args})")
                lines.append(f'    return _store_object(result, "{handle_type}")')
            else:
                lines.append(f"    return _instance.{method_name}({call_args})")

        else:
            # Regular function call
            if is_c_extension and has_none_defaults:
                # C extension with None defaults - use dynamic args list
                lines.extend(self._generate_c_extension_call_body(
                    sig.parameters, call_target, returns_handle, handle_type
                ))
            elif use_kwargs:
                lines.extend(self._generate_kwargs_body(
                    sig.parameters, call_target, returns_handle, handle_type
                ))
            elif returns_handle:
                lines.append(f"    result = {call_target}({call_args})")
                lines.append(f'    return _store_object(result, "{handle_type}")')
            else:
                lines.append(f"    return {call_target}({call_args})")

        return lines

    def _build_params_string(self, params: list[ParameterInfo]) -> str:
        """Build parameter string for function signature."""
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

    def _build_call_args(self, params: list[ParameterInfo], use_positional: bool = False) -> str:
        """Build argument string for calling the function.

        Args:
            params: Parameter list
            use_positional: If True, use positional args instead of kwargs
        """
        if not params:
            return ""

        parts: list[str] = []
        for param in params:
            if param.is_handle_param:
                # Retrieve the actual object from handle
                if use_positional:
                    parts.append(f"_get_object({param.name})")
                else:
                    parts.append(f"{param.name}=_get_object({param.name})")
            else:
                if use_positional:
                    parts.append(param.name)
                else:
                    parts.append(f"{param.name}={param.name}")

        return ", ".join(parts)

    def _is_c_extension_callable(self, obj: Any) -> bool:
        """Check if a callable is from a C extension module."""
        return self.wrapper_gen._is_c_extension_callable(obj)

    def _generate_c_extension_call_body(
        self,
        params: list[ParameterInfo],
        call_target: str,
        returns_handle: bool,
        handle_type: str | None,
    ) -> list[str]:
        """Generate function body for C extension calls.

        C extensions don't support kwargs, so we build a positional args list.
        For optional parameters with None defaults, we stop adding args once
        we hit a None value (since positional args can't skip middle params).
        """
        lines: list[str] = []

        # Separate required and optional parameters
        required_params = [p for p in params if not p.has_default]
        optional_params = [p for p in params if p.has_default]

        # Build args list
        lines.append("    _args = []")

        # Add required parameters (they're always passed)
        for param in required_params:
            if param.is_handle_param:
                lines.append(f"    _args.append(_get_object({param.name}))")
            else:
                lines.append(f"    _args.append({param.name})")

        # Add optional parameters, but stop once we hit a None-default param that is None
        # This is because positional args can't skip middle parameters
        if optional_params:
            lines.append("    # Add optional params - stop at first None-default param that is None")
            lines.append("    _stop_adding = False")
            for param in optional_params:
                if param.default_value is None:
                    # This param has None as default - check if we should stop
                    lines.append(f"    if not _stop_adding and {param.name} is not None:")
                    if param.is_handle_param:
                        lines.append(f"        _args.append(_get_object({param.name}))")
                    else:
                        lines.append(f"        _args.append({param.name})")
                    lines.append(f"    elif {param.name} is None:")
                    lines.append("        _stop_adding = True")
                else:
                    # Non-None default - add if we haven't stopped
                    lines.append("    if not _stop_adding:")
                    if param.is_handle_param:
                        lines.append(f"        _args.append(_get_object({param.name}))")
                    else:
                        lines.append(f"        _args.append({param.name})")

        if returns_handle and handle_type:
            lines.append(f"    result = {call_target}(*_args)")
            lines.append(f'    return _store_object(result, "{handle_type}")')
        else:
            lines.append(f"    return {call_target}(*_args)")

        return lines

    def _generate_c_extension_method_body(
        self,
        params: list[ParameterInfo],
        method_name: str,
        returns_handle: bool,
        handle_type: str | None,
    ) -> list[str]:
        """Generate method body for C extension calls.

        Similar to _generate_c_extension_call_body but for instance methods.
        """
        lines: list[str] = []

        # Separate required and optional parameters
        required_params = [p for p in params if not p.has_default]
        optional_params = [p for p in params if p.has_default]

        # Build args list
        lines.append("    _args = []")

        # Add required parameters
        for param in required_params:
            if param.is_handle_param:
                lines.append(f"    _args.append(_get_object({param.name}))")
            else:
                lines.append(f"    _args.append({param.name})")

        # Add optional parameters, but stop once we hit a None-default param that is None
        if optional_params:
            lines.append("    # Add optional params - stop at first None-default param that is None")
            lines.append("    _stop_adding = False")
            for param in optional_params:
                if param.default_value is None:
                    lines.append(f"    if not _stop_adding and {param.name} is not None:")
                    if param.is_handle_param:
                        lines.append(f"        _args.append(_get_object({param.name}))")
                    else:
                        lines.append(f"        _args.append({param.name})")
                    lines.append(f"    elif {param.name} is None:")
                    lines.append("        _stop_adding = True")
                else:
                    lines.append("    if not _stop_adding:")
                    if param.is_handle_param:
                        lines.append(f"        _args.append(_get_object({param.name}))")
                    else:
                        lines.append(f"        _args.append({param.name})")

        if returns_handle and handle_type:
            lines.append(f"    result = _instance.{method_name}(*_args)")
            lines.append(f'    return _store_object(result, "{handle_type}")')
        else:
            lines.append(f"    return _instance.{method_name}(*_args)")

        return lines

    def _has_none_default_params(self, params: list[ParameterInfo]) -> bool:
        """Check if any parameters have None as their default value."""
        return any(
            p.has_default and p.default_value is None
            for p in params
        )

    def _generate_kwargs_body(
        self,
        params: list[ParameterInfo],
        call_target: str,
        returns_handle: bool,
        handle_type: str | None,
    ) -> list[str]:
        """Generate function body using kwargs to skip None defaults.

        This is needed for C extension functions that treat 'param not passed'
        differently from 'param=None'.
        """
        lines: list[str] = []
        lines.append("    _kwargs = {}")

        for param in params:
            if param.is_handle_param:
                # Handle params are always passed
                lines.append(f"    _kwargs['{param.name}'] = _get_object({param.name})")
            elif param.has_default and param.default_value is None:
                # Only add if not None (skip None defaults)
                lines.append(f"    if {param.name} is not None:")
                lines.append(f"        _kwargs['{param.name}'] = {param.name}")
            else:
                # Always pass this parameter
                lines.append(f"    _kwargs['{param.name}'] = {param.name}")

        if returns_handle and handle_type:
            lines.append(f"    result = {call_target}(**_kwargs)")
            lines.append(f'    return _store_object(result, "{handle_type}")')
        else:
            lines.append(f"    return {call_target}(**_kwargs)")

        return lines

    def _generate_method_kwargs_body(
        self,
        params: list[ParameterInfo],
        method_name: str,
        returns_handle: bool,
        handle_type: str | None,
    ) -> list[str]:
        """Generate method body using kwargs to properly handle optional parameters.

        Using keyword arguments allows skipping optional middle parameters,
        which is essential for methods like groupby() where you might pass
        'by' but skip 'axis' and 'level'.
        """
        lines: list[str] = []
        lines.append("    _kwargs = {}")

        for param in params:
            if param.is_handle_param:
                # Handle params are always passed (resolved from object store)
                lines.append(f"    _kwargs['{param.name}'] = _get_object({param.name})")
            elif param.has_default and param.default_value is None:
                # Only add if not None (skip None defaults)
                lines.append(f"    if {param.name} is not None:")
                lines.append(f"        _kwargs['{param.name}'] = {param.name}")
            else:
                # Always pass this parameter
                lines.append(f"    _kwargs['{param.name}'] = {param.name}")

        if returns_handle and handle_type:
            lines.append(f"    result = _instance.{method_name}(**_kwargs)")
            lines.append(f'    return _store_object(result, "{handle_type}")')
        else:
            lines.append(f"    return _instance.{method_name}(**_kwargs)")

        return lines

    def _get_docstring(self, tool: ResolvedTool) -> str | None:
        """Get docstring for a tool."""
        doc = inspect.getdoc(tool.callable_obj)
        return doc

    def _escape_docstring(self, docstring: str) -> str:
        """Escape a docstring for safe inclusion in generated code."""
        # Escape backslashes to prevent unicode escape errors
        return docstring.replace("\\", "\\\\")

    def _safe_function_name(self, name: str) -> str:
        """Convert a tool name to a valid Python function name."""
        # Replace dots, dashes, and other invalid chars with underscores
        result = name.replace(".", "_").replace("-", "_")
        # Ensure it starts with a letter or underscore
        if result and result[0].isdigit():
            result = f"_{result}"
        return result


def generate_from_manifest(
    module: ModuleType,
    manifest_path: Path,
    output_path: Path,
    module_name: str | None = None,
) -> str:
    """Generate MCP server from a manifest file.

    This is the main entry point for manifest-based generation.

    Args:
        module: The module to generate from
        manifest_path: Path to the YAML manifest file
        output_path: Path to write the generated server
        module_name: Optional override for module name

    Returns:
        The generated server code
    """
    manifest = Manifest.from_yaml(manifest_path)
    generator = ManifestGenerator()
    return generator.generate(module, manifest, output_path, module_name)
