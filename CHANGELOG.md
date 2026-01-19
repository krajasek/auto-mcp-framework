# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-01-18

### Added

- **Core Framework**
  - Automatic MCP server generation from Python modules
  - LLM-powered tool description generation (Ollama, OpenAI, Anthropic)
  - Multiple output formats: standalone file, Python package, or in-memory server

- **Package Analysis**
  - Recursive analysis of installed packages (pandas, requests, numpy, etc.)
  - Pattern-based include/exclude filtering
  - Re-export detection and handling
  - uvx isolation support for package commands

- **Transport Support**
  - stdio transport for CLI integrations
  - SSE (Server-Sent Events) transport
  - Streamable HTTP with stateless/stateful modes

- **Type System**
  - Comprehensive type serialization for complex Python types
  - Built-in adapters for datetime, Path, UUID, Decimal, Enum
  - Optional adapters for pandas DataFrames, NumPy arrays, PIL Images
  - Compression support (gzip, zlib, lz4) for large data
  - Object store for server-side handle-based storage

- **Session Management**
  - Explicit session lifecycle with `create_session`/`close_session` tools
  - Automatic `SessionContext` injection into functions
  - Session TTL and cleanup hooks
  - Per-session data storage

- **Decorators**
  - `@mcp_tool` - Mark functions as MCP tools with custom metadata
  - `@mcp_exclude` - Exclude functions from exposure
  - `@mcp_resource` - Expose data as MCP resources
  - `@mcp_prompt` - Define prompt templates
  - `@mcp_session_init` / `@mcp_session_cleanup` - Session lifecycle hooks

- **Developer Experience**
  - CLI commands: `generate`, `serve`, `check`, `inspect`, `cache`, `config`, `package`
  - Hot reload for development with file watching
  - File-based caching for LLM responses
  - Comprehensive test suite with 90% coverage

- **Integrations**
  - Claude Desktop configuration guide
  - Cursor IDE integration
  - Windsurf integration
  - VS Code integration

[0.1.0]: https://github.com/krajasek/auto-mcp-framework/releases/tag/v0.1.0
