"""Worker functions for isolated execution in uvx subprocess.

These functions run inside the uvx subprocess and communicate
results back to the parent process via JSON on stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from auto_mcp.core.package import PackageAnalyzer
from auto_mcp.isolation.manager import IsolationConfig


def _output_result(success: bool, data: dict[str, Any] | None = None, error: str | None = None) -> None:
    """Output a JSON result to stdout.

    Args:
        success: Whether the operation succeeded
        data: Result data (if success)
        error: Error message (if not success)
    """
    result = {"success": success}
    if data:
        result.update(data)
    if error:
        result["error"] = error

    print(json.dumps(result), flush=True)


def worker_check(config_json: str) -> None:
    """Worker entry point for package check.

    Analyzes the package and outputs JSON result to stdout.

    Args:
        config_json: JSON-encoded IsolationConfig
    """
    try:
        config = IsolationConfig.from_dict(json.loads(config_json))

        analyzer = PackageAnalyzer(
            include_private=config.include_private,
            max_depth=config.max_depth,
            include_reexports=config.include_reexports,
        )

        metadata = analyzer.analyze_package(
            config.package_name,
            include_patterns=config.include_patterns,
            exclude_patterns=config.exclude_patterns,
        )

        # Serialize and output
        _output_result(
            success=True,
            data={"metadata": metadata.to_dict()},
        )

    except ImportError as e:
        _output_result(success=False, error=f"Cannot import package: {e}")
        sys.exit(1)
    except Exception as e:
        _output_result(success=False, error=str(e))
        sys.exit(1)


def worker_generate(config_json: str) -> None:
    """Worker entry point for package generate.

    Generates an MCP server file and outputs JSON result to stdout.

    Args:
        config_json: JSON-encoded IsolationConfig
    """
    try:
        config = IsolationConfig.from_dict(json.loads(config_json))

        if not config.output_path:
            _output_result(success=False, error="output_path is required")
            sys.exit(1)

        output_path = Path(config.output_path)

        # Import generator components
        from auto_mcp.core.generator import GeneratorConfig, MCPGenerator

        # Create generator config with all analysis options
        server_name = config.server_name or f"{config.package_name}-mcp-server"
        gen_config = GeneratorConfig(
            server_name=server_name,
            include_private=config.include_private,
            max_depth=config.max_depth,
            public_api_only=config.public_api_only,
            include_patterns=config.include_patterns,
            exclude_patterns=config.exclude_patterns,
            include_reexports=config.include_reexports,
            enable_sessions=config.enable_sessions,
            session_ttl=config.session_ttl,
            max_sessions=config.max_sessions,
            use_llm=False,  # LLM not available in isolation
        )

        # Generate server code using generate_standalone_from_package
        generator = MCPGenerator(config=gen_config, llm=None, cache=None)
        result_path = generator.generate_standalone_from_package(
            config.package_name,
            output_path,
        )

        _output_result(
            success=True,
            data={
                "output_path": str(result_path),
                "server_name": server_name,
            },
        )

    except ImportError as e:
        _output_result(success=False, error=f"Cannot import package: {e}")
        sys.exit(1)
    except Exception as e:
        _output_result(success=False, error=str(e))
        sys.exit(1)


def worker_serve(config_json: str) -> None:
    """Worker entry point for package serve.

    Runs the MCP server directly. This function does not return
    until the server is stopped.

    Args:
        config_json: JSON-encoded IsolationConfig
    """
    try:
        config = IsolationConfig.from_dict(json.loads(config_json))

        # Import generator components
        from auto_mcp.core.generator import GeneratorConfig, MCPGenerator

        # Create generator config
        server_name = config.server_name or f"{config.package_name}-mcp-server"
        gen_config = GeneratorConfig(
            server_name=server_name,
            include_private=config.include_private,
            max_depth=config.max_depth,
            public_api_only=config.public_api_only,
            include_patterns=config.include_patterns,
            exclude_patterns=config.exclude_patterns,
            include_reexports=config.include_reexports,
            enable_sessions=config.enable_sessions,
            session_ttl=config.session_ttl,
            max_sessions=config.max_sessions,
        )

        # Create generator (without LLM - not available in isolation)
        generator = MCPGenerator(config=gen_config, llm=None, cache=None)

        # Create server from package
        server = generator.create_server_from_package(config.package_name)

        # Run server
        server.run(transport=config.transport)

    except ImportError as e:
        # For serve, we print error to stderr since stdout is for MCP
        print(f"Error: Cannot import package: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
