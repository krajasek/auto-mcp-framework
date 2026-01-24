"""Tests for the module analyzer."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from auto_mcp.core.analyzer import MethodMetadata, ModuleAnalyzer
from auto_mcp.decorators import mcp_exclude, mcp_prompt, mcp_resource, mcp_tool


# Sample functions for testing
def simple_function(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


async def async_function(url: str) -> dict[str, Any]:
    """Fetch data from a URL asynchronously."""
    return {"url": url}


def _private_function() -> None:
    """This is a private function."""
    pass


def dunder_style_function() -> None:
    """This is a dunder-style function (named for testing)."""
    pass


# Create a real dunder-like function for testing by renaming
dunder_style_function.__name__ = "__dunder_function__"


@mcp_tool(name="custom_add", description="Custom addition tool")
def decorated_tool(x: int, y: int) -> int:
    """A decorated tool function."""
    return x + y


@mcp_exclude
def excluded_function() -> None:
    """This function should be excluded."""
    pass


@mcp_resource(uri="data://items/{id}", mime_type="application/json")
def resource_function(id: str) -> dict[str, Any]:
    """A resource function."""
    return {"id": id}


@mcp_prompt(name="greeting")
def prompt_function(name: str) -> str:
    """A prompt function."""
    return f"Hello, {name}!"


def function_with_defaults(
    required: str,
    optional: int = 10,
    flag: bool = False,
) -> str:
    """Function with default parameter values."""
    return f"{required}-{optional}-{flag}"


class SampleClass:
    """A sample class for testing method analysis."""

    def public_method(self, x: int) -> int:
        """A public method."""
        return x * 2

    async def async_method(self, data: str) -> str:
        """An async method."""
        return data.upper()

    def _private_method(self) -> None:
        """A private method."""
        pass

    @staticmethod
    def static_method(value: str) -> str:
        """A static method."""
        return value.lower()

    @classmethod
    def class_method(cls, name: str) -> str:
        """A class method."""
        return f"Class: {name}"

    @mcp_tool(description="Decorated class method")
    def decorated_method(self, n: int) -> int:
        """A decorated method."""
        return n**2


class TestMethodMetadata:
    """Tests for MethodMetadata dataclass."""

    def test_is_private(self) -> None:
        """Test private method detection."""
        analyzer = ModuleAnalyzer()
        metadata = analyzer._analyze_callable(_private_function, "test_module")
        assert metadata is not None
        assert metadata.is_private is True

        metadata = analyzer._analyze_callable(simple_function, "test_module")
        assert metadata is not None
        assert metadata.is_private is False

    def test_is_dunder(self) -> None:
        """Test dunder method detection."""
        analyzer = ModuleAnalyzer()
        metadata = analyzer._analyze_callable(dunder_style_function, "test_module")
        assert metadata is not None
        assert metadata.is_dunder is True

        metadata = analyzer._analyze_callable(simple_function, "test_module")
        assert metadata is not None
        assert metadata.is_dunder is False

    def test_is_excluded(self) -> None:
        """Test excluded method detection."""
        analyzer = ModuleAnalyzer()
        metadata = analyzer._analyze_callable(excluded_function, "test_module")
        assert metadata is not None
        assert metadata.is_excluded is True

    def test_is_tool(self) -> None:
        """Test tool method detection."""
        analyzer = ModuleAnalyzer()
        metadata = analyzer._analyze_callable(decorated_tool, "test_module")
        assert metadata is not None
        assert metadata.is_tool is True
        assert metadata.mcp_metadata["tool_name"] == "custom_add"
        assert metadata.mcp_metadata["tool_description"] == "Custom addition tool"

    def test_is_resource(self) -> None:
        """Test resource method detection."""
        analyzer = ModuleAnalyzer()
        metadata = analyzer._analyze_callable(resource_function, "test_module")
        assert metadata is not None
        assert metadata.is_resource is True
        assert metadata.mcp_metadata["resource_uri"] == "data://items/{id}"
        assert metadata.mcp_metadata["resource_mime_type"] == "application/json"

    def test_is_prompt(self) -> None:
        """Test prompt method detection."""
        analyzer = ModuleAnalyzer()
        metadata = analyzer._analyze_callable(prompt_function, "test_module")
        assert metadata is not None
        assert metadata.is_prompt is True
        assert metadata.mcp_metadata["prompt_name"] == "greeting"


class TestModuleAnalyzer:
    """Tests for ModuleAnalyzer class."""

    def test_analyze_simple_function(self) -> None:
        """Test analyzing a simple function."""
        analyzer = ModuleAnalyzer()
        metadata = analyzer._analyze_callable(simple_function, "test_module")

        assert metadata is not None
        assert metadata.name == "simple_function"
        assert metadata.qualified_name == "simple_function"
        assert metadata.docstring == "Add two numbers together."
        assert metadata.is_async is False
        assert metadata.is_method is False
        assert metadata.return_type is int

    def test_analyze_async_function(self) -> None:
        """Test analyzing an async function."""
        analyzer = ModuleAnalyzer()
        metadata = analyzer._analyze_callable(async_function, "test_module")

        assert metadata is not None
        assert metadata.name == "async_function"
        assert metadata.is_async is True

    def test_analyze_function_with_defaults(self) -> None:
        """Test analyzing a function with default parameters."""
        analyzer = ModuleAnalyzer()
        metadata = analyzer._analyze_callable(function_with_defaults, "test_module")

        assert metadata is not None
        assert len(metadata.parameters) == 3

        # Check required parameter
        required_param = metadata.parameters[0]
        assert required_param["name"] == "required"
        assert required_param["has_default"] is False

        # Check optional parameter
        optional_param = metadata.parameters[1]
        assert optional_param["name"] == "optional"
        assert optional_param["has_default"] is True
        assert optional_param["default"] == 10

        # Check flag parameter
        flag_param = metadata.parameters[2]
        assert flag_param["name"] == "flag"
        assert flag_param["has_default"] is True
        assert flag_param["default"] is False

    def test_analyze_class_method(self) -> None:
        """Test analyzing a method with class context."""
        analyzer = ModuleAnalyzer()
        metadata = analyzer._analyze_callable(
            SampleClass.public_method,
            "test_module",
            "SampleClass",
        )

        assert metadata is not None
        assert metadata.name == "public_method"
        assert metadata.qualified_name == "SampleClass.public_method"
        assert metadata.is_method is True

    def test_should_expose_excludes_private(self) -> None:
        """Test that private methods are excluded by default."""
        analyzer = ModuleAnalyzer(include_private=False)

        private_meta = analyzer._analyze_callable(_private_function, "test_module")
        assert private_meta is not None
        assert analyzer.should_expose(private_meta) is False

        public_meta = analyzer._analyze_callable(simple_function, "test_module")
        assert public_meta is not None
        assert analyzer.should_expose(public_meta) is True

    def test_should_expose_includes_private_when_enabled(self) -> None:
        """Test that private methods are included when enabled."""
        analyzer = ModuleAnalyzer(include_private=True)

        private_meta = analyzer._analyze_callable(_private_function, "test_module")
        assert private_meta is not None
        assert analyzer.should_expose(private_meta) is True

    def test_should_expose_excludes_dunder(self) -> None:
        """Test that dunder methods are always excluded."""
        analyzer = ModuleAnalyzer(include_private=True)

        dunder_meta = analyzer._analyze_callable(dunder_style_function, "test_module")
        assert dunder_meta is not None
        assert analyzer.should_expose(dunder_meta) is False

    def test_should_expose_excludes_decorated(self) -> None:
        """Test that @mcp_exclude decorated functions are excluded."""
        analyzer = ModuleAnalyzer()

        excluded_meta = analyzer._analyze_callable(excluded_function, "test_module")
        assert excluded_meta is not None
        assert analyzer.should_expose(excluded_meta) is False

    def test_should_expose_includes_decorated_tools(self) -> None:
        """Test that @mcp_tool decorated functions are always included."""
        analyzer = ModuleAnalyzer(include_private=False)

        tool_meta = analyzer._analyze_callable(decorated_tool, "test_module")
        assert tool_meta is not None
        assert analyzer.should_expose(tool_meta) is True

    def test_extract_parameters(self) -> None:
        """Test parameter extraction."""
        analyzer = ModuleAnalyzer()
        sig = inspect.signature(simple_function)
        hints = {"a": int, "b": int}

        params = analyzer._extract_parameters(sig, hints)

        assert len(params) == 2
        assert params[0]["name"] == "a"
        assert params[0]["type"] is int
        assert params[0]["type_str"] == "int"
        assert params[1]["name"] == "b"

    def test_extract_parameters_skips_self(self) -> None:
        """Test that self/cls parameters are skipped."""
        analyzer = ModuleAnalyzer()
        sig = inspect.signature(SampleClass.public_method)

        params = analyzer._extract_parameters(sig, {"x": int})

        # Should only have 'x', not 'self'
        assert len(params) == 1
        assert params[0]["name"] == "x"

    def test_type_to_string(self) -> None:
        """Test type annotation string conversion."""
        analyzer = ModuleAnalyzer()

        assert analyzer._type_to_string(int) == "int"
        assert analyzer._type_to_string(str) == "str"
        assert analyzer._type_to_string(None) == "Any"
        assert "dict" in analyzer._type_to_string(dict[str, int]).lower()

    def test_extract_mcp_metadata_tool(self) -> None:
        """Test MCP metadata extraction for tools."""
        analyzer = ModuleAnalyzer()
        metadata = analyzer._extract_mcp_metadata(decorated_tool)

        assert metadata["is_tool"] is True
        assert metadata["is_excluded"] is False
        assert metadata["tool_name"] == "custom_add"
        assert metadata["tool_description"] == "Custom addition tool"

    def test_extract_mcp_metadata_resource(self) -> None:
        """Test MCP metadata extraction for resources."""
        analyzer = ModuleAnalyzer()
        metadata = analyzer._extract_mcp_metadata(resource_function)

        assert metadata["is_resource"] is True
        assert metadata["resource_uri"] == "data://items/{id}"
        assert metadata["resource_mime_type"] == "application/json"

    def test_extract_mcp_metadata_plain(self) -> None:
        """Test MCP metadata extraction for plain functions."""
        analyzer = ModuleAnalyzer()
        metadata = analyzer._extract_mcp_metadata(simple_function)

        assert metadata["is_tool"] is False
        assert metadata["is_excluded"] is False
        assert metadata["is_resource"] is False
        assert metadata["is_prompt"] is False


class TestModuleAnalyzerFile:
    """Tests for file-based module analysis."""

    def test_analyze_file(self, tmp_path: Path) -> None:
        """Test analyzing a Python file."""
        # Create a sample module file
        module_code = '''
def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"

def _helper() -> None:
    """Internal helper."""
    pass

class Greeter:
    """A greeter class."""

    def say_hello(self, name: str) -> str:
        """Say hello."""
        return f"Hello, {name}!"
'''
        module_file = tmp_path / "sample.py"
        module_file.write_text(module_code)

        analyzer = ModuleAnalyzer()
        results = analyzer.analyze_file(module_file)

        # Should include greet function and Greeter.say_hello method
        names = [m.name for m in results]
        assert "greet" in names
        assert "say_hello" in names
        assert "_helper" not in names  # Private excluded

    def test_analyze_file_with_decorators(self, tmp_path: Path) -> None:
        """Test analyzing a file with MCP decorators."""
        module_code = '''
from auto_mcp.decorators import mcp_tool, mcp_exclude

@mcp_tool(name="add")
def add_numbers(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

@mcp_exclude
def internal() -> None:
    """Internal function."""
    pass

def public_func() -> str:
    """A public function."""
    return "hello"
'''
        module_file = tmp_path / "decorated.py"
        module_file.write_text(module_code)

        analyzer = ModuleAnalyzer()
        results = analyzer.analyze_file(module_file)

        names = [m.name for m in results]
        assert "add_numbers" in names
        assert "public_func" in names
        assert "internal" not in names  # Excluded by decorator

        # Check that add_numbers has tool metadata
        add_meta = next(m for m in results if m.name == "add_numbers")
        assert add_meta.is_tool is True

    def test_analyze_file_not_found(self) -> None:
        """Test analyzing a non-existent file."""
        analyzer = ModuleAnalyzer()

        with pytest.raises((FileNotFoundError, ValueError)):
            analyzer.analyze_file(Path("/nonexistent/module.py"))


class TestClassAnalysis:
    """Tests for class method analysis."""

    def test_analyze_class_methods(self) -> None:
        """Test analyzing class methods."""
        analyzer = ModuleAnalyzer()
        results = analyzer._analyze_class(SampleClass, "test_module")

        method_names = [m.name for m in results]

        # Should include public methods
        assert "public_method" in method_names
        assert "async_method" in method_names
        assert "static_method" in method_names
        assert "class_method" in method_names
        assert "decorated_method" in method_names

        # Should include private method (filtering happens in should_expose)
        assert "_private_method" in method_names

    def test_class_method_qualified_names(self) -> None:
        """Test that class methods have correct qualified names."""
        analyzer = ModuleAnalyzer()
        results = analyzer._analyze_class(SampleClass, "test_module")

        for method in results:
            assert method.qualified_name.startswith("SampleClass.")

    def test_async_class_method(self) -> None:
        """Test detecting async class methods."""
        analyzer = ModuleAnalyzer()
        results = analyzer._analyze_class(SampleClass, "test_module")

        async_method = next(m for m in results if m.name == "async_method")
        assert async_method.is_async is True

        sync_method = next(m for m in results if m.name == "public_method")
        assert sync_method.is_async is False


class TestMethodMetadataToDict:
    """Tests for MethodMetadata.to_dict() serialization."""

    def test_to_dict_basic(self) -> None:
        """Test basic serialization to dict."""
        analyzer = ModuleAnalyzer()
        metadata = analyzer._analyze_callable(simple_function, "test_module")

        assert metadata is not None
        result = metadata.to_dict()

        assert result["name"] == "simple_function"
        assert "qualified_name" in result
        assert "signature" in result
        assert "type_hints" in result

    def test_to_dict_with_generic_type_hints(self) -> None:
        """Test serialization with generic type hints."""
        def func_with_generics(items: list[str], mapping: dict[str, int]) -> tuple[int, str]:
            """Function with generic type hints."""
            return (1, "test")

        func_with_generics.__module__ = "test_module"
        analyzer = ModuleAnalyzer()
        metadata = analyzer._analyze_callable(func_with_generics, "test_module")

        assert metadata is not None
        result = metadata.to_dict()

        # Type hints should be stringified
        assert isinstance(result["type_hints"], dict)
        assert "items" in result["type_hints"]
        assert "mapping" in result["type_hints"]

    def test_to_dict_with_non_serializable_default(self) -> None:
        """Test serialization with non-JSON-serializable defaults."""
        class CustomObj:
            pass

        sentinel = CustomObj()

        def func_with_complex_default(x: int = 5, obj: object = sentinel) -> None:
            pass

        func_with_complex_default.__module__ = "test_module"
        analyzer = ModuleAnalyzer()
        metadata = analyzer._analyze_callable(func_with_complex_default, "test_module")

        assert metadata is not None
        result = metadata.to_dict()

        # Should serialize without error
        assert "parameters" in result
        # Complex defaults should be converted to repr strings
        params = result["parameters"]
        assert len(params) >= 1

    def test_to_dict_with_return_type(self) -> None:
        """Test serialization with return type annotation."""
        analyzer = ModuleAnalyzer()
        metadata = analyzer._analyze_callable(simple_function, "test_module")

        assert metadata is not None
        result = metadata.to_dict()

        assert "return_type" in result
        assert result["return_type"] == "int"

    def test_from_dict_roundtrip(self) -> None:
        """Test that to_dict and from_dict work as a roundtrip."""
        analyzer = ModuleAnalyzer()
        metadata = analyzer._analyze_callable(simple_function, "test_module")

        assert metadata is not None
        serialized = metadata.to_dict()

        # Deserialize
        restored = MethodMetadata.from_dict(serialized)

        assert restored.name == metadata.name
        assert restored.qualified_name == metadata.qualified_name
        assert restored.module_name == metadata.module_name
        assert restored.is_async == metadata.is_async

    def test_from_dict_minimal(self) -> None:
        """Test from_dict with minimal data."""
        data = {
            "name": "test_func",
            "qualified_name": "module.test_func",
            "module_name": "module",
        }

        restored = MethodMetadata.from_dict(data)

        assert restored.name == "test_func"
        assert restored.qualified_name == "module.test_func"
        assert restored.parameters == []
        assert restored.type_hints == {}
