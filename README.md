# auto-mcp

[![PyPI version](https://badge.fury.io/py/auto-mcp.svg)](https://pypi.org/project/auto-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/auto-mcp.svg)](https://pypi.org/project/auto-mcp/)
[![License](https://img.shields.io/pypi/l/auto-mcp.svg)](https://github.com/krajasek/auto-mcp-framework/blob/main/LICENSE)

Automatically generate MCP (Model Context Protocol) servers from Python modules using LLM-powered documentation.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [MCP Transports](#mcp-transports)
- [Package Analysis](#package-analysis)
- [Type Serialization System](#type-serialization-system)
- [CLI Reference](#cli-reference)
- [Python API Reference](#python-api-reference)
- [Decorators](#decorators)
- [Session Lifecycle](#session-lifecycle)
- [LLM Providers](#llm-providers)
- [Configuration](#configuration)
- [Hot Reload](#hot-reload)
- [Examples](#examples)
  - [Simple Math](#simple-math-examplessimple_math)
  - [Async API](#async-api-examplesasync_api)
  - [Class Service](#class-service-examplesclass_service)
  - [Pandas Analytics](#pandas-analytics-examplespandas_analytics)
  - [SQLite Database](#sqlite-database-examplessqlite_database)
- [Pandas MCP Server Setup Guide](#pandas-mcp-server-setup-guide)
- [SQLite MCP Server Setup Guide](#sqlite-mcp-server-setup-guide)
- [Integration with Claude Desktop](#integration-with-claude-desktop)
- [Development](#development)
- [License](#license)

---

## Features

- **Automatic Tool Generation**: Exposes public functions as MCP tools
- **Package Analysis**: Recursively analyze installed packages (requests, pandas, etc.)
- **LLM-Powered Descriptions**: Uses local (Ollama) or cloud (OpenAI, Anthropic) LLMs to generate tool descriptions
- **Multiple Output Formats**: Standalone file, Python package, or in-memory server
- **Multiple Transports**: stdio, SSE, and Streamable HTTP with stateless/stateful modes
- **Type Serialization**: Handle complex Python types (datetime, Path, UUID, pandas DataFrames, etc.)
- **Compression Support**: Automatic compression for large data with gzip, zlib, or lz4
- **Object Store**: Server-side handle-based storage for stateful objects (sessions, connections)
- **Decorator Support**: Fine-grained control with `@mcp_tool`, `@mcp_exclude`, `@mcp_resource`, `@mcp_prompt`
- **Session Lifecycle**: Explicit session management with `create_session`/`close_session` tools and automatic `SessionContext` injection
- **Async Support**: Full support for async functions
- **Hot Reload**: Watch for file changes during development
- **Caching**: File-based caching to avoid redundant LLM calls
- **Type Safety**: Full type hints and mypy strict mode

## Installation

```bash
# Using uv (recommended)
uv add auto-mcp

# Using pip
pip install auto-mcp
```

## Quick Start

### 1. Create a Python module with functions to expose

```python
# math_utils.py
def add(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b

def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b

def _private_helper():
    """This won't be exposed (starts with underscore)."""
    pass
```

### 2. Generate and run an MCP server

**Using the CLI:**
```bash
# Generate a standalone server file
auto-mcp generate math_utils.py -o server.py

# Or serve directly
auto-mcp serve math_utils.py
```

**Using the Python API:**
```python
from auto_mcp import AutoMCP
import math_utils

auto = AutoMCP(use_llm=False)
server = auto.create_server([math_utils])
server.run()
```

### 3. Or generate from an installed package

```bash
# Check what would be exposed from the requests package
auto-mcp package check requests

# Generate a server from the json stdlib package
auto-mcp package generate json -o json_server.py --no-llm

# Serve directly
auto-mcp package serve json --no-llm

# For packages like pandas/numpy that re-export from submodules:
auto-mcp package generate pandas -o pandas_server.py --no-llm --include-reexports
```

---

## MCP Transports

auto-mcp supports multiple transport protocols for MCP communication.

### stdio (Default)

Standard input/output transport. Used by Claude Desktop and most MCP clients.

**CLI:**
```bash
# Explicit (default)
auto-mcp serve mymodule.py --transport stdio

# Implicit (stdio is default)
auto-mcp serve mymodule.py
```

**Python API:**
```python
server = auto.create_server([mymodule])
server.run()  # stdio by default
server.run(transport="stdio")  # explicit
```

**Claude Desktop configuration:**
```json
{
  "mcpServers": {
    "my-tools": {
      "command": "auto-mcp",
      "args": ["serve", "mymodule.py", "--no-llm"]
    }
  }
}
```

### SSE (Server-Sent Events)

HTTP-based transport using Server-Sent Events. Useful for web clients.

**CLI:**
```bash
# Basic SSE server
auto-mcp serve mymodule.py --transport sse

# Custom host and port
auto-mcp serve mymodule.py --transport sse --host 127.0.0.1 --port 3000
```

**Python API:**
```python
server = auto.create_server([mymodule])
server.run(transport="sse")
```

**Client connection:**
```bash
# The SSE endpoint will be available at:
# http://localhost:8080/sse
```

### Streamable HTTP

Modern HTTP transport with streaming support. Supports both stateless and stateful modes.

**CLI:**
```bash
# Streamable HTTP (stateless by default)
auto-mcp serve mymodule.py --transport streamable-http

# With custom settings
auto-mcp serve mymodule.py --transport streamable-http --port 8080
```

**Python API:**
```python
server = auto.create_server([mymodule])
server.run(transport="streamable-http")
```

### Stateless vs Stateful HTTP

MCP HTTP transports can operate in two modes:

#### Stateless Mode (Default)

Each request is independent. No session state is maintained between requests.

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(name="my-server", stateless_http=True)  # Default

# Or via auto-mcp
server = auto.create_server([mymodule])
server.run(transport="streamable-http")  # Stateless by default
```

**Characteristics:**
- Each request is independent
- No session management overhead
- Scales horizontally easily
- Best for simple, stateless tools

#### Stateful Mode

Maintains session state across requests. Useful for tools that need context.

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(name="my-server", stateless_http=False)

# For more control, use the underlying server directly
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(name="stateful-server")

@mcp.tool()
def increment_counter() -> int:
    """Increment and return the session counter."""
    # State is maintained per session
    if not hasattr(increment_counter, '_count'):
        increment_counter._count = 0
    increment_counter._count += 1
    return increment_counter._count
```

**Characteristics:**
- Session state persists across requests
- Requires session management
- Better for conversational or contextual tools
- Higher memory usage per session

### Transport Comparison

| Transport | Protocol | Streaming | Use Case |
|-----------|----------|-----------|----------|
| `stdio` | stdin/stdout | Yes | CLI tools, Claude Desktop |
| `sse` | HTTP + SSE | Yes | Web clients, browsers |
| `streamable-http` | HTTP | Yes | Modern HTTP clients, APIs |

### Environment Variables for Transports

```bash
# Default transport
AUTO_MCP_TRANSPORT=stdio

# HTTP settings (for sse and streamable-http)
AUTO_MCP_HOST=0.0.0.0
AUTO_MCP_PORT=8080
```

---

## Package Analysis

Generate MCP servers from installed Python packages without writing any code.

### CLI Commands

#### Check a Package

Preview what would be exposed without generating anything:

```bash
# Basic check
auto-mcp package check requests

# With verbose output (shows module tree)
auto-mcp package check requests -v

# Check only public API (__all__ exports)
auto-mcp package check requests --public-api-only

# Limit recursion depth
auto-mcp package check boto3 --max-depth 2

# Filter modules with patterns
auto-mcp package check requests --include 'requests.api.*' --exclude 'requests.compat.*'
```

#### Generate from a Package

```bash
# Generate server file
auto-mcp package generate json -o json_server.py --no-llm

# With LLM descriptions
auto-mcp package generate requests -o requests_server.py --llm-provider ollama

# Only public API
auto-mcp package generate pandas -o pandas_server.py --public-api-only

# With filtering
auto-mcp package generate boto3 -o s3_tools.py \
    --include 'boto3.s3.*' \
    --max-depth 2 \
    --no-llm
```

#### Serve a Package Directly

```bash
# Serve with stdio transport (for Claude Desktop)
auto-mcp package serve json --no-llm

# Serve with SSE transport
auto-mcp package serve requests --transport sse --port 3000

# Serve with streamable HTTP
auto-mcp package serve json --transport streamable-http

# With options
auto-mcp package serve requests \
    --name "HTTP Tools" \
    --public-api-only \
    --no-llm
```

### Python API

```python
from auto_mcp import AutoMCP, quick_server_from_package

# Quick one-liner
server = quick_server_from_package("json", name="JSON Tools")
server.run()

# With more control
auto = AutoMCP(
    use_llm=False,
    public_api_only=True,
    max_depth=2,
    include_patterns=["requests.api.*"],
    exclude_patterns=["requests.compat.*"],
)

# Analyze a package
metadata = auto.analyze_package("requests")
print(f"Found {metadata.module_count} modules")
print(f"Found {metadata.method_count} methods")

# Create server from package
server = auto.create_server_from_package("requests")
server.run()

# Generate file from package
auto.generate_file_from_package("json", "json_server.py")

# For packages with re-exported functions (pandas, numpy, etc.)
auto = AutoMCP(
    use_llm=False,
    include_reexports=True,  # Include functions from submodules
    max_depth=0,
)
server = auto.create_server_from_package("pandas")
```

### Package Analysis Options

| Option | Description |
|--------|-------------|
| `--max-depth` | Maximum recursion depth for submodule discovery |
| `--public-api-only` | Only expose functions in `__all__` |
| `--include-private` | Include private modules (starting with `_`) |
| `--include PATTERN` | Glob patterns for modules to include |
| `--exclude PATTERN` | Glob patterns for modules to exclude |
| `--include-reexports` | Include functions re-exported in `__all__` from submodules |

### Re-exported Functions

Many large packages like `pandas`, `numpy`, and `requests` define functions in submodules but re-export them at the package level via `__all__`. By default, these re-exported functions are not discovered because their `__module__` attribute points to the original submodule.

Use `--include-reexports` to include these functions:

```bash
# Without --include-reexports: 0 tools found (pandas uses re-exports)
auto-mcp package check pandas --max-depth 0

# With --include-reexports: 530+ tools found
auto-mcp package check pandas --max-depth 0 --include-reexports

# Generate pandas server with all re-exported functions
auto-mcp package generate pandas -o pandas_server.py --no-llm --include-reexports
```

**Common packages that need `--include-reexports`:**
- `pandas` - DataFrame operations, I/O functions (read_csv, concat, merge, etc.)
- `numpy` - Array operations, mathematical functions
- `requests` - HTTP functions (get, post, put, etc.)
- `scipy` - Scientific computing functions

### Example: Creating a JSON Tools Server

```bash
# 1. Check what's available
auto-mcp package check json -v

# Output:
# Package: json
# Modules discovered: 3
#
# Tools (4)
# ┏━━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━┓
# ┃ Name   ┃ Module ┃ Async ┃ Parameters     ┃
# ┡━━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━┩
# │ dump   │ json   │       │ obj, fp, ...   │
# │ dumps  │ json   │       │ obj, ...       │
# │ load   │ json   │       │ fp, ...        │
# │ loads  │ json   │       │ s, ...         │
# └────────┴────────┴───────┴────────────────┘

# 2. Generate and run
auto-mcp package serve json --no-llm

# 3. Or for Claude Desktop, add to config:
```

```json
{
  "mcpServers": {
    "json-tools": {
      "command": "auto-mcp",
      "args": ["package", "serve", "json", "--no-llm"]
    }
  }
}
```

---

## Type Serialization System

auto-mcp includes a powerful type serialization system for handling complex Python types in MCP contexts. This enables tools to accept and return types like `datetime`, `Path`, `UUID`, pandas DataFrames, and more.

### Quick Start

```python
from auto_mcp.types import TypeRegistry, register_stdlib_adapters

# Create a registry with standard library adapters
registry = TypeRegistry()
register_stdlib_adapters(registry)

# Now datetime, Path, UUID, etc. are automatically serialized
from datetime import datetime

# Serialize a datetime to JSON-compatible format
serialized = registry.serialize(datetime.now())
print(serialized)  # "2024-01-15T10:30:00"

# Deserialize back to datetime
dt = registry.deserialize("2024-01-15T10:30:00", datetime)
print(dt)  # datetime(2024, 1, 15, 10, 30, 0)
```

### Built-in Type Adapters

The following types are supported out of the box:

| Type | Serialized Format | Example |
|------|-------------------|---------|
| `datetime` | ISO 8601 string | `"2024-01-15T10:30:00"` |
| `date` | ISO 8601 string | `"2024-01-15"` |
| `time` | ISO 8601 string | `"10:30:00"` |
| `timedelta` | Total seconds (float) | `3600.5` |
| `Path` | String path | `"/home/user/file.txt"` |
| `UUID` | String UUID | `"550e8400-e29b-41d4-a716-446655440000"` |
| `Decimal` | String number | `"123.456"` |
| `bytes` | Base64 string | `"SGVsbG8gV29ybGQ="` |
| `set` | Sorted list | `[1, 2, 3]` |
| `frozenset` | Sorted list | `[1, 2, 3]` |
| `complex` | Dict with real/imag | `{"real": 3.0, "imag": 4.0}` |

**Optional adapters** (require additional packages):

| Type | Package | Serialized Format |
|------|---------|-------------------|
| `pandas.DataFrame` | pandas | Dict with columns, data, shape |
| `PIL.Image` | pillow | Base64 PNG with metadata |
| `numpy.ndarray` | numpy | Dict with data, shape, dtype |

### Using Type Adapters

#### Register Standard Library Adapters

```python
from auto_mcp.types import TypeRegistry, register_stdlib_adapters

registry = TypeRegistry()
register_stdlib_adapters(registry)
```

#### Register All Available Adapters

```python
from auto_mcp.types import TypeRegistry, register_all_adapters

registry = TypeRegistry()
register_all_adapters(registry)  # Includes pandas, PIL, numpy if installed
```

#### Create Custom Adapters

```python
from auto_mcp.types import TypeAdapter, FunctionAdapter
from dataclasses import dataclass

# Option 1: Using FunctionAdapter (simple)
@dataclass
class Point:
    x: float
    y: float

point_adapter = FunctionAdapter(
    target_type=Point,
    serializer=lambda p: {"x": p.x, "y": p.y},
    deserializer=lambda d: Point(d["x"], d["y"]),
    schema={"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}}},
)

registry.register_adapter(point_adapter)

# Option 2: Using TypeAdapter class (more control)
class PointAdapter(TypeAdapter[Point]):
    target_type = Point

    def serialize(self, obj: Point) -> dict:
        return {"x": obj.x, "y": obj.y}

    def deserialize(self, data: dict) -> Point:
        return Point(data["x"], data["y"])

    def json_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
            },
            "required": ["x", "y"],
        }

registry.register_adapter(PointAdapter())
```

#### Quick Registration

```python
from datetime import datetime

registry.register(
    datetime,
    serialize=lambda dt: dt.isoformat(),
    deserialize=lambda s: datetime.fromisoformat(s),
    schema={"type": "string", "format": "date-time"},
)
```

### Function Wrappers

Automatically transform function inputs and outputs:

```python
from auto_mcp.types import FunctionWrapper, TypeRegistry, register_stdlib_adapters
from datetime import datetime
from pathlib import Path

registry = TypeRegistry()
register_stdlib_adapters(registry)

def process_file(path: Path, modified_after: datetime) -> dict:
    """Process a file if modified after the given time."""
    stat = path.stat()
    return {
        "path": str(path),
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }

# Wrap the function for automatic type conversion
wrapper = FunctionWrapper(process_file, registry=registry)

# Call with JSON-compatible inputs - types are auto-converted
result = wrapper.call({
    "path": "/etc/hosts",
    "modified_after": "2024-01-01T00:00:00"
})
# path is converted from string to Path
# modified_after is converted from string to datetime
```

### Object Store

For stateful objects that can't be serialized (database connections, sessions, etc.), use the Object Store:

```python
from auto_mcp.types import ObjectStore, TypeRegistry

# Create store and registry
store = ObjectStore()
registry = TypeRegistry()

# Register a type for server-side storage
class DatabaseSession:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.connected = True

    def query(self, sql: str) -> list:
        return [{"id": 1, "name": "Example"}]

registry.register_stored_type(
    DatabaseSession,
    ttl=3600,  # Auto-expire after 1 hour
    max_instances=10,  # Limit concurrent sessions
)

# Store an object and get a handle
session = DatabaseSession("postgresql://localhost/mydb")
handle = store.store(session, ttl=3600)
print(handle)  # "obj_a1b2c3d4..."

# Retrieve by handle
retrieved = store.get(handle)
result = retrieved.query("SELECT * FROM users")

# Clean up
store.remove(handle)
```

#### Object Store with Function Wrapper

```python
from auto_mcp.types import FunctionWrapper, ObjectStore, TypeRegistry

registry = TypeRegistry()
store = ObjectStore()

class Session:
    pass

registry.register_stored_type(Session, ttl=3600)

def create_session() -> Session:
    """Create a new session."""
    return Session()

def use_session(session: Session) -> str:
    """Use an existing session."""
    return f"Using session: {session}"

# Wrap functions
create_wrapper = FunctionWrapper(create_session, registry=registry, store=store)
use_wrapper = FunctionWrapper(use_session, registry=registry, store=store)

# create_session returns a handle string
handle = create_wrapper.call({})
print(handle)  # "obj_..."

# use_session accepts the handle and retrieves the object
result = use_wrapper.call({"session": handle})
```

### Compression

For large data, auto-mcp supports automatic compression:

```python
from auto_mcp.types import (
    CompressedAdapter,
    CompressionConfig,
    CompressionAlgorithm,
    with_compression,
    DateTimeAdapter,
)

# Method 1: Wrap any adapter with compression
adapter = DateTimeAdapter()
compressed = with_compression(
    adapter,
    threshold=1024,  # Only compress if > 1KB
    algorithm=CompressionAlgorithm.GZIP,
    level=6,
)

# Method 2: Using CompressedAdapter directly
config = CompressionConfig(
    enabled=True,
    algorithm=CompressionAlgorithm.GZIP,
    threshold=1024,  # Minimum size to trigger compression
    level=6,  # Compression level (1-9)
)
compressed = CompressedAdapter(adapter, config)

# Serialized data includes compression metadata
result = compressed.serialize(datetime.now())
# {
#     "compressed": True,
#     "algorithm": "gzip",
#     "original_size": 2048,
#     "compressed_size": 512,
#     "compression_ratio": 0.25,
#     "data": "H4sIAAAAAAAA..."
# }
```

#### Compression Algorithms

| Algorithm | Description | Use Case |
|-----------|-------------|----------|
| `GZIP` | Standard gzip (default) | General purpose, good compression |
| `ZLIB` | zlib compression | Slightly faster than gzip |
| `LZ4` | Very fast compression | When speed is critical (requires `lz4` package) |
| `NONE` | No compression | Disabled |

#### Auto-Compress Registry

Automatically apply compression to types that typically produce large output:

```python
from auto_mcp.types import AutoCompressRegistry, CompressionConfig

# Create auto-compress registry
config = CompressionConfig(threshold=10240)  # 10KB threshold
auto_compress = AutoCompressRegistry(config)

# Register types known to produce large output
auto_compress.register_large_type(pandas.DataFrame)
auto_compress.register_large_type(numpy.ndarray)

# Wrap adapters
df_adapter = create_pandas_dataframe_adapter()
compressed_adapter = auto_compress.wrap_adapter(df_adapter)
```

### Integration with MCP Generator

The type system integrates automatically with the MCP generator:

```python
from auto_mcp import AutoMCP
from auto_mcp.types import TypeRegistry, register_stdlib_adapters

# Create registry with adapters
registry = TypeRegistry()
register_stdlib_adapters(registry)

# Pass to AutoMCP
auto = AutoMCP(
    use_llm=False,
    type_registry=registry,  # Use custom registry
    enable_type_transforms=True,  # Enable automatic transforms
)

# Now your tools can use complex types
server = auto.create_server([mymodule])
```

### Class Wrapper

Wrap entire classes for MCP exposure:

```python
from auto_mcp.types import ClassWrapper, TypeRegistry, register_stdlib_adapters
from datetime import datetime

registry = TypeRegistry()
register_stdlib_adapters(registry)

class DateService:
    def parse_date(self, date_str: str) -> datetime:
        """Parse a date string."""
        return datetime.fromisoformat(date_str)

    def format_date(self, dt: datetime, fmt: str = "%Y-%m-%d") -> str:
        """Format a datetime."""
        return dt.strftime(fmt)

    def _private_method(self):
        """Not exposed."""
        pass

# Wrap the class
wrapper = ClassWrapper(DateService, registry=registry)

# Get available methods (excludes private)
print(wrapper.get_method_names())  # ['parse_date', 'format_date']

# Create instance and call methods
instance = wrapper.create()
result = wrapper.call_method(instance, "format_date", {
    "dt": "2024-01-15T10:30:00",
    "fmt": "%B %d, %Y"
})
print(result)  # "January 15, 2024"
```

### Type Strategies

The registry uses different strategies based on the type:

| Strategy | Description | Example Types |
|----------|-------------|---------------|
| `PASSTHROUGH` | Already JSON-compatible | `str`, `int`, `float`, `bool`, `list`, `dict` |
| `ADAPTER` | Serialize/deserialize via adapter | `datetime`, `Path`, `UUID`, custom types |
| `OBJECT_STORE` | Store server-side with handle | Sessions, connections, file handles |
| `UNSUPPORTED` | Cannot be handled | Unregistered complex types |

```python
from auto_mcp.types import TypeRegistry, TypeStrategy

registry = TypeRegistry()
register_stdlib_adapters(registry)

# Check strategy for a type
strategy = registry.get_strategy(datetime)
print(strategy)  # TypeStrategy.ADAPTER

strategy = registry.get_strategy(str)
print(strategy)  # TypeStrategy.PASSTHROUGH

# Get full type info
info = registry.get_type_info(datetime)
print(info.strategy)  # TypeStrategy.ADAPTER
print(info.adapter)  # DateTimeAdapter instance
print(info.json_schema)  # {"type": "string", "format": "date-time"}
```

---

## CLI Reference

### `auto-mcp generate`

Generate MCP server code from Python modules.

```bash
# Generate standalone file
auto-mcp generate mymodule.py -o server.py

# Generate with custom server name
auto-mcp generate mymodule.py -o server.py --name my-server

# Generate a complete Python package
auto-mcp generate mymodule.py --package myserver -o ./dist

# Generate from multiple modules
auto-mcp generate module1.py module2.py -o server.py

# Use LLM for better descriptions
auto-mcp generate mymodule.py -o server.py --llm-provider ollama --llm-model qwen2.5-coder:7b
```

**Options:**
| Option | Description |
|--------|-------------|
| `-o, --output` | Output file path (required) |
| `--name` | Server name (default: auto-mcp-server) |
| `--package` | Generate as package with this name |
| `--llm-provider` | LLM provider: ollama, openai, anthropic |
| `--llm-model` | Model name for the LLM provider |
| `--no-cache` | Disable caching |
| `--include-private` | Include private functions (starting with _) |
| `--enable-sessions` | Enable session lifecycle support |
| `--session-ttl` | Session TTL in seconds (default: 3600) |
| `--max-sessions` | Maximum concurrent sessions (default: 100) |

### `auto-mcp serve`

Run an MCP server directly from Python modules.

```bash
# Basic usage (stdio transport)
auto-mcp serve mymodule.py

# With SSE transport
auto-mcp serve mymodule.py --transport sse --port 8080

# With streamable HTTP transport
auto-mcp serve mymodule.py --transport streamable-http --port 3000

# With hot-reload for development
auto-mcp serve mymodule.py --watch

# With LLM-enhanced descriptions
auto-mcp serve mymodule.py --llm-provider ollama --llm-model qwen2.5-coder:7b
```

**Options:**
| Option | Description |
|--------|-------------|
| `--name` | Server name |
| `--transport` | Transport: stdio, sse, streamable-http (default: stdio) |
| `--port` | Port for HTTP transports (default: 8080) |
| `--host` | Host for HTTP transports (default: 0.0.0.0) |
| `--watch` | Enable hot-reload on file changes |
| `--llm-provider` | LLM provider |
| `--llm-model` | Model name |
| `--enable-sessions` | Enable session lifecycle support |
| `--session-ttl` | Session TTL in seconds (default: 3600) |
| `--max-sessions` | Maximum concurrent sessions (default: 100) |

### `auto-mcp check`

Validate modules without generating output (dry-run).

```bash
# Check what tools would be generated
auto-mcp check mymodule.py

# Verbose output with descriptions
auto-mcp check mymodule.py --verbose
```

### `auto-mcp inspect`

Inspect modules and display detailed MCP component information. This command provides deep visibility into what an MCP server exposes, including tools, resources, prompts, JSON schemas, and parameter details.

```bash
# Basic inspection (table format)
auto-mcp inspect mymodule.py

# Verbose output with full JSON schemas
auto-mcp inspect mymodule.py -v

# JSON output for tooling integration
auto-mcp inspect mymodule.py -f json

# Tree view for hierarchical overview
auto-mcp inspect mymodule.py -f tree

# Filter by name pattern (glob)
auto-mcp inspect mymodule.py --filter "get_*"
auto-mcp inspect mymodule.py --filter "*user*"

# Filter by component type
auto-mcp inspect mymodule.py -t tools
auto-mcp inspect mymodule.py -t resources

# Show source code
auto-mcp inspect mymodule.py --show-source

# Include private methods
auto-mcp inspect mymodule.py --include-private

# Inspect multiple modules
auto-mcp inspect module1.py module2.py
```

**Example Output (table format):**
```
Module: calculator.py

Tools (3)
┌────────────┬─────────────────────────────┬───────┬──────────────┐
│ Name       │ Description                 │ Async │ Parameters   │
├────────────┼─────────────────────────────┼───────┼──────────────┤
│ add        │ Add two numbers together    │       │ a, b         │
│ multiply   │ Multiply two numbers        │       │ x, y         │
│ fetch_rate │ Fetch exchange rate         │ ✓     │ currency     │
└────────────┴─────────────────────────────┴───────┴──────────────┘
```

**Example Output (verbose mode):**
```
Tool: add
Description: Add two numbers together
Async: No  |  Session: No

Parameters:
┌──────┬───────┬──────────┬─────────────────────┐
│ Name │ Type  │ Default  │ Schema              │
├──────┼───────┼──────────┼─────────────────────┤
│ a    │ int   │ required │ {"type": "integer"} │
│ b    │ int   │ required │ {"type": "integer"} │
└──────┴───────┴──────────┴─────────────────────┘

Returns: int
```

**Example Output (tree format):**
```
calculator
├── Tools
│   ├── add(a: int, b: int) -> int
│   │   └── Add two numbers together
│   └── multiply(x: int, y: int) -> int
│       └── Multiply two numbers
└── Resources
    └── (none)
```

**Options:**
| Option | Description |
|--------|-------------|
| `-f, --format` | Output format: table (default), json, tree |
| `--filter` | Filter components by name (glob pattern) |
| `-t, --type` | Component type: tools, resources, prompts, all (default) |
| `-s, --show-schema` | Display full JSON schemas |
| `--show-source` | Display function source code |
| `--include-private` | Include private methods (starting with _) |
| `-v, --verbose` | Verbose output (implies --show-schema) |

### `auto-mcp cache`

Manage the description cache.

```bash
# Show cache statistics
auto-mcp cache stats

# Clear cache for specific modules
auto-mcp cache clear mymodule.py

# Clear all cache
auto-mcp cache clear
```

### `auto-mcp config`

View configuration settings.

```bash
# Show current configuration
auto-mcp config show

# Show environment variable reference
auto-mcp config env
```

### `auto-mcp package`

Commands for working with installed Python packages.

#### `auto-mcp package check`

Analyze a package and show what would be exposed.

```bash
auto-mcp package check requests
auto-mcp package check requests -v
auto-mcp package check boto3 --max-depth 2 --public-api-only
auto-mcp package check pandas --include-reexports  # For packages with re-exports
```

**Options:**
| Option | Description |
|--------|-------------|
| `--max-depth` | Maximum recursion depth |
| `--public-api-only` | Only show `__all__` exports |
| `--include-private` | Include private modules |
| `--include PATTERN` | Glob pattern for modules to include |
| `--exclude PATTERN` | Glob pattern for modules to exclude |
| `--include-reexports` | Include functions re-exported from submodules |
| `-v, --verbose` | Show module tree and details |

#### `auto-mcp package generate`

Generate an MCP server from a package.

```bash
auto-mcp package generate json -o server.py --no-llm
auto-mcp package generate requests -o server.py --public-api-only
auto-mcp package generate pandas -o pandas_server.py --no-llm --include-reexports
```

**Options:**
| Option | Description |
|--------|-------------|
| `-o, --output` | Output file path (required) |
| `--name` | Server name |
| `--max-depth` | Maximum recursion depth |
| `--public-api-only` | Only expose `__all__` exports |
| `--include PATTERN` | Glob pattern for modules to include |
| `--exclude PATTERN` | Glob pattern for modules to exclude |
| `--include-reexports` | Include functions re-exported from submodules |
| `--llm-provider` | LLM provider |
| `--no-llm` | Disable LLM descriptions |

#### `auto-mcp package serve`

Run an MCP server from a package.

```bash
auto-mcp package serve json --no-llm
auto-mcp package serve requests --transport sse --port 3000
auto-mcp package serve pandas --no-llm --include-reexports
```

**Options:**
| Option | Description |
|--------|-------------|
| `--name` | Server name |
| `--transport` | Transport: stdio, sse, streamable-http |
| `--max-depth` | Maximum recursion depth |
| `--public-api-only` | Only expose `__all__` exports (default: True) |
| `--include PATTERN` | Glob pattern for modules to include |
| `--exclude PATTERN` | Glob pattern for modules to exclude |
| `--include-reexports` | Include functions re-exported from submodules |
| `--llm-provider` | LLM provider |
| `--no-llm` | Disable LLM descriptions |

---

## Python API Reference

### AutoMCP Class

The main entry point for programmatic usage.

```python
from auto_mcp import AutoMCP

# Basic initialization (no LLM)
auto = AutoMCP(use_llm=False)

# With Ollama for descriptions
auto = AutoMCP(
    llm_provider="ollama",
    llm_model="qwen2.5-coder:7b",
)

# With OpenAI
auto = AutoMCP(
    llm_provider="openai",
    llm_model="gpt-4o-mini",
    # API key from OPENAI_API_KEY env var or pass directly
)

# With Anthropic
auto = AutoMCP(
    llm_provider="anthropic",
    llm_model="claude-3-haiku-20240307",
)

# Full configuration
auto = AutoMCP(
    llm_provider="ollama",
    llm_model="qwen2.5-coder:7b",
    server_name="my-server",
    use_cache=True,
    cache_dir="./cache",
    include_private=False,
    generate_resources=True,
    generate_prompts=True,
    include_reexports=False,  # Set True for pandas, numpy, etc.
    enable_sessions=False,    # Enable session lifecycle
    session_ttl=3600,         # Session TTL in seconds
    max_sessions=100,         # Maximum concurrent sessions
)
```

### Creating Servers

```python
import mymodule

# Create in-memory server
server = auto.create_server([mymodule])
server.run()

# Create with custom name
server = auto.create_server([mymodule], name="custom-name")

# Create from multiple modules
server = auto.create_server([module1, module2, module3])
```

### Generating Files

```python
from pathlib import Path

# Generate standalone file
auto.generate_file([mymodule], Path("server.py"))

# Generate with custom name
auto.generate_file([mymodule], "server.py", name="my-server")

# Generate complete package
auto.generate_package(
    [mymodule],
    output_dir=Path("./dist"),
    package_name="my-mcp-server",
)
```

### Analyzing Modules

```python
# Async analysis
tools, resources, prompts = await auto.analyze([mymodule])

for tool in tools:
    print(f"Tool: {tool.name} - {tool.description}")

# Sync analysis
tools, resources, prompts = auto.analyze_sync([mymodule])
```

### Quick Server Function

For simple one-off usage:

```python
from auto_mcp import quick_server
import mymodule

# Create and get server in one call
server = quick_server(mymodule, name="quick-server")
server.run()

# Multiple modules
server = quick_server(module1, module2, module3)
```

### Context Manager

```python
# Automatically saves cache on exit
with AutoMCP(use_cache=True, cache_dir="./cache") as auto:
    server = auto.create_server([mymodule])
    # ... use server
# Cache is saved automatically
```

### Cache Management

```python
# Save cache for specific modules
auto.save_cache([mymodule])

# Save all cached data
auto.save_cache()

# Clear cache
count = auto.clear_cache([mymodule])
print(f"Cleared {count} cached entries")

# Clear all cache
auto.clear_cache()
```

---

## Decorators

Control how functions are exposed as MCP components.

### @mcp_tool

Explicitly mark a function as an MCP tool with custom settings.

```python
from auto_mcp import mcp_tool

@mcp_tool(name="custom_add", description="Add two numbers with precision")
def add(a: float, b: float) -> float:
    """This docstring is overridden by the decorator description."""
    return a + b

@mcp_tool()  # Use defaults, just ensure it's exposed
def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b
```

### @mcp_exclude

Exclude a public function from being exposed.

```python
from auto_mcp import mcp_exclude

@mcp_exclude
def helper_function():
    """This public function won't become an MCP tool."""
    pass
```

### @mcp_resource

Mark a function as an MCP resource.

```python
from auto_mcp import mcp_resource

@mcp_resource(uri="data://users/{user_id}")
def get_user(user_id: str) -> dict:
    """Get user data by ID."""
    return {"id": user_id, "name": "Example User"}
```

### @mcp_prompt

Mark a function as an MCP prompt template.

```python
from auto_mcp import mcp_prompt

@mcp_prompt(name="greeting")
def greeting_prompt(name: str, style: str = "formal") -> str:
    """Generate a greeting prompt."""
    if style == "formal":
        return f"Please greet {name} in a formal, professional manner."
    return f"Give a casual, friendly greeting to {name}."
```

### @mcp_session_init

Mark a function as a session initialization hook.

```python
from auto_mcp import mcp_session_init, SessionContext

@mcp_session_init(order=0)
def setup_database(session: SessionContext) -> None:
    """Initialize database connection for this session."""
    session.data.set("db", create_connection())

@mcp_session_init(order=1)  # Runs after order=0
async def load_user_preferences(session: SessionContext) -> None:
    """Load user preferences after DB is ready."""
    db = session.data.get("db")
    prefs = await db.get_preferences(session.metadata.get("user_id"))
    session.data.set("preferences", prefs)
```

### @mcp_session_cleanup

Mark a function as a session cleanup hook.

```python
from auto_mcp import mcp_session_cleanup, SessionContext

@mcp_session_cleanup(order=0)
async def cleanup_database(session: SessionContext) -> None:
    """Close database connection when session ends."""
    db = session.data.get("db")
    if db:
        await db.close()
```

---

## Session Lifecycle

auto-mcp supports explicit session lifecycle management for tools that need to maintain state across multiple calls. This is useful for scenarios like database connections, user preferences, shopping carts, or any stateful operations.

### Overview

When sessions are enabled, auto-mcp automatically adds two tools to your server:

- **`create_session`**: Creates a new session and returns a `session_id`
- **`close_session`**: Closes a session and runs cleanup hooks

Tools that declare a `session: SessionContext` parameter receive the session automatically when called with a `session_id`.

### Enabling Sessions

#### CLI

```bash
# Generate server with sessions enabled
auto-mcp generate mymodule.py -o server.py --enable-sessions

# With custom TTL (2 hours) and max sessions
auto-mcp generate mymodule.py -o server.py --enable-sessions --session-ttl 7200 --max-sessions 50

# Serve with sessions
auto-mcp serve mymodule.py --enable-sessions
```

#### Python API

```python
from auto_mcp import AutoMCP

auto = AutoMCP(
    enable_sessions=True,
    session_ttl=3600,      # Session expires after 1 hour
    max_sessions=100,      # Maximum concurrent sessions
)

server = auto.create_server([mymodule])
server.run()
```

#### Environment Variables

```bash
AUTO_MCP_ENABLE_SESSIONS=true
AUTO_MCP_SESSION_TTL=3600
AUTO_MCP_MAX_SESSIONS=100
```

### Writing Session-Aware Tools

Tools can optionally receive session context by declaring a `session: SessionContext` parameter:

```python
from auto_mcp import SessionContext

def get_cart_items(session: SessionContext) -> list[dict]:
    """Get items in the shopping cart."""
    return session.data.get("cart", [])

def add_to_cart(session: SessionContext, product_id: str, quantity: int) -> dict:
    """Add an item to the shopping cart."""
    cart = session.data.get("cart", [])
    cart.append({"product_id": product_id, "quantity": quantity})
    session.data.set("cart", cart)
    return {"status": "added", "cart_size": len(cart)}

def calculate_total(product_id: str, quantity: int, price: float) -> float:
    """Calculate total for an item (no session needed)."""
    return quantity * price
```

**Important**: Session injection is **optional**. Tools without a `SessionContext` parameter work normally without any session handling.

### Tool Schema Transformation

When a tool declares `session: SessionContext`, the MCP schema is automatically transformed:

**Python function:**
```python
def get_data(session: SessionContext, user_id: str) -> dict:
    return session.data.get(user_id)
```

**Generated MCP tool schema:**
```json
{
  "name": "get_data",
  "inputSchema": {
    "type": "object",
    "properties": {
      "session_id": {"type": "string", "description": "Session ID from create_session"},
      "user_id": {"type": "string"}
    },
    "required": ["session_id", "user_id"]
  }
}
```

The `session` parameter is replaced with `session_id` in the schema, and the actual `SessionContext` is injected at runtime.

### Session Hooks

Use decorators to run code when sessions are created or closed:

```python
from auto_mcp import mcp_session_init, mcp_session_cleanup, SessionContext

@mcp_session_init(order=0)
def on_session_start(session: SessionContext) -> None:
    """Initialize session state."""
    session.data.set("created_at", time.time())
    session.data.set("request_count", 0)

@mcp_session_cleanup(order=0)
async def on_session_end(session: SessionContext) -> None:
    """Clean up session resources."""
    db = session.data.get("db_connection")
    if db:
        await db.close()
```

**Hook execution order:**
- Init hooks run in ascending order (0, 1, 2, ...)
- Cleanup hooks run in descending order (2, 1, 0, ...)

### SessionContext API

```python
@dataclass
class SessionContext:
    session_id: str           # Unique session identifier
    created_at: float         # Unix timestamp of creation
    metadata: dict[str, Any]  # Immutable session metadata
    data: SessionData         # Mutable session data storage

    @property
    def age_seconds(self) -> float:
        """Time since session creation."""
        ...

    def refresh(self) -> bool:
        """Extend session TTL."""
        ...

    def invalidate(self) -> None:
        """Mark session for closure."""
        ...
```

### SessionData API

```python
class SessionData:
    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from session data."""
        ...

    def set(self, key: str, value: Any) -> None:
        """Set a value in session data."""
        ...

    def delete(self, key: str) -> bool:
        """Delete a key from session data."""
        ...

    def clear(self) -> None:
        """Clear all session data."""
        ...

    def keys(self) -> list[str]:
        """Get all keys in session data."""
        ...

    def contains(self, key: str) -> bool:
        """Check if key exists."""
        ...
```

### Complete Example

```python
# mymodule.py
from auto_mcp import (
    SessionContext,
    mcp_session_init,
    mcp_session_cleanup,
)

# Session hooks
@mcp_session_init(order=0)
def init_session(session: SessionContext) -> None:
    """Initialize session with empty cart."""
    session.data.set("cart", [])
    session.data.set("total", 0.0)

@mcp_session_cleanup(order=0)
def cleanup_session(session: SessionContext) -> None:
    """Log session summary on close."""
    cart = session.data.get("cart", [])
    total = session.data.get("total", 0)
    print(f"Session {session.session_id}: {len(cart)} items, ${total:.2f}")

# Session-aware tools
def add_item(session: SessionContext, name: str, price: float) -> dict:
    """Add item to cart."""
    cart = session.data.get("cart", [])
    cart.append({"name": name, "price": price})
    session.data.set("cart", cart)
    session.data.set("total", session.data.get("total", 0) + price)
    return {"added": name, "cart_size": len(cart)}

def get_cart(session: SessionContext) -> dict:
    """Get cart contents."""
    return {
        "items": session.data.get("cart", []),
        "total": session.data.get("total", 0),
    }

def checkout(session: SessionContext) -> dict:
    """Process checkout and clear cart."""
    cart = session.data.get("cart", [])
    total = session.data.get("total", 0)
    session.data.set("cart", [])
    session.data.set("total", 0)
    return {"items_purchased": len(cart), "amount": total}

# Non-session tool (works without session)
def get_product_info(product_id: str) -> dict:
    """Get product details (no session needed)."""
    return {"id": product_id, "name": "Sample Product", "price": 29.99}
```

**Client usage:**
```
1. Call create_session() -> {"session_id": "session:abc123..."}
2. Call add_item(session_id="session:abc123...", name="Widget", price=9.99)
3. Call add_item(session_id="session:abc123...", name="Gadget", price=19.99)
4. Call get_cart(session_id="session:abc123...")
5. Call checkout(session_id="session:abc123...")
6. Call close_session(session_id="session:abc123...")
```

### Session Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `enable_sessions` | `false` | Enable session lifecycle support |
| `session_ttl` | `3600` | Session TTL in seconds (1 hour) |
| `max_sessions` | `100` | Maximum concurrent sessions |

---

## LLM Providers

auto-mcp supports multiple LLM providers for generating tool descriptions.

### Ollama (Local, Recommended)

```bash
# Install Ollama: https://ollama.ai
# Pull a model
ollama pull qwen2.5-coder:7b
```

```python
auto = AutoMCP(
    llm_provider="ollama",
    llm_model="qwen2.5-coder:7b",  # Default
)
```

**Recommended models:**
- `qwen2.5-coder:7b` - Best balance of quality and speed (default)
- `deepseek-coder-v2:16b` - Higher quality, needs more RAM
- `codellama:7b` - Good alternative

### OpenAI

```bash
export OPENAI_API_KEY=your-api-key
```

```python
auto = AutoMCP(
    llm_provider="openai",
    llm_model="gpt-4o-mini",  # Default, cost-effective
)
```

### Anthropic

```bash
export ANTHROPIC_API_KEY=your-api-key
```

```python
auto = AutoMCP(
    llm_provider="anthropic",
    llm_model="claude-3-haiku-20240307",  # Default, fast and cheap
)
```

### Without LLM

Use docstrings directly without LLM enhancement:

```python
auto = AutoMCP(use_llm=False)
```

---

## Configuration

### Environment Variables

All settings can be configured via environment variables with the `AUTO_MCP_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_MCP_LLM_PROVIDER` | `ollama` | LLM provider: ollama, openai, anthropic |
| `AUTO_MCP_LLM_MODEL` | `qwen2.5-coder:7b` | Model name |
| `AUTO_MCP_LLM_BASE_URL` | | Custom LLM endpoint URL |
| `AUTO_MCP_OPENAI_API_KEY` | | OpenAI API key |
| `AUTO_MCP_ANTHROPIC_API_KEY` | | Anthropic API key |
| `AUTO_MCP_CACHE_ENABLED` | `true` | Enable prompt caching |
| `AUTO_MCP_CACHE_DIR` | | Custom cache directory |
| `AUTO_MCP_SERVER_NAME` | `auto-mcp-server` | Default server name |
| `AUTO_MCP_TRANSPORT` | `stdio` | Transport: stdio, sse, streamable-http |
| `AUTO_MCP_HOST` | `0.0.0.0` | Server host for HTTP transports |
| `AUTO_MCP_PORT` | `8080` | Server port for HTTP transports |
| `AUTO_MCP_INCLUDE_PRIVATE` | `false` | Include private functions |
| `AUTO_MCP_GENERATE_RESOURCES` | `true` | Generate MCP resources |
| `AUTO_MCP_GENERATE_PROMPTS` | `true` | Generate MCP prompts |
| `AUTO_MCP_ENABLE_SESSIONS` | `false` | Enable session lifecycle support |
| `AUTO_MCP_SESSION_TTL` | `3600` | Session TTL in seconds |
| `AUTO_MCP_MAX_SESSIONS` | `100` | Maximum concurrent sessions |

### .env File

Create a `.env` file in your project root:

```bash
AUTO_MCP_LLM_PROVIDER=ollama
AUTO_MCP_LLM_MODEL=qwen2.5-coder:7b
AUTO_MCP_CACHE_ENABLED=true
AUTO_MCP_SERVER_NAME=my-server
```

---

## Hot Reload

Enable hot-reload during development to automatically regenerate the server when source files change.

### CLI

```bash
auto-mcp serve mymodule.py --watch
```

### Python API

```python
from auto_mcp import AutoMCP
from auto_mcp.watcher import HotReloadServer

auto = AutoMCP(use_llm=False)

# Create hot-reload server
hot_server = HotReloadServer(auto, [mymodule])

# Run with file watching
hot_server.run()
```

---

## Examples

The `examples/` directory contains complete working examples:

### Simple Math (`examples/simple_math/`)

Basic mathematical functions demonstrating core functionality.

```python
# examples/simple_math/math_utils.py
def add(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b

def factorial(n: int) -> int:
    """Calculate factorial of n."""
    if n <= 1:
        return 1
    return n * factorial(n - 1)
```

```bash
auto-mcp serve examples/simple_math/math_utils.py
```

### Async API (`examples/async_api/`)

Async functions simulating API calls.

```python
# examples/async_api/weather_api.py
async def get_current_weather(city: str, country: str = "US") -> dict:
    """Get current weather for a city."""
    await asyncio.sleep(0.1)  # Simulate API call
    return {"city": city, "temperature": 22.5, "conditions": "Sunny"}

async def get_forecast(city: str, days: int = 5) -> list[dict]:
    """Get weather forecast."""
    ...
```

```bash
auto-mcp serve examples/async_api/weather_api.py
```

### Class Service (`examples/class_service/`)

Class-based service with decorated methods.

```python
# examples/class_service/todo_service.py
from auto_mcp import mcp_tool, mcp_exclude

class TodoService:
    def __init__(self):
        self._todos = {}

    @mcp_tool(name="create_todo", description="Create a new todo item")
    def create(self, title: str, priority: str = "medium") -> dict:
        """Create a todo."""
        ...

    @mcp_tool(name="list_todos")
    def list_all(self, status: str = "all") -> list[dict]:
        """List all todos."""
        ...

    @mcp_exclude
    def _internal_helper(self):
        """Not exposed."""
        pass

# Expose instance methods
todo_service = TodoService()
create_todo = todo_service.create
list_todos = todo_service.list_all
```

```bash
auto-mcp serve examples/class_service/todo_service.py
```

### Pandas Analytics (`examples/pandas_analytics/`)

Demonstrates generating MCP servers from installed packages with re-exported functions, DataFrame serialization, and aggregation operations.

```bash
# Generate the pandas MCP server (530+ tools)
auto-mcp package generate pandas -o examples/pandas_analytics/pandas_server.py \
    --no-llm --max-depth 0 --include-reexports

# Run the test script to verify DataFrame serialization
python examples/pandas_analytics/test_pandas_mcp.py

# Start the pandas server
python examples/pandas_analytics/pandas_server.py
```

**Key features demonstrated:**
- Using `--include-reexports` to expose pandas functions (concat, merge, read_csv, etc.)
- DataFrame serialization/deserialization through the type system
- Aggregation operations (pivot_table, crosstab, groupby)

**Example pandas tools exposed:**
| Tool | Description |
|------|-------------|
| `concat` | Concatenate pandas objects along an axis |
| `merge` | Merge DataFrame objects with database-style join |
| `read_csv` | Read CSV file into DataFrame |
| `read_json` | Read JSON into DataFrame |
| `pivot_table` | Create spreadsheet-style pivot table |
| `crosstab` | Compute cross-tabulation of factors |
| `melt` | Unpivot DataFrame from wide to long format |
| `get_dummies` | Convert categorical to dummy/indicator variables |

```python
# Using the Python API
from auto_mcp import AutoMCP

auto = AutoMCP(
    use_llm=False,
    include_reexports=True,  # Required for pandas
    max_depth=0,
)

# Create server from pandas
server = auto.create_server_from_package("pandas")
```

---

## Pandas MCP Server Setup Guide

The pandas MCP server (`examples/pandas_analytics/`) exposes 100+ pandas functions as MCP tools for data analysis, manipulation, and I/O operations. This section covers setup for various AI coding tools and example conversations.

### Generating the Server

Generate the pandas MCP server with re-exports enabled (required for pandas):

```bash
# Generate the server with all pandas functions
auto-mcp package generate pandas -o examples/pandas_analytics/pandas_server.py \
    --no-llm --max-depth 0 --include-reexports

# Or use the pre-generated server directly
python examples/pandas_analytics/pandas_server.py
```

### Available Tool Categories

The pandas MCP server exposes 100+ tools in these categories:

| Category | Tools | Description |
|----------|-------|-------------|
| **Data I/O** | `read_csv`, `read_excel`, `read_json`, `read_parquet`, `read_sql`, `read_html`, `read_xml`, `read_feather`, `read_pickle` | Read data from various file formats |
| **Data Manipulation** | `concat`, `merge`, `merge_asof`, `merge_ordered`, `melt`, `pivot`, `pivot_table`, `wide_to_long` | Combine, reshape, and transform DataFrames |
| **Data Analysis** | `crosstab`, `cut`, `qcut`, `get_dummies`, `factorize`, `value_counts`, `unique` | Statistical analysis and categorization |
| **Date/Time** | `date_range`, `bdate_range`, `timedelta_range`, `period_range`, `to_datetime`, `to_timedelta` | Date and time operations |
| **JSON Processing** | `json_normalize` | Flatten nested JSON into tabular format |
| **Testing** | `assert_frame_equal`, `assert_series_equal`, `assert_index_equal` | DataFrame comparison utilities |
| **Plotting** | `boxplot`, `scatter_matrix`, `parallel_coordinates`, `andrews_curves`, `radviz` | Visualization helpers |

### Tool Configuration

#### Claude Code

Add the pandas MCP server to your Claude Code configuration:

**Option 1: Project-level configuration (`.claude/settings.local.json`)**

```json
{
  "mcpServers": {
    "pandas-analytics": {
      "command": "uv",
      "args": ["run", "python", "/path/to/auto-mcp-framework/examples/pandas_analytics/pandas_server.py"]
    }
  }
}
```

**Option 2: Global configuration (`~/.claude/settings.json`)**

```json
{
  "mcpServers": {
    "pandas-analytics": {
      "command": "python",
      "args": ["/path/to/auto-mcp-framework/examples/pandas_analytics/pandas_server.py"]
    }
  }
}
```

**Option 3: Using the CLI**

```bash
claude mcp add pandas-analytics -- python /path/to/pandas_server.py
```

#### Cursor

Add to your Cursor MCP configuration file (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "pandas-analytics": {
      "command": "python",
      "args": ["/path/to/auto-mcp-framework/examples/pandas_analytics/pandas_server.py"]
    }
  }
}
```

Restart Cursor after adding the configuration.

#### Windsurf

Add to your Windsurf MCP configuration (`~/.windsurf/mcp.json` or via Settings > MCP):

```json
{
  "mcpServers": {
    "pandas-analytics": {
      "command": "python",
      "args": ["/path/to/auto-mcp-framework/examples/pandas_analytics/pandas_server.py"]
    }
  }
}
```

#### VS Code Copilot (with MCP extension)

**Using the Claude MCP extension:**

Add to `.vscode/settings.json` or user settings:

```json
{
  "mcp.servers": {
    "pandas-analytics": {
      "command": "python",
      "args": ["/path/to/auto-mcp-framework/examples/pandas_analytics/pandas_server.py"]
    }
  }
}
```

**Using Continue.dev with MCP:**

Add to `~/.continue/config.json`:

```json
{
  "mcpServers": [
    {
      "name": "pandas-analytics",
      "command": "python",
      "args": ["/path/to/auto-mcp-framework/examples/pandas_analytics/pandas_server.py"]
    }
  ]
}
```

### Environment Variables

If using uv with pandas dependencies:

```json
{
  "mcpServers": {
    "pandas-analytics": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/auto-mcp-framework", "python", "examples/pandas_analytics/pandas_server.py"],
      "env": {
        "UV_PROJECT_ENVIRONMENT": "/path/to/auto-mcp-framework/.venv"
      }
    }
  }
}
```

### Example Conversations

Below are example prompts and interactions demonstrating the pandas MCP server capabilities.

#### Reading Data Files

**User prompt:**
> Read the sales data from sales_2024.csv and show me the first few rows

**AI response using tools:**
```
[Calls: read_csv(filepath_or_buffer="sales_2024.csv", nrows=5)]
→ DataFrame with columns: date, product, quantity, price, region
   First 5 rows returned

Here's a preview of your sales data:
| date       | product | quantity | price   | region |
|------------|---------|----------|---------|--------|
| 2024-01-01 | Laptop  | 5        | 1200.00 | North  |
| 2024-01-02 | Phone   | 12       | 800.00  | South  |
| 2024-01-03 | Tablet  | 8        | 500.00  | East   |
| 2024-01-04 | Laptop  | 3        | 1200.00 | West   |
| 2024-01-05 | Phone   | 15       | 800.00  | North  |

The CSV has 5 columns: date, product, quantity, price, and region.
```

**User prompt:**
> Read the Excel file report.xlsx, specifically the "Q4 Summary" sheet

**AI response using tools:**
```
[Calls: read_excel(io="report.xlsx", sheet_name="Q4 Summary")]
→ DataFrame with quarterly summary data

Successfully loaded the "Q4 Summary" sheet from report.xlsx:
| Category    | Q4 Revenue | Q4 Units | YoY Growth |
|-------------|------------|----------|------------|
| Electronics | 1,250,000  | 3,200    | 12.5%      |
| Accessories | 450,000    | 8,500    | 8.2%       |
| Services    | 320,000    | 1,100    | 15.8%      |
```

#### Merging and Joining DataFrames

**User prompt:**
> I have two DataFrames - customers and orders. Merge them on customer_id to see order details with customer names.

**AI response using tools:**
```
[Calls: merge(left=customers_df, right=orders_df, on="customer_id", how="inner")]
→ Merged DataFrame with customer and order details

Merged customers with orders (inner join on customer_id):
| customer_id | name    | email              | order_id | amount  | order_date |
|-------------|---------|--------------------| ---------|---------|------------|
| 101         | Alice   | alice@example.com  | ORD-001  | 1200.00 | 2024-01-15 |
| 101         | Alice   | alice@example.com  | ORD-005  | 450.00  | 2024-02-20 |
| 102         | Bob     | bob@example.com    | ORD-002  | 800.00  | 2024-01-18 |
| 103         | Charlie | charlie@email.com  | ORD-003  | 2100.00 | 2024-01-22 |

Found 4 matching records. Use how="left" to include customers without orders.
```

**User prompt:**
> Concatenate the Q1, Q2, and Q3 sales DataFrames into one combined dataset

**AI response using tools:**
```
[Calls: concat(objs=[q1_sales, q2_sales, q3_sales], ignore_index=True)]
→ Combined DataFrame with 450 rows

Combined all three quarters into a single DataFrame:
- Q1: 150 rows
- Q2: 145 rows
- Q3: 155 rows
- **Total: 450 rows**

The combined DataFrame maintains all original columns: date, product, quantity, price, region, revenue.
```

#### Pivot Tables and Cross-Tabulation

**User prompt:**
> Create a pivot table showing total revenue by product and region

**AI response using tools:**
```
[Calls: pivot_table(data=sales_df, values="revenue", index="region", columns="product", aggfunc="sum", fill_value=0, margins=True)]
→ Pivot table with region rows and product columns

Revenue by Region and Product:
| region | Laptop     | Phone      | Tablet    | All        |
|--------|------------|------------|-----------|------------|
| East   | $48,000    | $64,000    | $32,000   | $144,000   |
| North  | $84,000    | $120,000   | $28,000   | $232,000   |
| South  | $60,000    | $96,000    | $40,000   | $196,000   |
| West   | $36,000    | $56,000    | $20,000   | $112,000   |
| All    | $228,000   | $336,000   | $120,000  | $684,000   |

Key insights:
- **Phone** generates the highest revenue ($336K)
- **North region** is the top performer ($232K)
- Total revenue across all products and regions: **$684,000**
```

**User prompt:**
> Show me a cross-tabulation of orders by day of week and product category

**AI response using tools:**
```
[Calls: crosstab(index=orders_df["day_of_week"], columns=orders_df["category"], margins=True)]
→ Cross-tabulation showing order counts

Order Frequency by Day and Category:
| day_of_week | Electronics | Accessories | Services | All |
|-------------|-------------|-------------|----------|-----|
| Monday      | 45          | 62          | 28       | 135 |
| Tuesday     | 52          | 58          | 31       | 141 |
| Wednesday   | 48          | 71          | 25       | 144 |
| Thursday    | 55          | 65          | 29       | 149 |
| Friday      | 68          | 82          | 35       | 185 |
| Saturday    | 42          | 48          | 12       | 102 |
| Sunday      | 38          | 41          | 8        | 87  |
| All         | 348         | 427         | 168      | 943 |

Insights:
- **Friday** is the busiest day (185 orders)
- **Accessories** is the most ordered category (427)
- Weekend orders are significantly lower than weekdays
```

#### Reshaping Data

**User prompt:**
> I have wide-format data with columns for each month. Convert it to long format for analysis.

**AI response using tools:**
```
[Calls: melt(frame=wide_df, id_vars=["product", "region"], value_vars=["jan_sales", "feb_sales", "mar_sales"], var_name="month", value_name="sales")]
→ Long-format DataFrame

Converted from wide to long format using melt:

**Before (wide):**
| product | region | jan_sales | feb_sales | mar_sales |
|---------|--------|-----------|-----------|-----------|
| Laptop  | North  | 5000      | 6200      | 5800      |
| Phone   | North  | 8000      | 7500      | 8200      |

**After (long):**
| product | region | month     | sales |
|---------|--------|-----------|-------|
| Laptop  | North  | jan_sales | 5000  |
| Laptop  | North  | feb_sales | 6200  |
| Laptop  | North  | mar_sales | 5800  |
| Phone   | North  | jan_sales | 8000  |
| Phone   | North  | feb_sales | 7500  |
| Phone   | North  | mar_sales | 8200  |

This format is better for time-series analysis and visualization.
```

#### Data Binning and Categorization

**User prompt:**
> Categorize customers into age groups: Young (18-30), Adult (31-50), Senior (51+)

**AI response using tools:**
```
[Calls: cut(x=customers_df["age"], bins=[18, 30, 50, 100], labels=["Young", "Adult", "Senior"])]
→ Categorical series with age groups

Added age_group column to customers:
| customer_id | name    | age | age_group |
|-------------|---------|-----|-----------|
| 101         | Alice   | 28  | Young     |
| 102         | Bob     | 45  | Adult     |
| 103         | Charlie | 62  | Senior    |
| 104         | Diana   | 31  | Adult     |
| 105         | Eve     | 24  | Young     |

Distribution:
- Young (18-30): 42 customers (35%)
- Adult (31-50): 51 customers (43%)
- Senior (51+): 27 customers (22%)
```

**User prompt:**
> Create dummy variables for the category column for machine learning

**AI response using tools:**
```
[Calls: get_dummies(data=products_df, columns=["category"], prefix="cat")]
→ DataFrame with one-hot encoded category columns

One-hot encoded the category column:
| product_id | name   | price  | cat_Electronics | cat_Accessories | cat_Services |
|------------|--------|--------|-----------------|-----------------|--------------|
| P001       | Laptop | 1200.0 | 1               | 0               | 0            |
| P002       | Case   | 49.99  | 0               | 1               | 0            |
| P003       | Setup  | 150.0  | 0               | 0               | 1            |

Ready for machine learning with 3 binary category columns.
```

#### Working with JSON Data

**User prompt:**
> I have nested JSON data from an API. Flatten it into a DataFrame.

**AI response using tools:**
```
[Calls: json_normalize(data=api_response, record_path="orders", meta=["customer_id", "customer_name"], sep="_")]
→ Flattened DataFrame from nested JSON

Normalized nested JSON structure:

**Original JSON:**
```json
{
  "customer_id": 101,
  "customer_name": "Alice",
  "orders": [
    {"order_id": "A1", "amount": 500, "items": 3},
    {"order_id": "A2", "amount": 750, "items": 5}
  ]
}
```

**Flattened DataFrame:**
| customer_id | customer_name | order_id | amount | items |
|-------------|---------------|----------|--------|-------|
| 101         | Alice         | A1       | 500    | 3     |
| 101         | Alice         | A2       | 750    | 5     |

Each nested order is now a separate row with customer info preserved.
```

#### Date Range Generation

**User prompt:**
> Generate a date range for all business days in Q1 2024

**AI response using tools:**
```
[Calls: bdate_range(start="2024-01-01", end="2024-03-31")]
→ DatetimeIndex with business days

Generated 63 business days in Q1 2024:
- Start: 2024-01-01 (Monday)
- End: 2024-03-29 (Friday)
- Excludes weekends automatically

First 10 dates:
2024-01-01, 2024-01-02, 2024-01-03, 2024-01-04, 2024-01-05,
2024-01-08, 2024-01-09, 2024-01-10, 2024-01-11, 2024-01-12

Use this for time series analysis, trading calendars, or scheduling.
```

#### Detecting Missing Values

**User prompt:**
> Check for missing values in the dataset

**AI response using tools:**
```
[Calls: isna(obj=df)]
→ Boolean DataFrame indicating missing values

[Calls: value_counts(values=df.isna().sum())]
→ Count of missing values per column

Missing value analysis:
| Column     | Missing | Percentage |
|------------|---------|------------|
| email      | 15      | 3.0%       |
| phone      | 8       | 1.6%       |
| address    | 23      | 4.6%       |
| age        | 0       | 0.0%       |
| name       | 0       | 0.0%       |

Recommendations:
- **email**: Consider imputation or requiring at checkout
- **address**: May need data cleaning campaign
- **phone**: Low missing rate, acceptable for most analyses
```

#### DataFrame Comparison (Testing)

**User prompt:**
> Verify that the transformed DataFrame matches the expected output

**AI response using tools:**
```
[Calls: assert_frame_equal(left=result_df, right=expected_df, check_dtype=True)]
→ No exception raised - DataFrames are equal

✓ **Verification passed!**

The transformed DataFrame matches the expected output:
- Column names: ✓ Match
- Data types: ✓ Match
- Values: ✓ Match
- Index: ✓ Match
- Shape: (100, 5) ✓ Match

Your transformation is correct.
```

### Troubleshooting

**Server not starting:**
- Ensure pandas is installed: `pip install pandas`
- Check Python path and environment configuration
- Run `python pandas_server.py` manually to see error messages

**Tools not appearing:**
- Restart your AI tool after configuration changes
- Verify JSON syntax in configuration files
- The server exposes 100+ tools - some UIs may truncate the list

**Memory issues with large DataFrames:**
- Use `nrows` parameter in `read_csv` to limit rows
- Use `chunksize` for streaming large files
- Consider using `read_parquet` for better performance

**Type errors:**
- pandas MCP tools expect Python objects
- The AI will construct DataFrames from your descriptions
- For complex operations, describe the data structure clearly

---

### SQLite Database (`examples/sqlite_database/`)

Demonstrates creating MCP tools for database operations with SQLite.

```bash
# Run the test script
python examples/sqlite_database/test_sqlite_mcp.py

# Start the SQLite MCP server
python examples/sqlite_database/sqlite_server.py
```

**Key features demonstrated:**
- Database connection management
- CRUD operations (Create, Read, Update, Delete)
- Raw SQL query execution
- Aggregation queries (SUM, AVG, COUNT, MIN, MAX)
- JOIN operations between tables
- Sample data generation

**Available tools (18):**
| Tool | Description |
|------|-------------|
| `connect_database` | Connect to SQLite database (memory or file) |
| `disconnect_database` | Close database connection |
| `execute_query` | Execute SQL and return results |
| `execute_script` | Execute multi-statement SQL scripts |
| `create_table` | Create a new table with schema |
| `drop_table` | Drop a table |
| `list_tables` | List all tables in database |
| `describe_table` | Get table schema |
| `insert_row` | Insert a single row |
| `insert_many` | Bulk insert multiple rows |
| `select_all` | Select all rows with pagination |
| `select_where` | Select rows matching conditions |
| `update_rows` | Update rows matching conditions |
| `delete_rows` | Delete rows matching conditions |
| `count_rows` | Count rows in a table |
| `aggregate_query` | Run aggregate functions |
| `join_query` | Execute JOIN between tables |
| `create_sample_data` | Generate sample users/products/orders |

---

## SQLite MCP Server Setup Guide

The SQLite MCP server example (`examples/sqlite_database/`) provides a fully-functional database server that can be integrated with various AI coding tools. This section covers setup and usage examples.

### Generating the Server

First, generate the MCP server from the SQLite tools module:

```bash
# Generate the server
cd examples/sqlite_database
uv run auto-mcp generate sqlite_tools.py -o sqlite_server.py --no-llm --name sqlite-tools
```

Or use the pre-generated `sqlite_server.py` directly.

### Tool Configuration

#### Claude Code

Add the SQLite MCP server to your Claude Code configuration:

**Option 1: Project-level configuration (`.claude/settings.local.json`)**

Create or edit `.claude/settings.local.json` in your project root:

```json
{
  "mcpServers": {
    "sqlite-tools": {
      "command": "uv",
      "args": ["run", "python", "/path/to/auto-mcp-framework/examples/sqlite_database/sqlite_server.py"]
    }
  }
}
```

**Option 2: Global configuration (`~/.claude/settings.json`)**

```json
{
  "mcpServers": {
    "sqlite-tools": {
      "command": "python",
      "args": ["/path/to/auto-mcp-framework/examples/sqlite_database/sqlite_server.py"]
    }
  }
}
```

**Option 3: Using the CLI**

```bash
claude mcp add sqlite-tools -- python /path/to/sqlite_server.py
```

#### Cursor

Add to your Cursor MCP configuration file (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "sqlite-tools": {
      "command": "python",
      "args": ["/path/to/auto-mcp-framework/examples/sqlite_database/sqlite_server.py"]
    }
  }
}
```

Restart Cursor after adding the configuration. The tools will be available in the AI assistant.

#### Windsurf

Add to your Windsurf MCP configuration (`~/.windsurf/mcp.json` or via Settings > MCP):

```json
{
  "mcpServers": {
    "sqlite-tools": {
      "command": "python",
      "args": ["/path/to/auto-mcp-framework/examples/sqlite_database/sqlite_server.py"]
    }
  }
}
```

Alternatively, configure through Windsurf's Settings UI:
1. Open Settings (`Cmd/Ctrl + ,`)
2. Search for "MCP"
3. Add a new server with name `sqlite-tools`
4. Set command to `python` and args to the server path

#### VS Code Copilot (with MCP extension)

For VS Code with GitHub Copilot and an MCP extension:

**Using the Claude MCP extension:**

Add to `.vscode/settings.json` or user settings:

```json
{
  "mcp.servers": {
    "sqlite-tools": {
      "command": "python",
      "args": ["/path/to/auto-mcp-framework/examples/sqlite_database/sqlite_server.py"]
    }
  }
}
```

**Using Continue.dev with MCP:**

Add to `~/.continue/config.json`:

```json
{
  "mcpServers": [
    {
      "name": "sqlite-tools",
      "command": "python",
      "args": ["/path/to/auto-mcp-framework/examples/sqlite_database/sqlite_server.py"]
    }
  ]
}
```

### Environment Variables

If using uv, ensure the correct Python environment:

```json
{
  "mcpServers": {
    "sqlite-tools": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/auto-mcp-framework", "python", "examples/sqlite_database/sqlite_server.py"],
      "env": {
        "UV_PROJECT_ENVIRONMENT": "/path/to/auto-mcp-framework/.venv"
      }
    }
  }
}
```

### Example Conversations

Below are example prompts and interactions demonstrating the SQLite MCP server capabilities.

#### Basic Setup and Sample Data

**User prompt:**
> Create an in-memory database and populate it with sample data for testing

**AI response using tools:**
```
I'll set up a database with sample data for you.

[Calls: connect_database(database=":memory:")]
→ "Connected to ':memory:' as 'default'"

[Calls: create_sample_data()]
→ "Sample data created: users (3), products (5), orders (6)"

[Calls: list_tables()]
→ ["orders", "products", "users"]

I've created an in-memory database with three tables:
- users (3 rows): Alice, Bob, and Charlie
- products (5 rows): Electronics and accessories
- orders (6 rows): Sample purchase history
```

#### Exploring Database Structure

**User prompt:**
> What tables exist and what are their schemas?

**AI response using tools:**
```
[Calls: get_database_info()]
→ {
    "connection": "default",
    "tables": {
      "users": {"row_count": 3, "columns": ["id", "name", "email", "age", "created_at"]},
      "products": {"row_count": 5, "columns": ["id", "name", "price", "category", "stock"]},
      "orders": {"row_count": 6, "columns": ["id", "user_id", "product_id", "quantity", "total", "order_date"]}
    }
  }

[Calls: describe_table(table_name="users")]
→ [
    {"column": "id", "type": "INTEGER", "nullable": false, "primary_key": true},
    {"column": "name", "type": "TEXT", "nullable": false, "primary_key": false},
    {"column": "email", "type": "TEXT", "nullable": true, "primary_key": false},
    {"column": "age", "type": "INTEGER", "nullable": true, "primary_key": false},
    {"column": "created_at", "type": "TIMESTAMP", "nullable": true, "primary_key": false}
  ]

The database has 3 tables:
- **users**: Stores user info (id, name, email, age, created_at)
- **products**: Product catalog (id, name, price, category, stock)
- **orders**: Purchase records linking users to products
```

#### CRUD Operations

**User prompt:**
> Add a new user named "Diana" with email diana@example.com, age 28

**AI response using tools:**
```
[Calls: insert_row(table_name="users", data={"name": "Diana", "email": "diana@example.com", "age": 28})]
→ 4

Done! Added Diana as user ID 4.
```

**User prompt:**
> Show me all users over 25 years old

**AI response using tools:**
```
[Calls: execute_query(sql="SELECT * FROM users WHERE age > 25")]
→ [
    {"id": 1, "name": "Alice", "email": "alice@example.com", "age": 30},
    {"id": 3, "name": "Charlie", "email": "charlie@example.com", "age": 35},
    {"id": 4, "name": "Diana", "email": "diana@example.com", "age": 28}
  ]

Found 3 users over 25: Alice (30), Charlie (35), and Diana (28).
```

**User prompt:**
> Update Diana's age to 29

**AI response using tools:**
```
[Calls: update_rows(table_name="users", data={"age": 29}, conditions={"name": "Diana"})]
→ 1

Updated Diana's age to 29 (1 row affected).
```

#### Aggregation and Analytics

**User prompt:**
> What's the total revenue by product category?

**AI response using tools:**
```
[Calls: execute_query(sql="SELECT p.category, SUM(o.total) as revenue FROM orders o JOIN products p ON o.product_id = p.id GROUP BY p.category")]
→ [
    {"category": "Electronics", "revenue": 3000.00},
    {"category": "Accessories", "revenue": 530.00}
  ]

Revenue breakdown:
- **Electronics**: $3,000.00
- **Accessories**: $530.00
- **Total**: $3,530.00
```

**User prompt:**
> What's the average order value?

**AI response using tools:**
```
[Calls: aggregate_query(table_name="orders", column="total", function="AVG")]
→ [{"result": 588.33}]

The average order value is $588.33.
```

#### JOIN Queries

**User prompt:**
> Show me all orders with customer and product names

**AI response using tools:**
```
[Calls: execute_query(sql="SELECT u.name as customer, p.name as product, o.quantity, o.total FROM orders o JOIN users u ON o.user_id = u.id JOIN products p ON o.product_id = p.id")]
→ [
    {"customer": "Alice", "product": "Laptop", "quantity": 1, "total": 1200.00},
    {"customer": "Alice", "product": "Headphones", "quantity": 2, "total": 300.00},
    {"customer": "Bob", "product": "Phone", "quantity": 1, "total": 800.00},
    {"customer": "Bob", "product": "Keyboard", "quantity": 1, "total": 80.00},
    {"customer": "Charlie", "product": "Tablet", "quantity": 2, "total": 1000.00},
    {"customer": "Charlie", "product": "Headphones", "quantity": 1, "total": 150.00}
  ]

| Customer | Product    | Qty | Total    |
|----------|------------|-----|----------|
| Alice    | Laptop     | 1   | $1,200   |
| Alice    | Headphones | 2   | $300     |
| Bob      | Phone      | 1   | $800     |
| Bob      | Keyboard   | 1   | $80      |
| Charlie  | Tablet     | 2   | $1,000   |
| Charlie  | Headphones | 1   | $150     |
```

#### Working with File-Based Databases

**User prompt:**
> Connect to a SQLite file called 'mydata.db' and show its tables

**AI response using tools:**
```
[Calls: connect_database(database="mydata.db", name="file_db")]
→ "Connected to 'mydata.db' as 'file_db'"

[Calls: list_tables(connection="file_db")]
→ ["customers", "invoices", "line_items"]

Connected to mydata.db. Found 3 tables: customers, invoices, line_items.
```

#### Complex Queries

**User prompt:**
> Find the top spending customer

**AI response using tools:**
```
[Calls: execute_query(sql="SELECT u.name, SUM(o.total) as total_spent FROM orders o JOIN users u ON o.user_id = u.id GROUP BY u.id ORDER BY total_spent DESC LIMIT 1")]
→ [{"name": "Alice", "total_spent": 1500.00}]

Alice is the top spending customer with $1,500.00 in total purchases.
```

**User prompt:**
> Create a new table to track inventory changes

**AI response using tools:**
```
[Calls: create_table(table_name="inventory_log", columns={"id": "INTEGER PRIMARY KEY AUTOINCREMENT", "product_id": "INTEGER REFERENCES products(id)", "change_amount": "INTEGER NOT NULL", "change_type": "TEXT NOT NULL", "changed_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "notes": "TEXT"})]
→ "Table 'inventory_log' created"

[Calls: describe_table(table_name="inventory_log")]
→ [
    {"column": "id", "type": "INTEGER", "primary_key": true},
    {"column": "product_id", "type": "INTEGER", "primary_key": false},
    {"column": "change_amount", "type": "INTEGER", "primary_key": false},
    {"column": "change_type", "type": "TEXT", "primary_key": false},
    {"column": "changed_at", "type": "TIMESTAMP", "primary_key": false},
    {"column": "notes", "type": "TEXT", "primary_key": false}
  ]

Created inventory_log table with columns:
- id (auto-increment primary key)
- product_id (foreign key to products)
- change_amount (required integer)
- change_type (e.g., "restock", "sold", "adjustment")
- changed_at (auto-timestamp)
- notes (optional text)
```

### Troubleshooting

**Server not starting:**
- Ensure Python path is correct and the environment has `mcp` installed
- Check that `sqlite_tools.py` is in the same directory as `sqlite_server.py`
- Run `python sqlite_server.py` manually to see error messages

**Tools not appearing:**
- Restart your AI tool after configuration changes
- Verify JSON syntax in configuration files
- Check tool logs for connection errors

**Permission errors:**
- For file-based databases, ensure write permissions to the directory
- Use absolute paths in database connections

---

## Integration with Claude Desktop

Add your generated server to Claude Desktop's configuration:

```json
{
  "mcpServers": {
    "my-tools": {
      "command": "python",
      "args": ["/path/to/server.py"]
    }
  }
}
```

Or for direct serving:

```json
{
  "mcpServers": {
    "my-tools": {
      "command": "auto-mcp",
      "args": ["serve", "/path/to/mymodule.py"]
    }
  }
}
```

---

## Development

```bash
# Clone the repository
git clone https://github.com/yourusername/auto-mcp.git
cd auto-mcp

# Install with dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov

# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Type check
uv run mypy src/

# Run all checks
uv run ruff format . && uv run ruff check . && uv run mypy src/ && uv run pytest
```

---

## License

MIT
