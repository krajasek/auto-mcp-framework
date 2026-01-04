#!/usr/bin/env python3
"""Run the pandas MCP server.

This script runs the pre-generated pandas MCP server.
The server exposes 530 pandas functions as MCP tools.

Usage:
    python run_server.py

Or run the generated server directly:
    python pandas_server.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Run the pandas server."""
    server_path = Path(__file__).parent / "pandas_server.py"

    if not server_path.exists():
        print("Server file not found. Generating...")
        # Generate the server
        subprocess.run([
            sys.executable, "-m", "auto_mcp",
            "package", "generate", "pandas",
            "-o", str(server_path),
            "--no-llm",
            "--max-depth", "0",
            "--include-reexports",
        ], check=True)
        print(f"Generated server at: {server_path}")

    print(f"Running pandas MCP server from: {server_path}")
    print("Press Ctrl+C to stop the server")
    print("-" * 50)

    # Run the server
    subprocess.run([sys.executable, str(server_path)], check=True)


if __name__ == "__main__":
    main()
