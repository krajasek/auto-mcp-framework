# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python framework that automatically generates MCP (Model Context Protocol) servers from Python modules by analyzing code structure and using LLMs to generate intelligent tool descriptions.

**Python is the primary language for this project.**

## Development Setup

This project uses `uv` for dependency management (Python 3.10+).

```bash
# Install dependencies
uv sync

# Install dev dependencies
uv sync --extra dev

# Run the CLI
uv run auto-mcp-tool--help

# Generate an MCP server from a module
uv run auto-mcp-toolgenerate mymodule.py -o server.py

# Serve a module directly
uv run auto-mcp-toolserve mymodule.py --port 8080
```

## Code Quality

- **Linting & Formatting**: Use Ruff for both linting and formatting
  ```bash
  uv run ruff check .
  uv run ruff format .
  ```
- **Type Checking**: Use mypy with strict mode
  ```bash
  uv run mypy src/
  ```
- **Testing**: Use pytest with 90% coverage target
  ```bash
  uv run pytest
  ```
- **Pre-commit Hooks**: Enforce code hygiene via pre-commit hooks
  ```bash
  uv run pre-commit install
  uv run pre-commit run --all-files
  ```

## Git Workflow

Use `gh` CLI for git management (PRs, issues, etc.).

## Architecture

```
src/auto_mcp/
├── __init__.py         # Public API: AutoMCP, decorators
├── cli.py              # Click CLI commands
├── config.py           # Pydantic Settings (AUTO_MCP_ prefix)
├── decorators.py       # @mcp_tool, @mcp_exclude, @mcp_resource, @mcp_prompt
├── core/
│   ├── analyzer.py     # Module introspection with ast + inspect
│   ├── generator.py    # MCP server code generation
│   └── server.py       # In-memory FastMCP server runtime
├── llm/
│   ├── base.py         # LLMProvider Protocol
│   ├── ollama.py       # Ollama integration (default)
│   ├── openai.py       # OpenAI API integration
│   └── anthropic.py    # Anthropic API integration
├── prompts/
│   └── templates.py    # LLM prompt templates for description generation
├── cache/
│   └── file_cache.py   # File-based prompt caching
├── watcher.py          # Hot-reload with watchdog
└── utils/
    └── logging.py      # Logging configuration
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `auto-mcp-toolgenerate <module> -o <output>` | Generate standalone MCP server file |
| `auto-mcp-toolgenerate <module> --package <name>` | Generate MCP server package |
| `auto-mcp-toolserve <module>` | Run in-memory MCP server |
| `auto-mcp-toolcheck <module>` | Dry-run validation |
| `auto-mcp-toolinspect <module>` | Inspect tools, schemas, and metadata |
| `auto-mcp-toolcache clear <module>` | Clear prompt cache |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_MCP_LLM_PROVIDER` | `ollama` | LLM provider: ollama, openai, anthropic |
| `AUTO_MCP_LLM_MODEL` | `qwen2.5-coder:7b` | Model name for prompt generation |
| `AUTO_MCP_CACHE_ENABLED` | `true` | Enable prompt caching |
| `AUTO_MCP_SERVER_NAME` | `auto-mcp-server` | Name for generated servers |
| `AUTO_MCP_TRANSPORT` | `stdio` | MCP transport: stdio, sse, streamable-http |

## Key Dependencies

- `mcp` - Official MCP Python SDK with FastMCP
- `pydantic-settings` - Configuration management
- `ollama` - Local LLM integration (default)
- `openai`, `anthropic` - Cloud LLM alternatives
- `watchdog` - File system watching for hot-reload
- `rich` - Terminal output formatting
- `click` - CLI framework
