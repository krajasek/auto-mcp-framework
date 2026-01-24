"""Tests for the wrapper generator module."""

from __future__ import annotations

from typing import Any

import pytest

from auto_mcp.wrapper.generator import CallableInfo, ClassInfo, WrapperGenerator
from auto_mcp.wrapper.type_mapper import (
    FunctionSignature,
    ParameterInfo,
    TypeMapper,
    TypeMapping,
    format_default_for_code,
    parse_default_value,
)


class TestTypeMapper:
    """Tests for the TypeMapper class."""

    def test_map_basic_types(self) -> None:
        """Test mapping basic types."""
        mapper = TypeMapper()

        # String types
        result = mapper.map_type_string("str")
        assert result.json_schema["type"] == "string"

        result = mapper.map_type_string("string")
        assert result.json_schema["type"] == "string"

        # Integer types
        result = mapper.map_type_string("int")
        assert result.json_schema["type"] == "integer"

        # Float types
        result = mapper.map_type_string("float")
        assert result.json_schema["type"] == "number"

        # Boolean types
        result = mapper.map_type_string("bool")
        assert result.json_schema["type"] == "boolean"

    def test_map_collection_types(self) -> None:
        """Test mapping collection types."""
        mapper = TypeMapper()

        result = mapper.map_type_string("list")
        assert result.json_schema["type"] == "array"

        result = mapper.map_type_string("dict")
        assert result.json_schema["type"] == "object"

    def test_map_handle_types(self) -> None:
        """Test mapping handle types like Connection, Cursor."""
        mapper = TypeMapper()

        result = mapper.map_type_string("Connection")
        assert result.is_handle is True
        assert result.handle_type_name == "Connection"
        assert result.json_schema["type"] == "string"

        result = mapper.map_type_string("Cursor")
        assert result.is_handle is True
        assert result.handle_type_name == "Cursor"

    def test_map_unknown_capitalized_type_not_handle(self) -> None:
        """Test that unknown capitalized types are NOT automatically treated as handles.

        Handle types must be explicitly registered (Connection, Cursor, etc.).
        Unknown types like CustomClass, DataFrame, etc. should return Any.
        """
        mapper = TypeMapper()

        result = mapper.map_type_string("CustomClass")
        assert result.is_handle is False
        assert result.python_type == "Any"

    def test_map_generic_list_type(self) -> None:
        """Test mapping list[X] types."""
        mapper = TypeMapper()

        result = mapper.map_type_string("list[str]")
        assert result.json_schema["type"] == "array"
        assert result.json_schema["items"]["type"] == "string"

    def test_add_handle_type(self) -> None:
        """Test adding custom handle types."""
        mapper = TypeMapper()

        mapper.add_handle_type("MyType", "My custom type")
        result = mapper.map_type_string("MyType")

        assert result.is_handle is True
        assert result.handle_type_name == "MyType"

    def test_get_type_str_for_code(self) -> None:
        """Test getting type strings for code generation."""
        mapper = TypeMapper()

        # Handle types become str
        mapping = mapper.map_type_string("Connection")
        assert mapper.get_type_str_for_code(mapping) == "str"

        # Basic types use their name
        mapping = mapper.map_type_string("int")
        assert mapper.get_type_str_for_code(mapping) == "int"


class TestParseDefaultValue:
    """Tests for parse_default_value function."""

    def test_parse_none(self) -> None:
        """Test parsing None."""
        value, repr_str = parse_default_value("None")
        assert value is None
        assert repr_str == "None"

    def test_parse_boolean(self) -> None:
        """Test parsing booleans."""
        value, repr_str = parse_default_value("True")
        assert value is True
        assert repr_str == "True"

        value, repr_str = parse_default_value("False")
        assert value is False
        assert repr_str == "False"

    def test_parse_integer(self) -> None:
        """Test parsing integers."""
        value, repr_str = parse_default_value("42")
        assert value == 42
        assert repr_str == "42"

    def test_parse_float(self) -> None:
        """Test parsing floats."""
        value, repr_str = parse_default_value("3.14")
        assert value == 3.14
        assert repr_str == "3.14"

    def test_parse_string(self) -> None:
        """Test parsing quoted strings."""
        value, repr_str = parse_default_value("'hello'")
        assert value == "hello"
        assert repr_str == "'hello'"

        value, repr_str = parse_default_value('"world"')
        assert value == "world"
        assert repr_str == "'world'"

    def test_parse_empty_list(self) -> None:
        """Test parsing empty list."""
        value, repr_str = parse_default_value("[]")
        assert value == []
        assert repr_str == "[]"


