#!/usr/bin/env python3
"""Run the async weather API MCP server.

This script demonstrates how auto-mcp handles async functions.

Usage:
    python run_server.py

Or with auto-mcp CLI:
    auto-mcp serve examples/async_api/weather_api.py
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
        use_llm=False,
        server_name="weather-api-server",
    )

    server = auto.create_server([weather_api])

    print("Starting weather-api-server MCP server...")
    print("Available tools:")
    print("  - get_current_weather: Get current weather for a city")
    print("  - get_forecast: Get multi-day forecast")
    print("  - get_temperature: Get just the temperature")
    print("  - compare_weather: Compare weather between two cities")
    print("  - search_cities: Search for cities by name")
    server.run()


if __name__ == "__main__":
    main()
