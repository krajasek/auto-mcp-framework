#!/usr/bin/env python3
"""Run the todo service MCP server.

This script demonstrates how auto-mcp handles class-based services
with decorated methods (@mcp_tool, @mcp_exclude).

Usage:
    python run_server.py

Or with auto-mcp CLI (recommended):
    auto-mcp-tool serve examples/class_service/todo_service.py --name todo-server
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the src directory to the path for development
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from auto_mcp import AutoMCP  # noqa: E402

# Import the module to expose
from examples.class_service import todo_service  # noqa: E402


def main() -> None:
    """Run the MCP server."""
    auto = AutoMCP(
        use_llm=False,  # Set to True and configure LLM for better descriptions
    )

    server = auto.create_server([todo_service], name="todo-server")

    print("Starting todo-server MCP server...")
    print("Available tools: create_todo, get_todo, list_todos, update_todo_status, delete_todo, search_todos, get_stats")
    print("\nNote: State is maintained in memory during the session.")
    print("Use Ctrl+C to stop the server.")
    server.run()


if __name__ == "__main__":
    main()
