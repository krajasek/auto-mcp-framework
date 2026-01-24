"""Wrapper generator for C extension modules.

This package provides tools to generate Python wrappers for C extension
modules, making them introspectable for MCP server generation.
"""

from auto_mcp.wrapper.generator import (
    CallableInfo,
    ClassInfo,
    WrapperGenerator,
    generate_wrapper_for_module,
)
from auto_mcp.wrapper.type_mapper import (
    FunctionSignature,
    ParameterInfo,
    TypeMapper,
    TypeMapping,
)

__all__ = [
    # Generator
    "WrapperGenerator",
    "generate_wrapper_for_module",
    "CallableInfo",
    "ClassInfo",
    # Type mapping
    "TypeMapper",
    "TypeMapping",
    "ParameterInfo",
    "FunctionSignature",
]