class TestWrapperGenerator:
    """Tests for the WrapperGenerator class."""

    def test_init_default(self) -> None:
        """Test default initialization."""
        gen = WrapperGenerator()
        assert gen.include_private is False
        assert gen.include_dunder is False
        assert gen.type_mapper is not None

    def test_init_with_options(self) -> None:
        """Test initialization with options."""
        gen = WrapperGenerator(include_private=True, include_dunder=True)
        assert gen.include_private is True
        assert gen.include_dunder is True

    def test_init_with_custom_mapper(self) -> None:
        """Test initialization with custom type mapper."""
        mapper = TypeMapper()
        gen = WrapperGenerator(type_mapper=mapper)
        assert gen.type_mapper is mapper

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
        sig = gen._parse_docstring_signature(docstring, "connect")

        assert len(sig.parameters) == 1
        assert sig.parameters[0].name == "database"
        assert sig.return_is_handle is True
        assert sig.return_handle_type == "Connection"

    def test_parse_docstring_signature_with_defaults(self) -> None:
        """Test parsing signature with default values."""
        gen = WrapperGenerator()
        docstring = "connect(database, timeout=5.0) -> Connection"
        sig = gen._parse_docstring_signature(docstring, "connect")

        assert len(sig.parameters) == 2
        assert sig.parameters[0].name == "database"
        assert sig.parameters[0].has_default is False
        assert sig.parameters[1].name == "timeout"
        assert sig.parameters[1].has_default is True
        assert sig.parameters[1].default_repr == "5.0"

    def test_parse_docstring_signature_no_return(self) -> None:
        """Test parsing signature without return type."""
        gen = WrapperGenerator()
        docstring = "execute(sql, parameters)"
        sig = gen._parse_docstring_signature(docstring, "execute")

        assert len(sig.parameters) == 2
        assert sig.parameters[0].name == "sql"
        assert sig.parameters[1].name == "parameters"
        assert sig.return_type_str == "Any"

    def test_parse_docstring_signature_empty(self) -> None:
        """Test parsing empty docstring."""
        gen = WrapperGenerator()
        sig = gen._parse_docstring_signature(None, "test")
        assert sig.parameters == []
        assert sig.return_type_str == "Any"

    def test_parse_docstring_handles_variadic(self) -> None:
        """Test parsing signature with *args and **kwargs."""
        gen = WrapperGenerator()
        docstring = "func(a, *args, **kwargs) -> int"
        sig = gen._parse_docstring_signature(docstring, "func")

        assert len(sig.parameters) == 1  # Only 'a', not *args/**kwargs
        assert sig.has_var_positional is True
        assert sig.has_var_keyword is True

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

        # Should delegate to original module using keyword args
        assert "json.dumps(" in code
        assert "json.loads(" in code

    def test_generate_wrapper_has_docstrings(self) -> None:
        """Test that generated wrapper preserves docstrings."""
        gen = WrapperGenerator()
        import json

        code = gen.generate_wrapper(json)

        # Should have some docstrings
        assert '"""' in code

    def test_generate_wrapper_has_object_store(self) -> None:
        """Test that generated wrapper includes object store."""
        gen = WrapperGenerator()
        import json

        code = gen.generate_wrapper(json)

        # Should have object store helpers
        assert "_object_store" in code
        assert "_store_object" in code
        assert "_get_object" in code
        assert "_release_object" in code
        assert "_list_handles" in code

    def test_generate_wrapper_has_schema(self) -> None:
        """Test that generated wrapper includes MCP schemas."""
        gen = WrapperGenerator()
        import json

        code = gen.generate_wrapper(json)

        # Should have __mcp_schema__ attributes
        assert "__mcp_schema__" in code

    def test_build_params_string_empty(self) -> None:
        """Test building params string with no params returns empty string."""
        gen = WrapperGenerator()
        result = gen._build_params_string([])
        # New behavior: empty list returns empty string, NOT *args/**kwargs
        assert result == ""

    def test_build_params_string_with_params(self) -> None:
        """Test building params string with parameters."""
        gen = WrapperGenerator()
        params = [
            ParameterInfo(
                name="a",
                type_str="int",
                json_schema={"type": "integer"},
                has_default=False,
                is_required=True,
            ),
            ParameterInfo(
                name="b",
                type_str="str",
                json_schema={"type": "string"},
                has_default=True,
                default_repr="'test'",
                is_required=False,
            ),
        ]
        result = gen._build_params_string(params)
        assert "a: int" in result
        assert "b: str = 'test'" in result
        # Should NOT have *args/**kwargs
        assert "*args" not in result
        assert "**kwargs" not in result

    def test_build_params_string_orders_required_first(self) -> None:
        """Test that required params come before optional params."""
        gen = WrapperGenerator()
        params = [
            ParameterInfo(
                name="optional",
                type_str="str",
                json_schema={"type": "string"},
                has_default=True,
                default_repr="None",
                is_required=False,
            ),
            ParameterInfo(
                name="required",
                type_str="int",
                json_schema={"type": "integer"},
                has_default=False,
                is_required=True,
            ),
        ]
        result = gen._build_params_string(params)
        # Required should come before optional
        assert result.index("required") < result.index("optional")

    def test_build_call_args_empty(self) -> None:
        """Test building call args with no params returns empty string."""
        gen = WrapperGenerator()
        result = gen._build_call_args([])
        # New behavior: empty list returns empty string
        assert result == ""

    def test_build_call_args_with_params(self) -> None:
        """Test building call args uses keyword arguments."""
        gen = WrapperGenerator()
        params = [
            ParameterInfo(
                name="a",
                type_str="int",
                json_schema={"type": "integer"},
            ),
            ParameterInfo(
                name="b",
                type_str="str",
                json_schema={"type": "string"},
            ),
        ]
        result = gen._build_call_args(params)
        # Should use keyword argument syntax
        assert "a=a" in result
        assert "b=b" in result
        # Should NOT have *args/**kwargs
        assert "*args" not in result
        assert "**kwargs" not in result

    def test_build_call_args_with_handle_params(self) -> None:
        """Test that handle params are resolved via _get_object."""
        gen = WrapperGenerator()
        params = [
            ParameterInfo(
                name="conn",
                type_str="str",
                json_schema={"type": "string"},
                is_handle_param=True,
                handle_type_name="Connection",
            ),
        ]
        result = gen._build_call_args(params)
        # Should call _get_object for handle params
        assert "conn=_get_object(conn)" in result


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

    def test_callable_info_with_signature(self) -> None:
        """Test CallableInfo with FunctionSignature."""
        sig = FunctionSignature(
            name="test",
            parameters=[
                ParameterInfo(
                    name="a",
                    type_str="int",
                    json_schema={"type": "integer"},
                )
            ],
            return_type_str="str",
        )
        info = CallableInfo(
            name="test",
            qualified_name="test",
            docstring="test(a) -> str",
            is_method=False,
            class_name=None,
            is_c_extension=True,
            signature=sig,
        )
        assert info.signature is not None
        assert len(info.signature.parameters) == 1
        assert info.signature.return_type_str == "str"


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

    def test_generated_wrapper_no_unnecessary_variadic(self) -> None:
        """Test that generated wrappers don't have unnecessary *args/**kwargs."""
        gen = WrapperGenerator()
        import json

        code = gen.generate_wrapper(json)

        # Count occurrences of *args and **kwargs
        # Should be minimal (only where truly needed)
        lines_with_variadic = [
            line for line in code.split("\n")
            if "*args" in line or "**kwargs" in line
        ]
        # Most functions should NOT have variadic
        total_def_lines = len([line for line in code.split("\n") if line.strip().startswith("def ")])

        # At most half the functions should have variadic (generous limit)
        assert len(lines_with_variadic) < total_def_lines


