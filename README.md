# auto-mcp

Automatically generate MCP (Model Context Protocol) servers from Python modules using LLM-powered documentation.

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

### `auto-mcp check`

Validate modules without generating output (dry-run).

```bash
# Check what tools would be generated
auto-mcp check mymodule.py

# Verbose output with descriptions
auto-mcp check mymodule.py --verbose
```

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
