"""Tests for CLI interface."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_mcp.cli import cli, load_module_from_path, load_modules


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_module_file(tmp_path: Path) -> Path:
    """Create a sample Python module file."""
    module_path = tmp_path / "sample.py"
    module_path.write_text('''"""Sample module for testing."""

def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

def multiply(x: float, y: float) -> float:
    """Multiply two numbers."""
    return x * y

def _private_func() -> None:
    """Private function."""
    pass
''')
    return module_path


@pytest.fixture
def decorated_module_file(tmp_path: Path) -> Path:
    """Create a module with decorators."""
    module_path = tmp_path / "decorated.py"
    module_path.write_text('''"""Decorated module for testing."""

from auto_mcp import mcp_tool, mcp_resource, mcp_prompt, mcp_exclude

@mcp_tool(name="custom_add", description="Add numbers with custom name")
def add_tool(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

@mcp_resource(uri="data://{id}", name="data_resource")
def get_data(id: str) -> str:
    """Get data by ID."""
    return f"data-{id}"

@mcp_prompt(name="greeting")
def greeting_prompt(name: str) -> str:
    """Generate greeting."""
    return f"Hello, {name}!"

@mcp_exclude
def excluded_func() -> None:
    """This should be excluded."""
    pass
''')
    return module_path


class TestLoadModuleFromPath:
    """Tests for load_module_from_path function."""

    def test_load_valid_module(self, sample_module_file: Path) -> None:
        """Test loading a valid Python module."""
        module = load_module_from_path(sample_module_file)

        assert module is not None
        assert module.__name__ == "sample"
        assert hasattr(module, "add")
        assert hasattr(module, "multiply")

    def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        """Test loading a non-existent file raises error."""
        from click import ClickException

        with pytest.raises(ClickException, match="Module not found"):
            load_module_from_path(tmp_path / "nonexistent.py")

    def test_load_non_python_file(self, tmp_path: Path) -> None:
        """Test loading a non-Python file raises error."""
        from click import ClickException

        txt_file = tmp_path / "file.txt"
        txt_file.write_text("not python")

        with pytest.raises(ClickException, match="Not a Python file"):
            load_module_from_path(txt_file)

    def test_load_module_with_syntax_error(self, tmp_path: Path) -> None:
        """Test loading a module with syntax error raises error."""
        from click import ClickException

        bad_module = tmp_path / "bad.py"
        bad_module.write_text("def broken(:\n    pass")

        with pytest.raises(ClickException, match="Error loading module"):
            load_module_from_path(bad_module)


class TestLoadModules:
    """Tests for load_modules function."""

    def test_load_multiple_modules(
        self, sample_module_file: Path, decorated_module_file: Path
    ) -> None:
        """Test loading multiple modules."""
        modules = load_modules(
            (str(sample_module_file), str(decorated_module_file))
        )

        assert len(modules) == 2


class TestCliMain:
    """Tests for main CLI group."""

    def test_help(self, runner: CliRunner) -> None:
        """Test --help option."""
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "auto-mcp" in result.output
        assert "generate" in result.output
        assert "serve" in result.output
        assert "check" in result.output
        assert "cache" in result.output
        assert "config" in result.output

    def test_version(self, runner: CliRunner) -> None:
        """Test --version option."""
        result = runner.invoke(cli, ["--version"])

        assert result.exit_code == 0
        assert "auto-mcp" in result.output or "version" in result.output.lower()


class TestCheckCommand:
    """Tests for check command."""

    def test_check_module(self, runner: CliRunner, sample_module_file: Path) -> None:
        """Test checking a module."""
        result = runner.invoke(cli, ["check", str(sample_module_file)])

        assert result.exit_code == 0
        assert "sample" in result.output
        assert "add" in result.output
        assert "multiply" in result.output

    def test_check_module_verbose(
        self, runner: CliRunner, sample_module_file: Path
    ) -> None:
        """Test checking a module with verbose output."""
        result = runner.invoke(cli, ["check", str(sample_module_file), "-v"])

        assert result.exit_code == 0
        assert "Docstring" in result.output or "Add two numbers" in result.output

    def test_check_includes_decorators(
        self, runner: CliRunner, decorated_module_file: Path
    ) -> None:
        """Test that check shows decorated methods."""
        result = runner.invoke(cli, ["check", str(decorated_module_file)])

        assert result.exit_code == 0
        # Should show custom tool name
        assert "custom_add" in result.output
        # Should show resource
        assert "data_resource" in result.output or "Resources" in result.output

    def test_check_summary(self, runner: CliRunner, sample_module_file: Path) -> None:
        """Test check shows summary."""
        result = runner.invoke(cli, ["check", str(sample_module_file)])

        assert result.exit_code == 0
        assert "Summary" in result.output
        assert "tool" in result.output.lower()


class TestGenerateCommand:
    """Tests for generate command."""

    def test_generate_standalone(
        self, runner: CliRunner, sample_module_file: Path, tmp_path: Path
    ) -> None:
        """Test generating a standalone server."""
        output_file = tmp_path / "server.py"

        result = runner.invoke(
            cli,
            [
                "generate",
                str(sample_module_file),
                "-o",
                str(output_file),
                "--no-llm",
            ],
        )

        assert result.exit_code == 0
        assert output_file.exists()

        content = output_file.read_text()
        assert "FastMCP" in content
        assert "@mcp.tool" in content

    def test_generate_with_custom_name(
        self, runner: CliRunner, sample_module_file: Path, tmp_path: Path
    ) -> None:
        """Test generating with custom server name."""
        output_file = tmp_path / "server.py"

        result = runner.invoke(
            cli,
            [
                "generate",
                str(sample_module_file),
                "-o",
                str(output_file),
                "--name",
                "my-custom-server",
                "--no-llm",
            ],
        )

        assert result.exit_code == 0

        content = output_file.read_text()
        assert "my-custom-server" in content


class TestCacheCommands:
    """Tests for cache subcommands."""

    def test_cache_stats(self, runner: CliRunner) -> None:
        """Test cache stats command."""
        result = runner.invoke(cli, ["cache", "stats"])

        assert result.exit_code == 0
        assert "Hits" in result.output
        assert "Misses" in result.output

    def test_cache_clear_all(self, runner: CliRunner) -> None:
        """Test cache clear --all command."""
        result = runner.invoke(cli, ["cache", "clear", "--all"])

        assert result.exit_code == 0
        assert "Cleared" in result.output

    def test_cache_clear_module(
        self, runner: CliRunner, sample_module_file: Path
    ) -> None:
        """Test cache clear for specific module."""
        result = runner.invoke(cli, ["cache", "clear", str(sample_module_file)])

        assert result.exit_code == 0

    def test_cache_clear_no_args(self, runner: CliRunner) -> None:
        """Test cache clear without arguments raises error."""
        result = runner.invoke(cli, ["cache", "clear"])

        assert result.exit_code != 0
        assert "Specify modules" in result.output or "Error" in result.output


class TestConfigCommands:
    """Tests for config subcommands."""

    def test_config_show(self, runner: CliRunner) -> None:
        """Test config show command."""
        result = runner.invoke(cli, ["config", "show"])

        assert result.exit_code == 0
        assert "LLM Provider" in result.output
        assert "LLM Model" in result.output
        assert "Cache" in result.output

    def test_config_env(self, runner: CliRunner) -> None:
        """Test config env command."""
        result = runner.invoke(cli, ["config", "env"])

        assert result.exit_code == 0
        assert "AUTO_MCP_LLM_PROVIDER" in result.output
        assert "AUTO_MCP_LLM_MODEL" in result.output


class TestServeCommand:
    """Tests for serve command (limited testing due to blocking nature)."""

    def test_serve_help(self, runner: CliRunner) -> None:
        """Test serve --help."""
        result = runner.invoke(cli, ["serve", "--help"])

        assert result.exit_code == 0
        assert "MODULES" in result.output
        assert "--name" in result.output
        assert "--transport" in result.output


class TestCliOptions:
    """Tests for CLI option handling."""

    def test_generate_no_resources(
        self, runner: CliRunner, sample_module_file: Path, tmp_path: Path
    ) -> None:
        """Test --no-resources option."""
        output_file = tmp_path / "server.py"

        result = runner.invoke(
            cli,
            [
                "generate",
                str(sample_module_file),
                "-o",
                str(output_file),
                "--no-llm",
                "--no-resources",
            ],
        )

        assert result.exit_code == 0

    def test_generate_no_prompts(
        self, runner: CliRunner, sample_module_file: Path, tmp_path: Path
    ) -> None:
        """Test --no-prompts option."""
        output_file = tmp_path / "server.py"

        result = runner.invoke(
            cli,
            [
                "generate",
                str(sample_module_file),
                "-o",
                str(output_file),
                "--no-llm",
                "--no-prompts",
            ],
        )

        assert result.exit_code == 0

    def test_generate_include_private(
        self, runner: CliRunner, sample_module_file: Path, tmp_path: Path
    ) -> None:
        """Test --include-private option."""
        output_file = tmp_path / "server.py"

        result = runner.invoke(
            cli,
            [
                "generate",
                str(sample_module_file),
                "-o",
                str(output_file),
                "--no-llm",
                "--include-private",
            ],
        )

        assert result.exit_code == 0


class TestCliErrorHandling:
    """Tests for CLI error handling."""

    def test_generate_missing_module(self, runner: CliRunner) -> None:
        """Test error when module doesn't exist."""
        result = runner.invoke(cli, ["generate", "nonexistent.py"])

        assert result.exit_code != 0

    def test_check_missing_module(self, runner: CliRunner) -> None:
        """Test error when module doesn't exist for check."""
        result = runner.invoke(cli, ["check", "nonexistent.py"])

        assert result.exit_code != 0
