"""Tests for the manifest-based MCP server generation."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from auto_mcp.manifest.schema import Manifest, ToolEntry
from auto_mcp.manifest.resolver import PatternResolver, ResolvedTool
from auto_mcp.manifest.generator import ManifestGenerator
from auto_mcp.manifest.dependencies import DependencyAnalyzer, analyze_and_include_dependencies


class TestManifestSchema:
    """Tests for the Manifest schema."""

    def test_manifest_from_yaml(self, tmp_path: Path) -> None:
        """Test loading a manifest from YAML."""
        yaml_content = """
server_name: test-server
auto_include_dependencies: true

tools:
  - connect
  - Connection.execute
"""
        yaml_file = tmp_path / "manifest.yaml"
        yaml_file.write_text(yaml_content)

        manifest = Manifest.from_yaml(yaml_file)

        assert manifest.server_name == "test-server"
        assert manifest.auto_include_dependencies is True
        assert len(manifest.tools) == 2

    def test_manifest_get_tool_entries(self) -> None:
        """Test extracting tool entries from manifest."""
        manifest = Manifest(
            tools=[
                "simple_func",
                {"function": "renamed_func", "name": "my_func", "description": "Custom description"},
            ]
        )

        entries = manifest.get_tool_entries()

        assert len(entries) == 2
        assert entries[0].function == "simple_func"
        assert entries[0].name is None
        assert entries[1].function == "renamed_func"
        assert entries[1].name == "my_func"
        assert entries[1].description == "Custom description"

    def test_manifest_get_server_name(self) -> None:
        """Test getting server name with default."""
        manifest1 = Manifest(tools=["func"])
        assert manifest1.get_server_name() == "auto-mcp-server"

        manifest2 = Manifest(server_name="custom-server", tools=["func"])
        assert manifest2.get_server_name() == "custom-server"

    def test_manifest_get_module_name(self) -> None:
        """Test getting module name with fallback."""
        manifest1 = Manifest(tools=["func"])
        assert manifest1.get_module_name("fallback") == "fallback"

        manifest2 = Manifest(module="custom_module", tools=["func"])
        assert manifest2.get_module_name("fallback") == "custom_module"

    def test_tool_entry_basic(self) -> None:
        """Test creating ToolEntry with basic fields."""
        entry = ToolEntry(function="my_function")

        assert entry.function == "my_function"
        assert entry.name is None
        assert entry.description is None

    def test_tool_entry_with_customization(self) -> None:
        """Test creating ToolEntry with custom name and description."""
        entry = ToolEntry(
            function="my_function",
            name="renamed",
            description="My description"
        )

        assert entry.function == "my_function"
        assert entry.name == "renamed"
        assert entry.description == "My description"


class TestPatternResolver:
    """Tests for the PatternResolver."""

    def test_resolve_simple_function(self) -> None:
        """Test resolving a simple top-level function."""
        import json

        resolver = PatternResolver(json)
        tools = resolver.resolve("loads")

        assert len(tools) == 1
        assert tools[0].name == "loads"
        assert tools[0].callable_obj == json.loads
        assert tools[0].is_method is False
        assert tools[0].is_constructor is False

    def test_resolve_class_expands_methods(self) -> None:
        """Test that resolving a class includes its methods."""
        import json

        resolver = PatternResolver(json)
        tools = resolver.resolve("JSONEncoder")

        # Should include constructor and public methods
        names = {t.name for t in tools}
        assert "JSONEncoder" in names  # Constructor
        assert any("encode" in n for n in names)  # encode method

    def test_resolve_specific_method(self) -> None:
        """Test resolving a specific class method."""
        import json

        resolver = PatternResolver(json)
        tools = resolver.resolve("JSONEncoder.encode")

        assert len(tools) == 1
        assert tools[0].name == "JSONEncoder.encode"
        assert tools[0].is_method is True
        assert tools[0].class_name == "JSONEncoder"

    def test_resolve_glob_pattern(self) -> None:
        """Test resolving a glob pattern."""
        import json

        resolver = PatternResolver(json)
        tools = resolver.resolve("dump*")

        names = {t.name for t in tools}
        assert "dump" in names
        assert "dumps" in names

    def test_resolved_tool_get_tool_name(self) -> None:
        """Test ResolvedTool.get_tool_name method."""
        tool1 = ResolvedTool(
            callable_obj=lambda: None,
            name="Connection.execute",
            qualified_name="Connection.execute",
            class_name="Connection",
            is_method=True,
        )
        assert tool1.get_tool_name() == "connection_execute"

        tool2 = ResolvedTool(
            callable_obj=lambda: None,
            name="connect",
            qualified_name="connect",
            custom_name="my_connect",
        )
        assert tool2.get_tool_name() == "my_connect"


class TestManifestGenerator:
    """Tests for the ManifestGenerator."""

    def test_generate_simple_module(self, tmp_path: Path) -> None:
        """Test generating a server from json module."""
        import json

        manifest = Manifest(
            server_name="json-server",
            tools=["loads", "dumps"],
        )

        generator = ManifestGenerator()
        output = tmp_path / "server.py"
        code = generator.generate(json, manifest, output)

        assert 'mcp = FastMCP(name="json-server")' in code
        assert "@mcp.tool" in code
        assert "def loads(" in code
        assert "def dumps(" in code
        assert output.exists()

    def test_generate_with_class_methods(self, tmp_path: Path) -> None:
        """Test generating a server with class methods."""
        import sqlite3

        manifest = Manifest(
            server_name="sqlite-server",
            tools=["connect", "Connection.execute", "Connection.close"],
        )

        generator = ManifestGenerator()
        output = tmp_path / "server.py"
        code = generator.generate(sqlite3, manifest, output)

        assert "def connect(" in code
        assert "def connection_execute(" in code
        assert "def connection_close(" in code
        # Should use handle storage for connect
        assert "_store_object(result, \"Connection\")" in code

    def test_factory_return_type_inference(self) -> None:
        """Test that factory functions are detected."""
        generator = ManifestGenerator()

        # Build inference map with Connection and Cursor
        handle_types = {"Connection", "Cursor"}
        factory_map = generator._build_factory_inference_map(handle_types)

        # "connect" should map to "Connection"
        assert factory_map.get("connect") == "Connection"
        # "cursor" should map to "Cursor"
        assert factory_map.get("cursor") == "Cursor"

    def test_method_return_type_inference(self) -> None:
        """Test that method return types are inferred."""
        generator = ManifestGenerator()

        handle_types = {"Cursor", "Connection"}
        method_map = generator._build_method_return_inference(handle_types)

        # "execute" should map to "Cursor"
        assert method_map.get("execute") == "Cursor"

    def test_has_none_default_params(self) -> None:
        """Test detection of None-default parameters."""
        from auto_mcp.wrapper.type_mapper import ParameterInfo

        generator = ManifestGenerator()

        params_with_none = [
            ParameterInfo(name="x", type_str="Any", json_schema={}, has_default=True, default_value=None, default_repr="None", is_required=False),
        ]
        assert generator._has_none_default_params(params_with_none) is True

        params_without_none = [
            ParameterInfo(name="x", type_str="Any", json_schema={}, has_default=True, default_value=5, default_repr="5", is_required=False),
        ]
        assert generator._has_none_default_params(params_without_none) is False


class TestDependencyAnalyzer:
    """Tests for the DependencyAnalyzer."""

    def test_analyze_dependencies(self) -> None:
        """Test analyzing dependencies for tools."""
        import json

        # Create some resolved tools
        tools = [
            ResolvedTool(
                callable_obj=json.JSONEncoder.encode,
                name="JSONEncoder.encode",
                qualified_name="JSONEncoder.encode",
                class_name="JSONEncoder",
                is_method=True,
            ),
        ]

        result = analyze_and_include_dependencies(json, tools)

        # Should include the original tools plus any auto-included ones
        assert len(result) >= len(tools)


class TestIntegration:
    """Integration tests for manifest-based generation."""

    def test_full_sqlite_workflow(self, tmp_path: Path) -> None:
        """Test generating and running a sqlite3 MCP server."""
        import sqlite3
        import sys

        manifest = Manifest(
            server_name="sqlite-test",
            auto_include_dependencies=True,
            tools=[
                "connect",
                "Connection.execute",
                "Connection.commit",
                "Connection.close",
                "Cursor.fetchall",
            ],
        )

        generator = ManifestGenerator()
        output = tmp_path / "sqlite_server.py"
        code = generator.generate(sqlite3, manifest, output)

        # Verify the generated code
        assert "def connect(" in code
        assert "def connection_execute(" in code
        assert "def cursor_fetchall(" in code

        # Import and test the generated module
        sys.path.insert(0, str(tmp_path))
        try:
            import sqlite_server  # type: ignore

            # Test the workflow
            conn_handle = sqlite_server.connect(":memory:")
            assert conn_handle.startswith("Connection_")

            cursor_handle = sqlite_server.connection_execute(
                conn_handle, "CREATE TABLE test (id INTEGER)"
            )
            assert cursor_handle.startswith("Cursor_")

            sqlite_server.connection_execute(conn_handle, "INSERT INTO test VALUES (1)")
            sqlite_server.connection_commit(conn_handle)

            cursor_handle2 = sqlite_server.connection_execute(
                conn_handle, "SELECT * FROM test"
            )
            rows = sqlite_server.cursor_fetchall(cursor_handle2)
            assert rows == [(1,)]

            sqlite_server.connection_close(conn_handle)
        finally:
            sys.path.remove(str(tmp_path))
            # Clean up imported module
            if "sqlite_server" in sys.modules:
                del sys.modules["sqlite_server"]

    def test_generate_with_custom_tool_names(self, tmp_path: Path) -> None:
        """Test generating with custom tool names."""
        import json

        manifest = Manifest(
            server_name="json-server",
            tools=[
                {"function": "loads", "name": "parse_json", "description": "Parse JSON string"},
                "dumps",
            ],
        )

        generator = ManifestGenerator()
        output = tmp_path / "server.py"
        code = generator.generate(json, manifest, output)

        # Should use custom name
        assert '@mcp.tool(name="parse_json")' in code
        # Should use default name
        assert '@mcp.tool(name="dumps")' in code
