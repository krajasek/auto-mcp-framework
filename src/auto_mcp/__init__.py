"""auto-mcp: Automatically generate MCP servers from Python modules."""

from auto_mcp.api import AutoMCP, quick_server, quick_server_from_package
from auto_mcp.config import Settings, get_settings
from auto_mcp.core.generator import GeneratorConfig, MCPGenerator
from auto_mcp.core.package import (
    PackageAnalyzer,
    PackageMetadata,
    analyze_installed_package,
)
from auto_mcp.decorators import mcp_exclude, mcp_prompt, mcp_resource, mcp_tool
from auto_mcp.session import (
    SessionConfig,
    SessionContext,
    SessionData,
    SessionManager,
    mcp_session_cleanup,
    mcp_session_init,
)

__all__ = [
    # High-level API
    "AutoMCP",
    "quick_server",
    "quick_server_from_package",
    # Package analysis
    "PackageAnalyzer",
    "PackageMetadata",
    "analyze_installed_package",
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
    # Session lifecycle
    "SessionContext",
    "SessionData",
    "SessionManager",
    "SessionConfig",
    "mcp_session_init",
    "mcp_session_cleanup",
]

__version__ = "0.1.0"
