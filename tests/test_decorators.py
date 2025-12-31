"""Tests for MCP decorators."""

from auto_mcp.decorators import (
    MCP_EXCLUDE_MARKER,
    MCP_PROMPT_MARKER,
    MCP_RESOURCE_MARKER,
    MCP_TOOL_MARKER,
    get_mcp_metadata,
    mcp_exclude,
    mcp_prompt,
    mcp_resource,
    mcp_tool,
)


class TestMcpTool:
    """Tests for mcp_tool decorator."""

    def test_basic_decoration(self) -> None:
        """Test basic tool decoration without arguments."""

        @mcp_tool()
        def my_func() -> None:
            pass

        assert hasattr(my_func, MCP_TOOL_MARKER)
        meta = getattr(my_func, MCP_TOOL_MARKER)
        assert meta["name"] is None
        assert meta["description"] is None

    def test_with_custom_name(self) -> None:
        """Test tool decoration with custom name."""

        @mcp_tool(name="custom_name")
        def my_func() -> None:
            pass

        meta = getattr(my_func, MCP_TOOL_MARKER)
        assert meta["name"] == "custom_name"

    def test_with_custom_description(self) -> None:
        """Test tool decoration with custom description."""

        @mcp_tool(description="Custom description")
        def my_func() -> None:
            pass

        meta = getattr(my_func, MCP_TOOL_MARKER)
        assert meta["description"] == "Custom description"

    def test_preserves_function(self) -> None:
        """Test that decoration preserves the original function."""

        @mcp_tool(name="add")
        def add(a: int, b: int) -> int:
            return a + b

        assert add(2, 3) == 5


class TestMcpExclude:
    """Tests for mcp_exclude decorator."""

    def test_marks_function(self) -> None:
        """Test that function is marked as excluded."""

        @mcp_exclude
        def internal_helper() -> None:
            pass

        assert hasattr(internal_helper, MCP_EXCLUDE_MARKER)
        assert getattr(internal_helper, MCP_EXCLUDE_MARKER) is True

    def test_preserves_function(self) -> None:
        """Test that decoration preserves the original function."""

        @mcp_exclude
        def helper(x: int) -> int:
            return x * 2

        assert helper(5) == 10


class TestMcpResource:
    """Tests for mcp_resource decorator."""

    def test_basic_decoration(self) -> None:
        """Test basic resource decoration."""

        @mcp_resource(uri="data://test/{id}")
        def get_data(id: str) -> str:
            return f"Data for {id}"

        assert hasattr(get_data, MCP_RESOURCE_MARKER)
        meta = getattr(get_data, MCP_RESOURCE_MARKER)
        assert meta["uri"] == "data://test/{id}"

    def test_with_all_options(self) -> None:
        """Test resource decoration with all options."""

        @mcp_resource(
            uri="file://docs/{name}",
            name="document_reader",
            description="Reads documents",
            mime_type="text/plain",
        )
        def read_doc(name: str) -> str:
            return f"Content of {name}"

        meta = getattr(read_doc, MCP_RESOURCE_MARKER)
        assert meta["uri"] == "file://docs/{name}"
        assert meta["name"] == "document_reader"
        assert meta["description"] == "Reads documents"
        assert meta["mime_type"] == "text/plain"


class TestMcpPrompt:
    """Tests for mcp_prompt decorator."""

    def test_basic_decoration(self) -> None:
        """Test basic prompt decoration."""

        @mcp_prompt()
        def greeting(name: str) -> str:
            return f"Greet {name}"

        assert hasattr(greeting, MCP_PROMPT_MARKER)

    def test_with_options(self) -> None:
        """Test prompt decoration with options."""

        @mcp_prompt(name="custom_greeting", description="A greeting prompt")
        def greeting(name: str) -> str:
            return f"Greet {name}"

        meta = getattr(greeting, MCP_PROMPT_MARKER)
        assert meta["name"] == "custom_greeting"
        assert meta["description"] == "A greeting prompt"


class TestGetMcpMetadata:
    """Tests for get_mcp_metadata function."""

    def test_tool_metadata(self) -> None:
        """Test getting metadata from tool-decorated function."""

        @mcp_tool(name="test", description="Test tool")
        def my_tool() -> None:
            pass

        meta = get_mcp_metadata(my_tool)
        assert meta["is_tool"] is True
        assert meta["is_excluded"] is False
        assert meta["is_resource"] is False
        assert meta["is_prompt"] is False
        assert meta["tool_meta"]["name"] == "test"

    def test_excluded_metadata(self) -> None:
        """Test getting metadata from excluded function."""

        @mcp_exclude
        def excluded_func() -> None:
            pass

        meta = get_mcp_metadata(excluded_func)
        assert meta["is_excluded"] is True
        assert meta["is_tool"] is False

    def test_undecorated_function(self) -> None:
        """Test getting metadata from undecorated function."""

        def plain_func() -> None:
            pass

        meta = get_mcp_metadata(plain_func)
        assert meta["is_tool"] is False
        assert meta["is_excluded"] is False
        assert meta["is_resource"] is False
        assert meta["is_prompt"] is False
        assert meta["tool_meta"] is None
