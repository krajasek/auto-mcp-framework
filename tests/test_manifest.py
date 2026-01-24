"""Tests for the manifest-based MCP server generation."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from auto_mcp.manifest.schema import Manifest, ToolEntry
from auto_mcp.manifest.resolver import PatternResolver, ResolvedTool, resolve_all_patterns
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

    def test_manifest_from_yaml_not_found(self, tmp_path: Path) -> None:
        """Test loading a manifest that doesn't exist."""
        nonexistent = tmp_path / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError):
            Manifest.from_yaml(nonexistent)

    def test_manifest_from_yaml_empty(self, tmp_path: Path) -> None:
        """Test loading an empty YAML manifest."""
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")

        manifest = Manifest.from_yaml(yaml_file)
        # Empty YAML results in None for server_name
        assert manifest.server_name is None
        # But default for auto_include_dependencies should be True
        assert manifest.auto_include_dependencies is True

    def test_manifest_from_dict(self) -> None:
        """Test creating manifest from dictionary."""
        data = {
            "server_name": "my-server",
            "tools": ["connect", "execute"]
        }

        manifest = Manifest.from_dict(data)
        assert manifest.server_name == "my-server"
        assert len(manifest.tools) == 2

    def test_manifest_to_yaml(self, tmp_path: Path) -> None:
        """Test writing manifest to YAML."""
        manifest = Manifest(
            server_name="test-server",
            tools=["connect", {"function": "execute", "name": "my_execute"}]
        )

        yaml_file = tmp_path / "output.yaml"
        manifest.to_yaml(yaml_file)

        assert yaml_file.exists()

        # Read back and verify
        loaded = Manifest.from_yaml(yaml_file)
        assert loaded.server_name == "test-server"

    def test_manifest_to_yaml_simple_tools(self, tmp_path: Path) -> None:
        """Test writing manifest with simple tool entries."""
        manifest = Manifest(
            server_name="test-server",
            tools=[
                ToolEntry(function="simple_func"),  # Should become string
                ToolEntry(function="named_func", name="custom_name"),  # Should stay dict
            ]
        )

        yaml_file = tmp_path / "output.yaml"
        manifest.to_yaml(yaml_file)

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

    def test_method_return_type_inference(self) -> None:
        """Test method return type inference map."""
        generator = ManifestGenerator()

        handle_types = {"Connection", "Cursor"}
        method_map = generator._build_method_inference_map(handle_types)

        # Methods that return handles should be mapped
        assert "cursor" in method_map  # Returns Cursor
        assert method_map["cursor"] == "Cursor"

    def test_generate_with_variadic_params(self, tmp_path: Path) -> None:
        """Test generating tools with *args and **kwargs."""
        import json

        manifest = Manifest(
            server_name="json-server",
            tools=["JSONEncoder.encode"],
        )

        generator = ManifestGenerator()
        output = tmp_path / "server.py"
        code = generator.generate(json, manifest, output)

        # Should generate valid code even with special params
        assert "def jsonencoder_encode(" in code

    def test_generate_with_auto_dependencies(self, tmp_path: Path) -> None:
        """Test generating with auto_include_dependencies enabled."""
        import sqlite3

        manifest = Manifest(
            server_name="sqlite-server",
            auto_include_dependencies=True,
            tools=["Connection.close"],  # Use a simple method
        )

        generator = ManifestGenerator()
        output = tmp_path / "server.py"
        code = generator.generate(sqlite3, manifest, output)

        # Should have the requested method
        assert "def connection_close(" in code
        # The method signature should have connection parameter
        assert "connection:" in code

    def test_escape_docstring(self) -> None:
        """Test escaping docstrings with backslashes."""
        generator = ManifestGenerator()

        # Test escaping backslashes
        docstring = "This has a \\n newline escape"
        escaped = generator._escape_docstring(docstring)
        assert "\\\\" in escaped

    def test_safe_function_name(self) -> None:
        """Test converting names to valid function names."""
        generator = ManifestGenerator()

        # Test various conversions
        assert generator._safe_function_name("Class.method") == "Class_method"
        assert generator._safe_function_name("my-func") == "my_func"
        assert generator._safe_function_name("123start") == "_123start"

    def test_generate_with_constructor(self, tmp_path: Path) -> None:
        """Test generating a server with class constructor."""
        import json

        manifest = Manifest(
            server_name="json-server",
            tools=["JSONEncoder"],  # Class as constructor
        )

        generator = ManifestGenerator()
        output = tmp_path / "server.py"
        code = generator.generate(json, manifest, output)

        # Should have constructor
        assert "def jsonencoder(" in code or "def JSONEncoder(" in code

    def test_build_params_string_empty(self) -> None:
        """Test building params string with empty params."""
        generator = ManifestGenerator()

        result = generator._build_params_string([])
        assert result == ""

    def test_build_call_args_empty(self) -> None:
        """Test building call args with empty params."""
        generator = ManifestGenerator()

        result = generator._build_call_args([])
        assert result == ""

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

    def test_get_type_name_with_type(self) -> None:
        """Test _get_type_name with actual type."""
        import json

        analyzer = DependencyAnalyzer(json)
        result = analyzer._get_type_name(str)
        assert result == "str"

    def test_get_type_name_with_string(self) -> None:
        """Test _get_type_name with string type hint."""
        import json

        analyzer = DependencyAnalyzer(json)
        result = analyzer._get_type_name("MyClass")
        assert result == "MyClass"

    def test_get_type_name_with_none(self) -> None:
        """Test _get_type_name returns None for unknown types."""
        import json

        analyzer = DependencyAnalyzer(json)
        result = analyzer._get_type_name(123)
        assert result is None

    def test_find_producers_empty(self) -> None:
        """Test find_producers with no matching producers."""
        import json

        analyzer = DependencyAnalyzer(json)
        # Try to find producers for a type that nothing produces
        result = analyzer.find_producers(type(None))
        assert isinstance(result, list)

    def test_find_producers_by_name_not_found(self) -> None:
        """Test find_producers_by_name with non-existent class."""
        import json

        analyzer = DependencyAnalyzer(json)
        result = analyzer.find_producers_by_name("NonExistentClass")
        assert result == []

    def test_get_required_types(self) -> None:
        """Test get_required_types returns method class names."""
        import json

        analyzer = DependencyAnalyzer(json)

        tools = [
            ResolvedTool(
                callable_obj=json.JSONEncoder.encode,
                name="JSONEncoder.encode",
                qualified_name="JSONEncoder.encode",
                class_name="JSONEncoder",
                is_method=True,
            ),
            ResolvedTool(
                callable_obj=json.dumps,
                name="dumps",
                qualified_name="dumps",
                is_method=False,
            ),
        ]

        required = analyzer.get_required_types(tools)
        assert "JSONEncoder" in required
        # dumps is not a method, so no class required
        assert len(required) == 1

    def test_auto_include_with_constructor(self) -> None:
        """Test auto_include adds class constructors."""
        import sqlite3

        analyzer = DependencyAnalyzer(sqlite3)

        # Create a tool that needs Connection
        tools = [
            ResolvedTool(
                callable_obj=sqlite3.Connection.close,
                name="Connection.close",
                qualified_name="Connection.close",
                class_name="Connection",
                is_method=True,
            ),
        ]

        result = analyzer.auto_include(tools)
        # Should have added connect() which creates Connections
        assert len(result) >= len(tools)

    def test_build_return_type_map(self) -> None:
        """Test _build_return_type_map covers private callables."""
        import json

        analyzer = DependencyAnalyzer(json)

        # The analyzer should have built a map of return types
        # Just verify it was initialized
        assert isinstance(analyzer._return_type_map, dict)
        assert isinstance(analyzer._class_to_producers, dict)

    def test_find_producers_with_subclass(self) -> None:
        """Test find_producers handles subclass relationships."""
        import io

        analyzer = DependencyAnalyzer(io)

        # Try to find producers - should not error even if no matches
        result = analyzer.find_producers(io.IOBase)
        assert isinstance(result, list)

    def test_auto_include_with_typed_producers(self) -> None:
        """Test auto_include with functions that have return type hints."""
        from types import ModuleType
        from typing import get_type_hints

        # Create a test module with typed functions
        test_module = ModuleType("test_typed_module")

        class MyClass:
            def method(self) -> str:
                return "result"

        def create_my_class() -> MyClass:
            """Factory function returning MyClass."""
            return MyClass()

        # Set up module
        test_module.MyClass = MyClass
        test_module.create_my_class = create_my_class
        create_my_class.__module__ = "test_typed_module"
        MyClass.__module__ = "test_typed_module"

        analyzer = DependencyAnalyzer(test_module)

        # Create a tool that uses MyClass
        tools = [
            ResolvedTool(
                callable_obj=MyClass.method,
                name="MyClass.method",
                qualified_name="MyClass.method",
                class_name="MyClass",
                is_method=True,
            ),
        ]

        result = analyzer.auto_include(tools)
        # Should have the original tool
        assert len(result) >= 1

    def test_dependency_analyzer_with_type_hints(self) -> None:
        """Test dependency analyzer builds type map correctly."""
        import json

        analyzer = DependencyAnalyzer(json)

        # The return type map should be populated
        # JSONDecoder produces objects
        assert isinstance(analyzer._return_type_map, dict)

    def test_get_type_name_variations(self) -> None:
        """Test _get_type_name with different type representations."""
        import json

        analyzer = DependencyAnalyzer(json)

        # Test with actual type
        result = analyzer._get_type_name(str)
        assert result == "str"

        # Test with string
        result = analyzer._get_type_name("CustomClass")
        assert result == "CustomClass"

        # Test with unknown
        result = analyzer._get_type_name(42)
        assert result is None


