# Async API Example

Demonstrates how auto-mcp handles async functions with a mock weather API.

## Files

- `weather_api.py` - Async weather API functions (simulated)
- `run_server.py` - Script to run the MCP server programmatically

## Usage

### Option 1: CLI (Recommended)

```bash
# Generate a standalone server file
auto-mcp-tool generate examples/async_api/weather_api.py -o weather_server.py --no-llm

# Run the server
python weather_server.py

# Or serve directly without generating a file
auto-mcp-tool serve examples/async_api/weather_api.py --name weather-server
```

### Option 2: Python API

```bash
python examples/async_api/run_server.py
```

### Option 3: Claude Desktop Integration

Add to your Claude Desktop config:

```json
{
  "mcpServers": {
    "weather-server": {
      "command": "auto-mcp-tool",
      "args": ["serve", "examples/async_api/weather_api.py", "--no-llm"]
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `get_current_weather` | Get the current weather for a city |
| `get_forecast` | Get a weather forecast for the coming days (1-7) |
| `get_temperature` | Get just the current temperature (celsius or fahrenheit) |
| `compare_weather` | Compare current weather between two cities |
| `search_cities` | Search for cities by name |

## Key Features Demonstrated

- **Async Functions**: All API functions are async and auto-mcp handles them correctly
- **Type Hints**: Uses `Literal` types for constrained parameters
- **Dataclasses**: Returns structured data
- **Concurrent Calls**: `compare_weather` uses `asyncio.gather` internally

## Example Interactions

```
User: What's the weather in Tokyo?
Assistant: [calls get_current_weather("Tokyo", "JP")]
-> Temperature: 22.5C, Conditions: Partly Cloudy, Humidity: 65%

User: Compare the weather in New York and London
Assistant: [calls compare_weather("New York", "London")]
-> New York: 18.3C, London: 12.1C, Difference: 6.2C, Warmer: New York

User: Give me a 3-day forecast for Paris
Assistant: [calls get_forecast("Paris", 3, "FR")]
-> Day 1: High 24C, Low 15C, Sunny
-> Day 2: High 22C, Low 14C, Partly Cloudy
-> Day 3: High 20C, Low 13C, Rainy
```