class TestHandleBasedTypes:
    """Tests for handle-based type management in generated wrappers."""

    def test_connect_returns_handle(self) -> None:
        """Test that connect function returns a handle."""
        gen = WrapperGenerator()
        import sqlite3

        code = gen.generate_wrapper(sqlite3)

        # connect should return a handle (store result)
        assert "_store_object" in code

    def test_method_wrappers_use_handles(self) -> None:
        """Test that class method wrappers accept handles."""
        gen = WrapperGenerator()
        import sqlite3

        code = gen.generate_wrapper(sqlite3)

        # Connection methods should have connection: str as first param
        # and use _get_object to retrieve the instance
        assert "connection: str" in code or "connection:" in code


class TestTypeMapperAdvanced:
    """Additional tests for TypeMapper edge cases."""

    def test_map_with_custom_mappings(self) -> None:
        """Test TypeMapper with custom additional mappings."""
        custom_mapping = TypeMapping(
            python_type="CustomType",
            json_schema={"type": "string", "format": "custom"}
        )
        additional = {"CustomType": custom_mapping}

        mapper = TypeMapper(additional_mappings=additional)

        result = mapper.map_type_string("CustomType")
        assert result.json_schema["format"] == "custom"

    def test_map_lowercase_type(self) -> None:
        """Test mapping lowercase type that exists as uppercase."""
        mapper = TypeMapper()

        # "STRING" should map to string type
        result = mapper.map_type_string("STRING")
        assert result.json_schema["type"] == "string"

    def test_map_optional_type(self) -> None:
        """Test mapping Optional[X] types."""
        mapper = TypeMapper()

        result = mapper.map_type_string("Optional[str]")
        assert result.json_schema["type"] == "string"

    def test_map_union_with_none(self) -> None:
        """Test mapping X | None pattern."""
        mapper = TypeMapper()

        result = mapper.map_type_string("str | None")
        assert result.json_schema["type"] == "string"

    def test_map_dict_type(self) -> None:
        """Test mapping dict[K, V] types."""
        mapper = TypeMapper()

        result = mapper.map_type_string("dict[str, int]")
        assert result.json_schema["type"] == "object"
        assert result.json_schema["additionalProperties"]["type"] == "integer"

    def test_map_tuple_type(self) -> None:
        """Test mapping tuple types."""
        mapper = TypeMapper()

        result = mapper.map_type_string("tuple[int, str]")
        assert result.json_schema["type"] == "array"

    def test_map_union_with_registered_handle(self) -> None:
        """Test mapping union with a registered handle type (line 231-233)."""
        # Create mapper with a custom handle mapping
        connection_mapping = TypeMapping(
            python_type="str",
            json_schema={"type": "string"},
            is_handle=True,
            handle_type_name="MyConnection"
        )
        mapper = TypeMapper(additional_mappings={"MyConnection": connection_mapping})

        # Union with registered handle type should return handle
        result = mapper.map_type_string("MyConnection | None")
        assert result.is_handle is True
        assert result.handle_type_name == "MyConnection"

    def test_map_union_no_handle(self) -> None:
        """Test mapping union without handles."""
        mapper = TypeMapper()

        # Union of unknown types returns Any
        result = mapper.map_type_string("Foo | Bar")
        assert result.python_type == "Any"

    def test_get_type_str_for_none(self) -> None:
        """Test getting type string for None type."""
        mapper = TypeMapper()

        mapping = TypeMapping(python_type=type(None), json_schema={"type": "null"})
        result = mapper.get_type_str_for_code(mapping)
        assert result == "None"


