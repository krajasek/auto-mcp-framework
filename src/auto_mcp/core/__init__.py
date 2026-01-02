"""Core modules for MCP generation."""

from auto_mcp.core.analyzer import MethodMetadata, ModuleAnalyzer
from auto_mcp.core.generator import (
    GeneratedPrompt,
    GeneratedResource,
    GeneratedTool,
    GeneratorConfig,
    MCPGenerator,
)
from auto_mcp.core.package import (
    ModuleInfo,
    PackageAnalyzer,
    PackageMetadata,
    analyze_installed_package,
)

__all__ = [
    "GeneratedPrompt",
    "GeneratedResource",
    "GeneratedTool",
    "GeneratorConfig",
    "MCPGenerator",
    "MethodMetadata",
    "ModuleAnalyzer",
    "ModuleInfo",
    "PackageAnalyzer",
    "PackageMetadata",
    "analyze_installed_package",
]
