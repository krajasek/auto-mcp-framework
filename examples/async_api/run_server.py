#!/usr/bin/env python3
"""Run the async weather API MCP server.

This script demonstrates how auto-mcp handles async functions.

Usage:
    python run_server.py

Or with auto-mcp CLI (recommended):
    auto-mcp-tool serve examples/async_api/weather_api.py --name weather-server
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the src directory to the path for development
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from auto_mcp import AutoMCP  # noqa: E402

# Import the module to expose
from examples.async_api import weather_api  # noqa: E402


def main() -> None:
    """Run the MCP server."""
    auto = AutoMCP(
        use_llm=False,  # Set to True and configure LLM for better descriptions
    )

    server = auto.create_server([weather_api], name="weather-server")

    print("Starting weather-server MCP server...")
    print("Available tools: get_current_weather, get_forecast, get_temperature, compare_weather, search_cities")
    print("\nNote: This uses simulated weather data for demonstration.")
    print("Use Ctrl+C to stop the server.")
    server.run()


if __name__ == "__main__":
    main()
