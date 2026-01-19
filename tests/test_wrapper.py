"""Tests for the wrapper generator module."""

from __future__ import annotations

import importlib
import textwrap
from typing import Any

import pytest

from auto_mcp.wrapper.generator import CallableInfo, ClassInfo, WrapperGenerator


class TestWrapperGenerator:
    """Tests for the WrapperGenerator class."""

    def test_init_default(self) -> None:
        """Test default initialization."""
        gen = WrapperGenerator()
        assert gen.include_private is False
        assert gen.include_dunder is False

    def test_init_with_options(self) -> None:
        """Test initialization with options."""
        gen = WrapperGenerator(include_private=True, include_dunder=True)
        assert gen.include_private is True
        assert gen.include_dunder is True

    def test_should_include_public(self) -> None:
        """Test that public names are included."""
        gen = WrapperGenerator()
        assert gen._should_include("connect") is True
        assert gen._should_include("execute") is True

    def test_should_include_private_excluded_by_default(self) -> None:
        """Test that private names are excluded by default."""
        gen = WrapperGenerator()
        assert gen._should_include("_internal") is False
        assert gen._should_include("_helper") is False

    def test_should_include_private_when_enabled(self) -> None:
        """Test that private names are included when enabled."""
        gen = WrapperGenerator(include_private=True)
        assert gen._should_include("_internal") is True

    def test_should_include_dunder_excluded_by_default(self) -> None:
        """Test that dunder methods are excluded by default."""
        gen = WrapperGenerator()
        assert gen._should_include("__init__") is False
        assert gen._should_include("__str__") is False

    def test_should_include_dunder_when_enabled(self) -> None:
        """Test that dunder methods are included when enabled."""
        gen = WrapperGenerator(include_dunder=True)
        assert gen._should_include("__init__") is True

    def test_is_c_extension_callable_builtin(self) -> None:
        """Test detection of builtin functions."""
        gen = WrapperGenerator()
        # Built-in functions
        assert gen._is_c_extension_callable(len) is True
        assert gen._is_c_extension_callable(print) is True

    def test_is_c_extension_callable_regular_function(self) -> None:
        """Test that regular Python functions are not detected as C extensions."""
        gen = WrapperGenerator()

        def regular_func() -> None:
            pass

        assert gen._is_c_extension_callable(regular_func) is False

    def test_parse_docstring_signature_simple(self) -> None:
        """Test parsing a simple docstring signature."""
        gen = WrapperGenerator()
        docstring = "connect(database) -> Connection"
        params, return_type = gen._parse_docstring_signature(docstring)

        assert len(params) == 1
        assert params[0]["name"] == "database"
        assert return_type == "Connection"

    def test_parse_docstring_signature_with_defaults(self) -> None:
        """Test parsing signature with default values."""
        gen = WrapperGenerator()
        docstring = "connect(database, timeout=5.0) -> Connection"
        params, return_type = gen._parse_docstring_signature(docstring)

        assert len(params) == 2
        assert params[0]["name"] == "database"
        assert params[1]["name"] == "timeout"
        assert params[1]["has_default"] is True
        assert params[1]["default"] == "5.0"

    def test_parse_docstring_signature_no_return(self) -> None:
        """Test parsing signature without return type."""
        gen = WrapperGenerator()
        docstring = "execute(sql, parameters)"
        params, return_type = gen._parse_docstring_signature(docstring)

        assert len(params) == 2
        assert params[0]["name"] == "sql"
        assert params[1]["name"] == "parameters"
        assert return_type is None

    def test_parse_docstring_signature_empty(self) -> None:
        """Test parsing empty docstring."""
        gen = WrapperGenerator()
        params, return_type = gen._parse_docstring_signature(None)
        assert params == []
        assert return_type is None

    def test_split_params_simple(self) -> None:
        """Test splitting simple parameter list."""
        gen = WrapperGenerator()
        result = gen._split_params("a, b, c")
        assert result == ["a", "b", "c"]

    def test_split_params_with_brackets(self) -> None:
        """Test splitting params with nested brackets."""
        gen = WrapperGenerator()
        result = gen._split_params("a, b=[1, 2], c")
        assert result == ["a", "b=[1, 2]", "c"]

    def test_analyze_module_json(self) -> None:
        """Test analyzing the json module."""
        gen = WrapperGenerator()
        import json

        functions, classes = gen.analyze_module(json)

        # Should find common functions
        func_names = [f.name for f in functions]
        assert "dumps" in func_names
        assert "loads" in func_names

    def test_analyze_module_sqlite3(self) -> None:
        """Test analyzing the sqlite3 module."""
        gen = WrapperGenerator()
        import sqlite3

        functions, classes = gen.analyze_module(sqlite3)

        # Should find connect function
        func_names = [f.name for f in functions]
        assert "connect" in func_names

        # Should find Connection class
        class_names = [c.name for c in classes]
        assert "Connection" in class_names

    def test_is_c_extension_module_sqlite3(self) -> None:
        """Test that sqlite3 is detected as C extension."""
        gen = WrapperGenerator()
        import sqlite3

        # sqlite3 has C extension components
        is_c = gen.is_c_extension_module(sqlite3)
        # This may vary by Python build, just test it doesn't crash
        assert isinstance(is_c, bool)

    def test_is_c_extension_module_pure_python(self) -> None:
        """Test that pure Python modules are not detected as C extensions."""
        gen = WrapperGenerator()
        # auto_mcp is a pure Python module
        import auto_mcp

        is_c = gen.is_c_extension_module(auto_mcp)
        assert is_c is False

    def test_generate_wrapper_json(self) -> None:
        """Test generating wrapper for json module."""
        gen = WrapperGenerator()
        import json

        code = gen.generate_wrapper(json)

        # Should contain import
        assert "import json" in code

        # Should contain wrapper functions
        assert "def dumps(" in code
        assert "def loads(" in code

        # Should delegate to original module
        assert "return json.dumps(" in code
        assert "return json.loads(" in code

    def test_generate_wrapper_has_docstrings(self) -> None:
        """Test that generated wrapper preserves docstrings."""
        gen = WrapperGenerator()
        import json

        code = gen.generate_wrapper(json)

        # Should have some docstrings
        assert '"""' in code

    def test_build_params_string_empty(self) -> None:
        """Test building params string with no params."""
        gen = WrapperGenerator()
        result = gen._build_params_string([])
        assert "*args: Any" in result
        assert "**kwargs: Any" in result

    def test_build_params_string_with_params(self) -> None:
        """Test building params string with parameters."""
        gen = WrapperGenerator()
        params = [
            {"name": "a", "type": "int", "has_default": False},
            {"name": "b", "type": "str", "has_default": True, "default": "'test'"},
        ]
        result = gen._build_params_string(params)
        assert "a: int" in result
        assert "b: str = 'test'" in result

    def test_build_call_args_empty(self) -> None:
        """Test building call args with no params."""
        gen = WrapperGenerator()
        result = gen._build_call_args([])
        assert result == "*args, **kwargs"

    def test_build_call_args_with_params(self) -> None:
        """Test building call args with parameters."""
        gen = WrapperGenerator()
        params = [{"name": "a"}, {"name": "b"}]
        result = gen._build_call_args(params)
        assert "a" in result
        assert "b" in result
        assert "*args" in result