class TestPatternResolverAdvanced:
    """Additional tests for PatternResolver."""

    def test_is_class_pattern(self) -> None:
        """Test _is_class_pattern method."""
        import json

        resolver = PatternResolver(json)

        # JSONEncoder is a class
        assert resolver._is_class_pattern("JSONEncoder") is True

        # dumps is a function, not a class
        assert resolver._is_class_pattern("dumps") is False

    def test_is_method_pattern(self) -> None:
        """Test _is_method_pattern method."""
        import json

        resolver = PatternResolver(json)

        # JSONEncoder.encode is a method
        assert resolver._is_method_pattern("JSONEncoder.encode") is True

        # Non-existent method
        assert resolver._is_method_pattern("JSONEncoder.nonexistent") is False

        # Not a class.method pattern
        assert resolver._is_method_pattern("dumps") is False

    def test_get_attribute_with_module_prefix(self) -> None:
        """Test _get_attribute handles module prefix."""
        import json

        resolver = PatternResolver(json)

        # Should handle json.dumps
        result = resolver._get_attribute("json.dumps")
        assert result is json.dumps

    def test_get_attribute_nonexistent(self) -> None:
        """Test _get_attribute returns None for missing attributes."""
        import json

        resolver = PatternResolver(json)

        result = resolver._get_attribute("nonexistent_function")
        assert result is None

    def test_resolve_function_not_callable(self) -> None:
        """Test _resolve_function returns empty for non-callable."""
        import json

        resolver = PatternResolver(json)

        # __name__ is a string, not callable
        result = resolver._resolve_function("__name__")
        assert result == []

    def test_resolve_class_as_constructor(self) -> None:
        """Test resolving a class returns constructor tool."""
        import json

        resolver = PatternResolver(json)

        result = resolver.resolve("JSONEncoder")
        assert len(result) >= 1

        # Should have a constructor
        constructors = [t for t in result if t.is_constructor]
        assert len(constructors) == 1

    def test_resolve_method(self) -> None:
        """Test resolving a method pattern."""
        import json

        resolver = PatternResolver(json)

        result = resolver.resolve("JSONEncoder.encode")
        assert len(result) == 1
        assert result[0].is_method is True
        assert result[0].class_name == "JSONEncoder"

    def test_resolve_with_custom_name(self) -> None:
        """Test resolving with custom name and description."""
        import json

        resolver = PatternResolver(json)

        result = resolver.resolve(
            "dumps",
            custom_name="my_dumps",
            custom_description="Custom description"
        )
        assert len(result) == 1
        assert result[0].custom_name == "my_dumps"
        assert result[0].custom_description == "Custom description"

    def test_resolve_glob_class_methods(self) -> None:
        """Test resolving glob patterns for class methods."""
        import json

        resolver = PatternResolver(json)

        # Resolve JSONEncoder.en* (should match encode)
        result = resolver.resolve("JSONEncoder.en*")
        assert len(result) >= 1

        # Check that encode is in the results
        names = [t.name for t in result]
        assert "JSONEncoder.encode" in names

    def test_resolve_glob_module_level(self) -> None:
        """Test resolving glob patterns at module level."""
        import json

        resolver = PatternResolver(json)

        # Resolve dump* (should match dumps, dump)
        result = resolver.resolve("dump*")
        assert len(result) >= 1

        names = [t.name for t in result]
        assert "dumps" in names

    def test_resolve_class_returns_constructor(self) -> None:
        """Test resolving class returns constructor."""
        import json

        resolver = PatternResolver(json)

        result = resolver.resolve("JSONEncoder")
        constructors = [t for t in result if t.is_constructor]
        assert len(constructors) == 1

    def test_resolve_nonexistent_function(self) -> None:
        """Test resolving nonexistent function returns empty list."""
        import json

        resolver = PatternResolver(json)

        result = resolver.resolve("nonexistent_function_xyz")
        assert result == []


class TestResolveAllPatterns:
    """Tests for resolve_all_patterns function."""

    def test_resolve_multiple_patterns(self) -> None:
        """Test resolving multiple patterns."""
        import json

        patterns = [
            ("dumps", None, None),
            ("loads", "my_loads", "Custom description"),
        ]

        result = resolve_all_patterns(json, patterns)

        assert len(result) == 2
        names = [t.name for t in result]
        assert "dumps" in names
        assert "loads" in names

    def test_resolve_all_deduplicates(self) -> None:
        """Test that resolve_all_patterns deduplicates tools."""
        import json

        # Same pattern twice
        patterns = [
            ("dumps", None, None),
            ("dumps", None, None),
        ]

        result = resolve_all_patterns(json, patterns)

        # Should only have one dumps
        assert len(result) == 1


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
