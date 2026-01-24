"""Manifest-based MCP server generation.

This module provides selective tool exposure via YAML manifests,
allowing users to specify exactly which functions/methods to expose
as MCP tools.
"""

from auto_mcp.manifest.dependencies import DependencyAnalyzer, analyze_and_include_dependencies
from auto_mcp.manifest.generator import ManifestGenerator, generate_from_manifest
from auto_mcp.manifest.resolver import PatternResolver, ResolvedTool, resolve_all_patterns
from auto_mcp.manifest.schema import Manifest, ToolEntry

__all__ = [
    "Manifest",
    "ToolEntry",
    "ManifestGenerator",
    "generate_from_manifest",
    "PatternResolver",
    "ResolvedTool",
    "resolve_all_patterns",
    "DependencyAnalyzer",
    "analyze_and_include_dependencies",
]
