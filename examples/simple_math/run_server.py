#!/usr/bin/env python3
"""Run the simple_math MCP server.

This script demonstrates how to use auto-mcp to create and run
an MCP server from the math_utils module.

Usage:
    python run_server.py

Or with auto-mcp CLI (recommended):
    auto-mcp-tool serve examples/simple_math/math_utils.py --name math-server
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the src directory to the path for development
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from auto_mcp import AutoMCP, quick_server  # noqa: E402

# Import the module to expose
from examples.simple_math import math_utils  # noqa: E402


def main() -> None:
    """Run the MCP server."""
    # Option 1: Quick one-liner (simplest)
    # server = quick_server(math_utils, name="math-server")
    # server.run()

    # Option 2: With more control using AutoMCP
    auto = AutoMCP(
        use_llm=False,  # Set to True and configure LLM for better descriptions
    )

    server = auto.create_server([math_utils], name="math-server")

    print("Starting math-server MCP server...")
    print("Available tools: add, subtract, multiply, divide, power, factorial, is_prime, gcd")
    print("\nUse Ctrl+C to stop the server.")
    server.run()


if __name__ == "__main__":
    main()
