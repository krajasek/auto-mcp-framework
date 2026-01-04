#!/usr/bin/env python3
"""Run the SQLite MCP server.

This script runs the SQLite MCP server which provides 18 tools
for database management, CRUD operations, and queries.

Usage:
    python run_server.py

Or run the generated server directly:
    python sqlite_server.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Run the SQLite server."""
    server_path = Path(__file__).parent / "sqlite_server.py"

    if not server_path.exists():
        print("Server file not found. Generating...")
        tools_path = Path(__file__).parent / "sqlite_tools.py"
        subprocess.run([
            sys.executable, "-m", "auto_mcp",
            "generate", str(tools_path),
            "-o", str(server_path),
            "--no-llm",
            "--name", "sqlite-tools",
        ], check=True)
        print(f"Generated server at: {server_path}")

    print(f"Running SQLite MCP server from: {server_path}")
    print("Available tools: 18 database operations")
    print("Press Ctrl+C to stop the server")
    print("-" * 50)

    # Run the server
    subprocess.run([sys.executable, str(server_path)], check=True)


if __name__ == "__main__":
    main()
