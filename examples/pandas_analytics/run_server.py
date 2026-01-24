#!/usr/bin/env python3
"""Run the Pandas MCP server.

This runs the pre-generated Pandas MCP server that was created from the manifest.

Usage:
    python run_server.py

The server was generated with:
    auto-mcp-tool generate pandas --manifest manifest.yaml -o server.py

Note: Requires pandas to be installed: pip install pandas
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Run the Pandas MCP server."""
    server_path = Path(__file__).parent / "server.py"

    if not server_path.exists():
        print(f"Error: Server file not found at {server_path}")
        print("\nTo generate it, run from the project root:")
        print("  auto-mcp-tool generate pandas --manifest examples/pandas_analytics/manifest.yaml -o examples/pandas_analytics/server.py")
        sys.exit(1)

    # Check if pandas is installed
    try:
        import pandas  # noqa: F401
    except ImportError:
        print("Error: pandas is not installed.")
        print("Install it with: pip install pandas")
        sys.exit(1)

    print("Starting Pandas MCP server...")
    print("Use Ctrl+C to stop the server")
    print("-" * 50)

    subprocess.run([sys.executable, str(server_path)], check=True)


if __name__ == "__main__":
    main()