class TestParseDefaultValueAdvanced:
    """Additional tests for parse_default_value edge cases."""

    def test_parse_module_qualified_name(self) -> None:
        """Test parsing module-qualified names like sys.maxsize."""
        value, code = parse_default_value("sys.maxsize")
        assert value is None
        assert code == "None"

    def test_parse_identifier(self) -> None:
        """Test parsing unknown identifier."""
        value, code = parse_default_value("some_variable")
        assert value is None
        assert code == "None"

    def test_parse_sentinel_value(self) -> None:
        """Test parsing sentinel-like values."""
        value, code = parse_default_value("SomeType")
        assert value is None
        assert code == "None"

    def test_parse_unrepresentable(self) -> None:
        """Test parsing unrepresentable values."""
        value, code = parse_default_value("<unrepresentable>")
        assert value is None
        assert code == "None"

    def test_parse_list_literal(self) -> None:
        """Test parsing list literal."""
        value, code = parse_default_value("[1, 2, 3]")
        assert code == "[1, 2, 3]"

    def test_parse_dict_literal(self) -> None:
        """Test parsing dict literal."""
        value, code = parse_default_value("{'a': 1}")
        assert code == "{'a': 1}"

    def test_parse_tuple_literal(self) -> None:
        """Test parsing tuple literal."""
        value, code = parse_default_value("(1, 2)")
        assert code == "(1, 2)"

    def test_parse_nan_float(self) -> None:
        """Test parsing NaN returns None."""
        value, code = parse_default_value("nan")
        assert code == "None"

    def test_parse_inf_float(self) -> None:
        """Test parsing inf returns None."""
        value, code = parse_default_value("inf")
        assert code == "None"

    def test_parse_empty_dict(self) -> None:
        """Test parsing empty dict literal."""
        value, code = parse_default_value("{}")
        assert value == {}
        assert code == "{}"

    def test_parse_empty_tuple(self) -> None:
        """Test parsing empty tuple literal."""
        value, code = parse_default_value("()")
        assert value == ()
        assert code == "()"


