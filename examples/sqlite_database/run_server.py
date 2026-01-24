#!/usr/bin/env python3
"""Run the SQLite MCP server.

This runs the pre-generated SQLite MCP server that was created from the manifest.

Usage:
    python run_server.py

The server was generated with:
    auto-mcp-tool generate sqlite3 --manifest manifest.yaml -o server.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Run the SQLite MCP server."""
    server_path = Path(__file__).parent / "server.py"

    if not server_path.exists():
        print(f"Error: Server file not found at {server_path}")
        print("\nTo generate it, run from the project root:")
        print("  auto-mcp-tool generate sqlite3 --manifest examples/sqlite_database/manifest.yaml -o examples/sqlite_database/server.py")
        sys.exit(1)

    print("Starting SQLite MCP server...")
    print("Use Ctrl+C to stop the server")
    print("-" * 50)

    subprocess.run([sys.executable, str(server_path)], check=True)


if __name__ == "__main__":
    main()
