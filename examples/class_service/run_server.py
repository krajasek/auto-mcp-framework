#!/usr/bin/env python3
"""Run the todo service MCP server.

This script demonstrates how auto-mcp handles class-based services
with decorated methods.

Usage:
    python run_server.py

Or with auto-mcp CLI:
    auto-mcp serve examples/class_service/todo_service.py
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
        use_llm=False,
        server_name="todo-service",
    )

    server = auto.create_server([todo_service])

    print("Starting todo-service MCP server...")
    print("Available tools:")
    print("  - create_todo: Create a new todo item")
    print("  - get_todo: Get a todo by ID")
    print("  - list_todos: List all todos with filtering")
    print("  - update_todo_status: Update todo status")
    print("  - delete_todo: Delete a todo")
    print("  - search_todos: Search todos by text")
    print("  - get_stats: Get todo statistics")
    server.run()


if __name__ == "__main__":
    main()