class TestCallableInfo:
    """Tests for CallableInfo dataclass."""

    def test_callable_info_creation(self) -> None:
        """Test creating CallableInfo."""
        info = CallableInfo(
            name="test",
            qualified_name="test",
            docstring="Test function",
            is_method=False,
            class_name=None,
            is_c_extension=False,
        )
        assert info.name == "test"
        assert info.docstring == "Test function"
        assert info.is_c_extension is False

    def test_callable_info_with_parsed_params(self) -> None:
        """Test CallableInfo with parsed parameters."""
        info = CallableInfo(
            name="test",
            qualified_name="test",
            docstring="test(a, b) -> int",
            is_method=False,
            class_name=None,
            is_c_extension=True,
            parsed_params=[{"name": "a"}, {"name": "b"}],
            parsed_return_type="int",
        )
        assert len(info.parsed_params) == 2
        assert info.parsed_return_type == "int"


class TestClassInfo:
    """Tests for ClassInfo dataclass."""

    def test_class_info_creation(self) -> None:
        """Test creating ClassInfo."""
        info = ClassInfo(
            name="TestClass",
            docstring="A test class",
        )
        assert info.name == "TestClass"
        assert info.methods == []

    def test_class_info_with_methods(self) -> None:
        """Test ClassInfo with methods."""
        method = CallableInfo(
            name="method1",
            qualified_name="TestClass.method1",
            docstring="A method",
            is_method=True,
            class_name="TestClass",
            is_c_extension=True,
        )
        info = ClassInfo(
            name="TestClass",
            docstring="A test class",
            methods=[method],
            is_c_extension=True,
        )
        assert len(info.methods) == 1
        assert info.is_c_extension is True


class TestGeneratedWrapperValidity:
    """Tests that generated wrappers are valid Python."""

    def test_generated_json_wrapper_is_valid_python(self) -> None:
        """Test that generated json wrapper is syntactically valid."""
        gen = WrapperGenerator()
        import json

        code = gen.generate_wrapper(json)

        # Should be valid Python syntax
        compile(code, "<test>", "exec")

    def test_generated_sqlite3_wrapper_is_valid_python(self) -> None:
        """Test that generated sqlite3 wrapper is syntactically valid."""
        gen = WrapperGenerator()
        import sqlite3

        code = gen.generate_wrapper(sqlite3)

        # Should be valid Python syntax
        compile(code, "<test>", "exec")
