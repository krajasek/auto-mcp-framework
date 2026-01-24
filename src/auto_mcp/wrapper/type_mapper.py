"""Type mapping utilities for wrapper generation.

This module maps docstring type strings to Python types and JSON schemas,
enabling proper type annotations and parameter schemas in generated wrappers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TypeMapping:
    """Mapping information for a type string."""

    python_type: type | str  # Python type or string representation
    json_schema: dict[str, Any]
    is_handle: bool = False  # Whether this type should use handle-based storage
    handle_type_name: str | None = None  # Name for handle (e.g., "Connection")


# Known type mappings from docstring type strings to Python types and JSON schemas
TYPE_MAPPINGS: dict[str, TypeMapping] = {
    # Basic types
    "str": TypeMapping(str, {"type": "string"}),
    "string": TypeMapping(str, {"type": "string"}),
    "int": TypeMapping(int, {"type": "integer"}),
    "integer": TypeMapping(int, {"type": "integer"}),
    "float": TypeMapping(float, {"type": "number"}),
    "number": TypeMapping(float, {"type": "number"}),
    "double": TypeMapping(float, {"type": "number"}),
    "bool": TypeMapping(bool, {"type": "boolean"}),
    "boolean": TypeMapping(bool, {"type": "boolean"}),
    "bytes": TypeMapping(
        bytes,
        {"type": "string", "contentEncoding": "base64", "description": "Base64-encoded bytes"},
    ),
    "bytearray": TypeMapping(
        bytearray,
        {"type": "string", "contentEncoding": "base64", "description": "Base64-encoded bytes"},
    ),
    # Collections
    "list": TypeMapping(list, {"type": "array"}),
    "array": TypeMapping(list, {"type": "array"}),
    "dict": TypeMapping(dict, {"type": "object"}),
    "dictionary": TypeMapping(dict, {"type": "object"}),
    "mapping": TypeMapping(dict, {"type": "object"}),
    "tuple": TypeMapping(tuple, {"type": "array"}),
    "set": TypeMapping(set, {"type": "array", "uniqueItems": True}),
    "frozenset": TypeMapping(frozenset, {"type": "array", "uniqueItems": True}),
    "sequence": TypeMapping(list, {"type": "array"}),
    "iterable": TypeMapping(list, {"type": "array"}),
    # Special types
    "none": TypeMapping(type(None), {"type": "null"}),
    "None": TypeMapping(type(None), {"type": "null"}),
    "any": TypeMapping("Any", {}),
    "Any": TypeMapping("Any", {}),
    "object": TypeMapping("Any", {"type": "object"}),
    "callable": TypeMapping("Callable", {"type": "string", "description": "Callable reference"}),
    "Callable": TypeMapping("Callable", {"type": "string", "description": "Callable reference"}),
    "type": TypeMapping("type", {"type": "string", "description": "Type reference"}),
    # Common handle types (database-related)
    "Connection": TypeMapping(
        "str",
        {"type": "string", "description": "Connection handle"},
        is_handle=True,
        handle_type_name="Connection",
    ),
    "connection": TypeMapping(
        "str",
        {"type": "string", "description": "Connection handle"},
        is_handle=True,
        handle_type_name="Connection",
    ),
    "Cursor": TypeMapping(
        "str",
        {"type": "string", "description": "Cursor handle"},
        is_handle=True,
        handle_type_name="Cursor",
    ),
    "cursor": TypeMapping(
        "str",
        {"type": "string", "description": "Cursor handle"},
        is_handle=True,
        handle_type_name="Cursor",
    ),
    "Blob": TypeMapping(
        "str",
        {"type": "string", "description": "Blob handle"},
        is_handle=True,
        handle_type_name="Blob",
    ),
    "blob": TypeMapping(
        "str",
        {"type": "string", "description": "Blob handle"},
        is_handle=True,
        handle_type_name="Blob",
    ),
    # File/IO types
    "file": TypeMapping(
        "str",
        {"type": "string", "description": "File handle"},
        is_handle=True,
        handle_type_name="File",
    ),
    "TextIO": TypeMapping(
        "str",
        {"type": "string", "description": "TextIO handle"},
        is_handle=True,
        handle_type_name="TextIO",
    ),
    "BinaryIO": TypeMapping(
        "str",
        {"type": "string", "description": "BinaryIO handle"},
        is_handle=True,
        handle_type_name="BinaryIO",
    ),
    "IO": TypeMapping(
        "str",
        {"type": "string", "description": "IO handle"},
        is_handle=True,
        handle_type_name="IO",
    ),
    # Path types
    "path": TypeMapping(str, {"type": "string", "description": "File system path"}),
    "Path": TypeMapping(str, {"type": "string", "description": "File system path"}),
    "PathLike": TypeMapping(str, {"type": "string", "description": "File system path"}),
}


@dataclass
class ParameterInfo:
    """Detailed parameter information for wrapper generation."""

    name: str
    type_str: str  # Type annotation string for code generation
    json_schema: dict[str, Any]
    has_default: bool = False
    default_value: Any = None
    default_repr: str = "None"  # String representation for code generation
    is_required: bool = True
    description: str | None = None
    is_handle_param: bool = False  # Parameter expects a handle string
    handle_type_name: str | None = None  # Expected handle type name


@dataclass
class FunctionSignature:
    """Parsed function signature information."""

    name: str
    parameters: list[ParameterInfo] = field(default_factory=list)
    return_type_str: str = "Any"
    return_schema: dict[str, Any] = field(default_factory=dict)
    return_is_handle: bool = False
    return_handle_type: str | None = None
    has_var_positional: bool = False  # Has *args
    has_var_keyword: bool = False  # Has **kwargs


class TypeMapper:
    """Maps docstring type strings to Python types and JSON schemas."""

    def __init__(self, additional_mappings: dict[str, TypeMapping] | None = None) -> None:
        """Initialize the type mapper.

        Args:
            additional_mappings: Additional type mappings to add
        """
        self._mappings = dict(TYPE_MAPPINGS)
        if additional_mappings:
            self._mappings.update(additional_mappings)

    def map_type_string(self, type_str: str) -> TypeMapping:
        """Map a docstring type string to a TypeMapping.

        Args:
            type_str: Type string from docstring (e.g., "str", "int", "Connection")

        Returns:
            TypeMapping with Python type and JSON schema
        """
        # Clean up the type string
        type_str = type_str.strip()

        # Direct lookup
        if type_str in self._mappings:
            return self._mappings[type_str]

        # Check for lowercase version
        if type_str.lower() in self._mappings:
            return self._mappings[type_str.lower()]

        # Handle Optional[X] or X | None patterns
        optional_match = re.match(r"Optional\[(.+)\]", type_str)
        if optional_match:
            inner_type = optional_match.group(1)
            inner_mapping = self.map_type_string(inner_type)
            return TypeMapping(
                python_type=f"{inner_mapping.python_type} | None"
                if isinstance(inner_mapping.python_type, str)
                else inner_mapping.python_type,
                json_schema={**inner_mapping.json_schema},
                is_handle=inner_mapping.is_handle,
                handle_type_name=inner_mapping.handle_type_name,
            )

        # Handle X | None pattern
        union_match = re.match(r"(.+)\s*\|\s*None", type_str)
        if union_match:
            inner_type = union_match.group(1)
            inner_mapping = self.map_type_string(inner_type)
            return TypeMapping(
                python_type=f"{inner_mapping.python_type} | None"
                if isinstance(inner_mapping.python_type, str)
                else inner_mapping.python_type,
                json_schema={**inner_mapping.json_schema},
                is_handle=inner_mapping.is_handle,
                handle_type_name=inner_mapping.handle_type_name,
            )

        # Handle general Union types like X | Y (e.g., DataFrame | Series)
        # If ANY component is a registered handle type, treat as handle
        if "|" in type_str:
            parts = [p.strip() for p in type_str.split("|")]
            for part in parts:
                # Check if this part is a registered handle type
                if part in self._mappings:
                    part_mapping = self._mappings[part]
                    if part_mapping.is_handle:
                        return TypeMapping(
                            python_type="str",
                            json_schema={"type": "string", "description": f"{part_mapping.handle_type_name} handle"},
                            is_handle=True,
                            handle_type_name=part_mapping.handle_type_name,
                        )
            # No handle types found in union, return Any
            return TypeMapping("Any", {})

        # Handle list[X] pattern
        list_match = re.match(r"list\[(.+)\]", type_str, re.IGNORECASE)
        if list_match:
            inner_type = list_match.group(1)
            inner_mapping = self.map_type_string(inner_type)
            return TypeMapping(
                python_type=list,
                json_schema={"type": "array", "items": inner_mapping.json_schema},
            )

        # Handle dict[K, V] pattern
        dict_match = re.match(r"dict\[(.+),\s*(.+)\]", type_str, re.IGNORECASE)
        if dict_match:
            value_type = dict_match.group(2)
            value_mapping = self.map_type_string(value_type)
            return TypeMapping(
                python_type=dict,
                json_schema={"type": "object", "additionalProperties": value_mapping.json_schema},
            )

        # Handle tuple[X, Y, ...] pattern
        tuple_match = re.match(r"tuple\[(.+)\]", type_str, re.IGNORECASE)
        if tuple_match:
            return TypeMapping(
                python_type=tuple,
                json_schema={"type": "array"},
            )

        # Unknown type - DO NOT automatically treat as handle type
        # Handle types must be explicitly registered (Connection, Cursor, etc.)
        # Unknown capitalized types (DataFrame, Series, Index, etc.) should be
        # treated as regular input parameters, not handles requiring lookup.
        # Fallback to Any for unknown types
        return TypeMapping("Any", {})

    def get_type_str_for_code(self, mapping: TypeMapping) -> str:
        """Get the type string for use in generated code.

        Args:
            mapping: TypeMapping to convert

        Returns:
            Type string suitable for Python code
        """
        if mapping.is_handle:
            return "str"

        if isinstance(mapping.python_type, str):
            return mapping.python_type

        if mapping.python_type is type(None):
            return "None"

        return mapping.python_type.__name__

    def add_handle_type(self, type_name: str, description: str | None = None) -> None:
        """Register a new handle type.

        Args:
            type_name: Name of the type (e.g., "Connection")
            description: Optional description for JSON schema
        """
        desc = description or f"{type_name} handle"
        mapping = TypeMapping(
            python_type="str",
            json_schema={"type": "string", "description": desc},
            is_handle=True,
            handle_type_name=type_name,
        )
        self._mappings[type_name] = mapping
        self._mappings[type_name.lower()] = mapping


def parse_default_value(default_str: str) -> tuple[Any, str]:
    """Parse a default value string into a Python value and code representation.

    Args:
        default_str: Default value string from docstring

    Returns:
        Tuple of (parsed value, code representation)
    """
    default_str = default_str.strip()

    # None
    if default_str.lower() == "none":
        return None, "None"

    # Boolean
    if default_str.lower() == "true":
        return True, "True"
    if default_str.lower() == "false":
        return False, "False"

    # String (quoted)
    if (default_str.startswith('"') and default_str.endswith('"')) or (
        default_str.startswith("'") and default_str.endswith("'")
    ):
        value = default_str[1:-1]
        return value, repr(value)

    # Integer
    try:
        value = int(default_str)
        return value, str(value)
    except ValueError:
        pass

    # Float
    try:
        value = float(default_str)
        # Handle special float values that can't be used without imports
        import math
        if math.isnan(value) or math.isinf(value):
            return None, "None"
        return value, str(value)
    except ValueError:
        pass

    # Empty collections
    if default_str == "[]":
        return [], "[]"
    if default_str == "{}":
        return {}, "{}"
    if default_str == "()":
        return (), "()"

    # List/Dict/Tuple literals - keep as string representation
    if default_str.startswith("[") or default_str.startswith("{") or default_str.startswith("("):
        return default_str, default_str

    # Sentinels and unparseable values - use None as a safe default
    # This handles things like <unrepresentable>, ConnectionType, etc.
    if default_str.startswith("<") or default_str[0].isupper():
        return None, "None"

    # Module-qualified names like sys.maxsize, math.inf, os.sep
    # These require imports we can't guarantee, so use None
    if "." in default_str:
        return None, "None"

    # Identifiers that aren't valid literals (e.g., variable names)
    # If it looks like an identifier but isn't a known literal, use None
    if default_str.isidentifier():
        return None, "None"

    # Unknown - use as-is (should rarely hit this)
    return default_str, default_str


def format_default_for_code(value: Any, type_str: str | None = None) -> str:
    """Format a default value for use in generated code.

    Args:
        value: The default value
        type_str: Optional type hint for context

    Returns:
        String representation for code
    """
    if value is None:
        return "None"

    if isinstance(value, bool):
        return "True" if value else "False"

    if isinstance(value, str):
        return repr(value)

    if isinstance(value, (int, float)):
        # Handle special float values that can't be used without imports
        if isinstance(value, float):
            import math
            if math.isnan(value) or math.isinf(value):
                return "None"
        return str(value)

    if isinstance(value, (list, dict, tuple)):
        return repr(value)

    # Fallback
    return repr(value)