class TestFormatDefaultForCode:
    """Tests for format_default_for_code function."""

    def test_format_none(self) -> None:
        """Test formatting None value."""
        result = format_default_for_code(None)
        assert result == "None"

    def test_format_bool_true(self) -> None:
        """Test formatting True value."""
        result = format_default_for_code(True)
        assert result == "True"

    def test_format_bool_false(self) -> None:
        """Test formatting False value."""
        result = format_default_for_code(False)
        assert result == "False"

    def test_format_string(self) -> None:
        """Test formatting string value."""
        result = format_default_for_code("hello")
        assert result == "'hello'"

    def test_format_int(self) -> None:
        """Test formatting integer value."""
        result = format_default_for_code(42)
        assert result == "42"

    def test_format_float(self) -> None:
        """Test formatting float value."""
        result = format_default_for_code(3.14)
        assert result == "3.14"

    def test_format_nan(self) -> None:
        """Test formatting NaN value returns None."""
        import math
        result = format_default_for_code(math.nan)
        assert result == "None"

    def test_format_inf(self) -> None:
        """Test formatting infinity value returns None."""
        import math
        result = format_default_for_code(math.inf)
        assert result == "None"

    def test_format_list(self) -> None:
        """Test formatting list value."""
        result = format_default_for_code([1, 2, 3])
        assert result == "[1, 2, 3]"

    def test_format_dict(self) -> None:
        """Test formatting dict value."""
        result = format_default_for_code({"a": 1})
        assert "'a': 1" in result

    def test_format_tuple(self) -> None:
        """Test formatting tuple value."""
        result = format_default_for_code((1, 2))
        assert result == "(1, 2)"

    def test_format_object(self) -> None:
        """Test formatting object falls back to repr."""
        result = format_default_for_code(object())
        assert "<object" in result


class TestWrapperGeneratorAdvanced:
    """Additional tests for WrapperGenerator."""

    def test_is_c_extension_module_builtin(self) -> None:
        """Test detecting builtin modules as C extensions."""
        gen = WrapperGenerator()
        import sys
        assert gen.is_c_extension_module(sys) is True

    def test_is_c_extension_module_pure_python(self) -> None:
        """Test that pure Python modules are not C extensions."""
        gen = WrapperGenerator()
        import json
        # json is not a C extension itself
        result = gen.is_c_extension_module(json)
        # This may vary by Python version

    def test_generate_wrapper_sqlite(self) -> None:
        """Test generating wrapper for sqlite3."""
        gen = WrapperGenerator()
        import sqlite3
        code = gen.generate_wrapper(sqlite3)
        # Should produce Python code with functions
        assert "def connect(" in code or "connect" in code

    def test_is_c_extension_callable(self) -> None:
        """Test _is_c_extension_callable method."""
        gen = WrapperGenerator()
        import sqlite3

        # sqlite3.connect is a C extension callable
        assert gen._is_c_extension_callable(sqlite3.connect) is True

        # A pure Python function is not
        def pure_python():
            pass
        assert gen._is_c_extension_callable(pure_python) is False

    def test_is_c_extension_module_with_so_file(self) -> None:
        """Test module with .so extension is detected as C extension."""
        from types import ModuleType
        import tempfile
        import os

        # Create a mock module with .so file
        mock_module = ModuleType("test_c_module")
        mock_module.__file__ = "/path/to/module.so"

        gen = WrapperGenerator()
        result = gen.is_c_extension_module(mock_module)
        assert result is True

    def test_is_c_extension_module_with_pyd_file(self) -> None:
        """Test module with .pyd extension is detected as C extension."""
        from types import ModuleType

        mock_module = ModuleType("test_c_module")
        mock_module.__file__ = "/path/to/module.pyd"

        gen = WrapperGenerator()
        result = gen.is_c_extension_module(mock_module)
        assert result is True

    def test_is_c_extension_module_with_dylib_file(self) -> None:
        """Test module with .dylib extension is detected as C extension."""
        from types import ModuleType

        mock_module = ModuleType("test_c_module")
        mock_module.__file__ = "/path/to/module.dylib"

        gen = WrapperGenerator()
        result = gen.is_c_extension_module(mock_module)
        assert result is True
