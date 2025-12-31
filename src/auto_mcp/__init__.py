"""auto-mcp: Automatically generate MCP servers from Python modules."""

from auto_mcp.api import AutoMCP, quick_server
from auto_mcp.config import Settings, get_settings
from auto_mcp.core.generator import GeneratorConfig, MCPGenerator
from auto_mcp.decorators import mcp_exclude, mcp_prompt, mcp_resource, mcp_tool

__all__ = [
    # High-level API
    "AutoMCP",
    "quick_server",
    # Config
    "Settings",
    "get_settings",
    # Generator (lower-level)
    "GeneratorConfig",
    "MCPGenerator",
    # Decorators
    "mcp_tool",
    "mcp_exclude",
    "mcp_resource",
    "mcp_prompt",
]

__version__ = "0.1.0"
