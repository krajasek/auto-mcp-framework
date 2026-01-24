# Examples

This directory contains examples demonstrating various auto-mcp features.

## Quick Start

### Simple Examples (serve directly)

```bash
# Math operations
auto-mcp-tool serve examples/simple_math/math_utils.py --name math-server

# Async weather API
auto-mcp-tool serve examples/async_api/weather_api.py --name weather-server

# Todo service with decorators
auto-mcp-tool serve examples/class_service/todo_service.py --name todo-server
```

### Manifest-Based Examples (pre-generated)

```bash
# SQLite database (already generated)
python examples/sqlite_database/server.py

# Pandas analytics (already generated, requires: pip install pandas)
python examples/pandas_analytics/server.py
```

## Examples Overview

| Example | Description | Approach |
|---------|-------------|----------|
| [simple_math](./simple_math/) | Basic math functions | Direct serve |
| [async_api](./async_api/) | Mock weather API | Direct serve |
| [class_service](./class_service/) | Todo list service | Decorators |
| [sqlite_database](./sqlite_database/) | SQLite operations | Manifest → Generate → Run |
| [pandas_analytics](./pandas_analytics/) | Pandas data analysis | Manifest → Generate → Run |

## Two Approaches

### 1. Direct Serve (Simple Modules)

For your own Python modules, serve them directly:

```bash
auto-mcp-tool serve mymodule.py --name my-server
```

Examples: `simple_math`, `async_api`, `class_service`

### 2. Manifest-Based (Large Packages)

For large packages like pandas or sqlite3, use manifests for selective exposure:

```bash
# Step 1: Create manifest.yaml
# Step 2: Generate
auto-mcp-tool generate pandas --manifest manifest.yaml -o server.py
# Step 3: Run
python server.py
```

Examples: `sqlite_database`, `pandas_analytics`

## Example Details

### simple_math
- **What**: Basic math functions (add, subtract, multiply, etc.)
- **Shows**: Simplest use case - plain functions with type hints

### async_api
- **What**: Mock weather API with async functions
- **Shows**: Async function handling, Literal types

### class_service
- **What**: Todo list service with decorated methods
- **Shows**: `@mcp_tool`, `@mcp_exclude` decorators

### sqlite_database
- **What**: SQLite database operations
- **Shows**: Manifest-based generation, handle-based storage

### pandas_analytics
- **What**: Pandas data analysis (97 tools)
- **Shows**: Selective exposure from large packages

## Claude Desktop Integration

Add to your config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "math": {
      "command": "auto-mcp-tool",
      "args": ["serve", "examples/simple_math/math_utils.py", "--no-llm"]
    },
    "sqlite": {
      "command": "python",
      "args": ["/full/path/to/examples/sqlite_database/server.py"]
    },
    "pandas": {
      "command": "python",
      "args": ["/full/path/to/examples/pandas_analytics/server.py"]
    }
  }
}
```

## Regenerating Manifest-Based Servers

If you modify a manifest, regenerate the server:

```bash
# SQLite
auto-mcp-tool generate sqlite3 --manifest examples/sqlite_database/manifest.yaml -o examples/sqlite_database/server.py

# Pandas
auto-mcp-tool generate pandas --manifest examples/pandas_analytics/manifest.yaml -o examples/pandas_analytics/server.py
```
