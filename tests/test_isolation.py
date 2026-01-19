"""Tests for the isolation modules."""

from __future__ import annotations

import json
import subprocess
import sys
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from auto_mcp.isolation.manager import (
    IsolationConfig,
    IsolationError,
    IsolationManager,
    PackageNotFoundError,
    check_auto_mcp_on_pypi,
    check_uvx_available,
    get_auto_mcp_source_dir,
    is_development_install,
    is_package_installed,
    parse_package_spec,
)
from auto_mcp.isolation.worker import (
    _output_result,
    worker_check,
    worker_generate,
    worker_serve,
)


# ============================================================================
# Tests for isolation/manager.py
# ============================================================================


class TestIsolationExceptions:
    """Test isolation exception classes."""

    def test_isolation_error_is_exception(self) -> None:
        """IsolationError should be an Exception."""
        err = IsolationError("test error")
        assert isinstance(err, Exception)
        assert str(err) == "test error"

    def test_package_not_found_error_is_isolation_error(self) -> None:
        """PackageNotFoundError should be a subclass of IsolationError."""
        err = PackageNotFoundError("package not found")
        assert isinstance(err, IsolationError)
        assert isinstance(err, Exception)
        assert str(err) == "package not found"


class TestGetAutoMcpSourceDir:
    """Tests for get_auto_mcp_source_dir function."""

    def test_returns_path_or_none(self) -> None:
        """Should return a Path or None."""
        result = get_auto_mcp_source_dir()
        assert result is None or isinstance(result, Path)

    def test_returns_path_for_editable_install(self) -> None:
        """Should return project root for editable installation."""
        result = get_auto_mcp_source_dir()
        if result is not None:
            # If we're in an editable install, the pyproject.toml should exist
            assert (result / "pyproject.toml").exists()

    @patch("auto_mcp.isolation.manager.Path")
    def test_returns_none_on_exception(self, mock_path: MagicMock) -> None:
        """Should return None if any exception occurs."""
        mock_path.side_effect = Exception("some error")
        # The function catches all exceptions internally
        # Since the import happens before our mock, we need a different approach
        with patch.dict("sys.modules", {"auto_mcp": None}):
            result = get_auto_mcp_source_dir()
            assert result is None


class TestIsDevelopmentInstall:
    """Tests for is_development_install function."""

    def test_returns_boolean(self) -> None:
        """Should return a boolean value."""
        result = is_development_install()
        assert isinstance(result, bool)

    @patch("auto_mcp.isolation.manager.get_auto_mcp_source_dir")
    def test_returns_true_when_source_dir_found(self, mock_get_source: MagicMock) -> None:
        """Should return True when source dir is found."""
        mock_get_source.return_value = Path("/some/path")
        assert is_development_install() is True

    @patch("auto_mcp.isolation.manager.get_auto_mcp_source_dir")
    def test_returns_false_when_source_dir_none(self, mock_get_source: MagicMock) -> None:
        """Should return False when source dir is None."""
        mock_get_source.return_value = None
        assert is_development_install() is False


class TestCheckUvxAvailable:
    """Tests for check_uvx_available function."""

    def test_returns_boolean(self) -> None:
        """Should return a boolean value."""
        result = check_uvx_available()
        assert isinstance(result, bool)

    @patch("shutil.which")
    def test_returns_true_when_uvx_found(self, mock_which: MagicMock) -> None:
        """Should return True when uvx is in PATH."""
        mock_which.return_value = "/usr/local/bin/uvx"
        assert check_uvx_available() is True
        mock_which.assert_called_once_with("uvx")

    @patch("shutil.which")
    def test_returns_false_when_uvx_not_found(self, mock_which: MagicMock) -> None:
        """Should return False when uvx is not in PATH."""
        mock_which.return_value = None
        assert check_uvx_available() is False


class TestCheckAutoMcpOnPypi:
    """Tests for check_auto_mcp_on_pypi function."""

    @patch("subprocess.run")
    def test_returns_true_when_uvx_works(self, mock_run: MagicMock) -> None:
        """Should return True when uvx help works."""
        mock_run.return_value = MagicMock(returncode=0)
        assert check_auto_mcp_on_pypi() is True

    @patch("subprocess.run")
    def test_returns_false_when_uvx_fails(self, mock_run: MagicMock) -> None:
        """Should return False when uvx returns non-zero."""
        mock_run.return_value = MagicMock(returncode=1)
        assert check_auto_mcp_on_pypi() is False

    @patch("subprocess.run")
    def test_returns_false_on_exception(self, mock_run: MagicMock) -> None:
        """Should return False on any exception."""
        mock_run.side_effect = Exception("error")
        assert check_auto_mcp_on_pypi() is False

    @patch("subprocess.run")
    def test_returns_false_on_timeout(self, mock_run: MagicMock) -> None:
        """Should return False on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="uvx", timeout=5)
        assert check_auto_mcp_on_pypi() is False


class TestIsPackageInstalled:
    """Tests for is_package_installed function."""

    def test_returns_true_for_installed_package(self) -> None:
        """Should return True for an installed package."""
        # pytest is definitely installed since we're running tests
        assert is_package_installed("pytest") is True

    def test_returns_false_for_nonexistent_package(self) -> None:
        """Should return False for a non-existent package."""
        assert is_package_installed("nonexistent_package_xyz_123") is False

    def test_strips_version_specifiers(self) -> None:
        """Should strip version specifiers before checking."""
        assert is_package_installed("pytest==8.0.0") is True
        assert is_package_installed("pytest>=7.0.0") is True
        assert is_package_installed("pytest<=9.0.0") is True
        assert is_package_installed("pytest<10.0.0") is True
        assert is_package_installed("pytest>6.0.0") is True

    def test_strips_extras(self) -> None:
        """Should strip extras before checking."""
        assert is_package_installed("pytest[extra]") is True


class TestParsePackageSpec:
    """Tests for parse_package_spec function."""

    def test_simple_package_name(self) -> None:
        """Should parse simple package name."""
        name, version = parse_package_spec("requests")
        assert name == "requests"
        assert version is None

    def test_package_with_exact_version(self) -> None:
        """Should parse package with exact version."""
        name, version = parse_package_spec("requests==2.28.0")
        assert name == "requests"
        assert version == "==2.28.0"

    def test_package_with_gte_version(self) -> None:
        """Should parse package with >= version."""
        name, version = parse_package_spec("requests>=2.28.0")
        assert name == "requests"
        assert version == ">=2.28.0"

    def test_package_with_lte_version(self) -> None:
        """Should parse package with <= version."""
        name, version = parse_package_spec("requests<=2.28.0")
        assert name == "requests"
        assert version == "<=2.28.0"

    def test_package_with_gt_version(self) -> None:
        """Should parse package with > version."""
        name, version = parse_package_spec("requests>2.0.0")
        assert name == "requests"
        assert version == ">2.0.0"

    def test_package_with_lt_version(self) -> None:
        """Should parse package with < version."""
        name, version = parse_package_spec("requests<3.0.0")
        assert name == "requests"
        assert version == "<3.0.0"


class TestIsolationConfig:
    """Tests for IsolationConfig dataclass."""

    def test_default_values(self) -> None:
        """Should have correct default values."""
        config = IsolationConfig(package_name="requests")
        assert config.package_name == "requests"
        assert config.version is None
        assert config.max_depth is None
        assert config.include_private is False
        assert config.include_reexports is False
        assert config.include_patterns is None
        assert config.exclude_patterns is None
        assert config.public_api_only is False
        assert config.server_name is None
        assert config.output_path is None
        assert config.enable_sessions is False
        assert config.session_ttl == 3600
        assert config.max_sessions == 100
        assert config.transport == "stdio"
        assert config.host == "localhost"
        assert config.port == 8000

    def test_to_dict(self) -> None:
        """Should convert to dictionary correctly."""
        config = IsolationConfig(
            package_name="requests",
            version="==2.28.0",
            max_depth=3,
            include_private=True,
            server_name="my-server",
        )
        data = config.to_dict()

        assert data["package_name"] == "requests"
        assert data["version"] == "==2.28.0"
        assert data["max_depth"] == 3
        assert data["include_private"] is True
        assert data["server_name"] == "my-server"
        assert data["transport"] == "stdio"

    def test_from_dict(self) -> None:
        """Should create from dictionary correctly."""
        data = {
            "package_name": "requests",
            "version": ">=2.0.0",
            "max_depth": 5,
            "include_private": True,
            "include_reexports": True,
            "include_patterns": ["get_*"],
            "exclude_patterns": ["_*"],
            "public_api_only": True,
            "server_name": "test-server",
            "output_path": "/tmp/output.py",
            "enable_sessions": True,
            "session_ttl": 7200,
            "max_sessions": 50,
            "transport": "sse",
            "host": "0.0.0.0",
            "port": 9000,
        }
        config = IsolationConfig.from_dict(data)

        assert config.package_name == "requests"
        assert config.version == ">=2.0.0"
        assert config.max_depth == 5
        assert config.include_private is True
        assert config.include_reexports is True
        assert config.include_patterns == ["get_*"]
        assert config.exclude_patterns == ["_*"]
        assert config.public_api_only is True
        assert config.server_name == "test-server"
        assert config.output_path == "/tmp/output.py"
        assert config.enable_sessions is True
        assert config.session_ttl == 7200
        assert config.max_sessions == 50
        assert config.transport == "sse"
        assert config.host == "0.0.0.0"
        assert config.port == 9000

    def test_from_dict_with_minimal_data(self) -> None:
        """Should create from minimal dictionary with defaults."""
        data = {"package_name": "requests"}
        config = IsolationConfig.from_dict(data)

        assert config.package_name == "requests"
        assert config.version is None
        assert config.include_private is False
        assert config.transport == "stdio"

    def test_roundtrip(self) -> None:
        """Should survive to_dict/from_dict roundtrip."""
        original = IsolationConfig(
            package_name="requests",
            version="==2.28.0",
            max_depth=3,
            include_private=True,
            include_patterns=["get_*", "post_*"],
            server_name="my-server",
            enable_sessions=True,
        )
        data = original.to_dict()
        restored = IsolationConfig.from_dict(data)

        assert restored.package_name == original.package_name
        assert restored.version == original.version
        assert restored.max_depth == original.max_depth
        assert restored.include_private == original.include_private
        assert restored.include_patterns == original.include_patterns
        assert restored.server_name == original.server_name
        assert restored.enable_sessions == original.enable_sessions


class TestIsolationManager:
    """Tests for IsolationManager class."""

    def test_initialization_simple(self) -> None:
        """Should initialize with simple package name."""
        manager = IsolationManager("requests")
        assert manager.package_name == "requests"
        assert manager.version is None
        assert manager.force_local is False

    def test_initialization_with_embedded_version(self) -> None:
        """Should parse embedded version from package name."""
        manager = IsolationManager("requests==2.28.0")
        assert manager.package_name == "requests"
        assert manager.version == "==2.28.0"

    def test_initialization_with_explicit_version(self) -> None:
        """Explicit version should override embedded version."""
        manager = IsolationManager("requests==2.28.0", version="==3.0.0")
        assert manager.package_name == "requests"
        assert manager.version == "==3.0.0"

    def test_initialization_with_force_local(self) -> None:
        """Should respect force_local flag."""
        manager = IsolationManager("requests", force_local=True)
        assert manager.force_local is True

    def test_is_locally_installed(self) -> None:
        """Should check if package is locally installed."""
        manager = IsolationManager("pytest")
        assert manager.is_locally_installed() is True

        manager2 = IsolationManager("nonexistent_package_xyz")
        assert manager2.is_locally_installed() is False

    def test_should_use_isolation_with_force_local(self) -> None:
        """Should return False when force_local is True."""
        manager = IsolationManager("nonexistent_package", force_local=True)
        assert manager.should_use_isolation() is False

    def test_should_use_isolation_for_installed_package(self) -> None:
        """Should return False for locally installed package."""
        manager = IsolationManager("pytest")
        assert manager.should_use_isolation() is False

    def test_should_use_isolation_for_not_installed_package(self) -> None:
        """Should return True for package not locally installed."""
        manager = IsolationManager("nonexistent_package_xyz")
        assert manager.should_use_isolation() is True

    def test_get_package_spec_simple(self) -> None:
        """Should return simple package name."""
        manager = IsolationManager("requests")
        assert manager.get_package_spec() == "requests"

    def test_get_package_spec_with_version(self) -> None:
        """Should return package with version."""
        manager = IsolationManager("requests", version="2.28.0")
        assert manager.get_package_spec() == "requests==2.28.0"

    def test_get_package_spec_with_version_operator(self) -> None:
        """Should not duplicate operator in version."""
        manager = IsolationManager("requests", version=">=2.28.0")
        assert manager.get_package_spec() == "requests>=2.28.0"

    @patch("auto_mcp.isolation.manager.get_auto_mcp_source_dir")
    def test_build_uvx_command_production(self, mock_source: MagicMock) -> None:
        """Should build correct uvx command for production."""
        mock_source.return_value = None
        manager = IsolationManager("requests")
        config_json = '{"package_name": "requests"}'

        cmd = manager._build_uvx_command("check", config_json)

        assert cmd[0] == "uvx"
        assert "--from" in cmd
        assert "auto-mcp-tool" in cmd
        assert "--with" in cmd
        assert "requests" in cmd
        assert "internal-worker" in cmd
        assert "check" in cmd
        assert "--config" in cmd
        assert config_json in cmd

    @patch("auto_mcp.isolation.manager.get_auto_mcp_source_dir")
    def test_build_uvx_command_development(self, mock_source: MagicMock) -> None:
        """Should build correct uvx command for development install."""
        mock_source.return_value = Path("/home/user/auto-mcp")
        manager = IsolationManager("requests")
        config_json = '{"package_name": "requests"}'

        cmd = manager._build_uvx_command("check", config_json)

        assert "/home/user/auto-mcp" in cmd

    def test_build_uvx_command_with_extra_args(self) -> None:
        """Should include extra arguments in command."""
        manager = IsolationManager("requests")
        config_json = '{"package_name": "requests"}'

        cmd = manager._build_uvx_command("check", config_json, extra_args=["--verbose"])

        assert "--verbose" in cmd

    @patch("subprocess.run")
    def test_run_subprocess_success(self, mock_run: MagicMock) -> None:
        """Should return completed process on success."""
        mock_run.return_value = MagicMock(returncode=0, stdout="output", stderr="")
        manager = IsolationManager("requests")

        result = manager._run_subprocess(["uvx", "--help"])

        assert result.returncode == 0

    @patch("subprocess.run")
    def test_run_subprocess_timeout(self, mock_run: MagicMock) -> None:
        """Should raise IsolationError on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["uvx"], timeout=300)
        manager = IsolationManager("requests")

        with pytest.raises(IsolationError, match="timed out"):
            manager._run_subprocess(["uvx", "--help"])

    @patch("subprocess.run")
    def test_run_subprocess_uvx_not_found(self, mock_run: MagicMock) -> None:
        """Should raise IsolationError when uvx not found."""
        mock_run.side_effect = FileNotFoundError("uvx not found")
        manager = IsolationManager("requests")

        with pytest.raises(IsolationError, match="uvx is not available"):
            manager._run_subprocess(["uvx", "--help"])

    @patch("subprocess.run")
    def test_run_subprocess_worker_json_error(self, mock_run: MagicMock) -> None:
        """Should parse worker JSON error from stdout."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='{"success": false, "error": "Cannot import package"}',
            stderr="",
        )
        manager = IsolationManager("requests")

        with pytest.raises(IsolationError, match="Worker error: Cannot import package"):
            manager._run_subprocess(["uvx", "command"])

    @patch("subprocess.run")
    def test_run_subprocess_auto_mcp_not_found(self, mock_run: MagicMock) -> None:
        """Should raise IsolationError when auto-mcp-tool not on PyPI."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="auto-mcp-tool not found on PyPI",
        )
        manager = IsolationManager("requests")

        with pytest.raises(IsolationError, match="auto-mcp-tool is not available"):
            manager._run_subprocess(["uvx", "command"])

    @patch("subprocess.run")
    def test_run_subprocess_internal_worker_not_found(self, mock_run: MagicMock) -> None:
        """Should raise IsolationError when internal-worker command not found."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error: No such command 'internal-worker'",
        )
        manager = IsolationManager("requests")

        with pytest.raises(IsolationError, match="does not support isolated"):
            manager._run_subprocess(["uvx", "command"])

    @patch("subprocess.run")
    def test_run_subprocess_package_not_found(self, mock_run: MagicMock) -> None:
        """Should raise PackageNotFoundError when package not on PyPI."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="requests not found on PyPI",
        )
        manager = IsolationManager("requests")

        with pytest.raises(PackageNotFoundError, match="not found on PyPI"):
            manager._run_subprocess(["uvx", "command"])

    @patch("subprocess.run")
    def test_run_subprocess_version_not_found(self, mock_run: MagicMock) -> None:
        """Should raise IsolationError for unavailable version."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Could not find a version that satisfies",
        )
        manager = IsolationManager("requests", version="99.99.99")

        with pytest.raises(IsolationError, match="Version '99.99.99' not available"):
            manager._run_subprocess(["uvx", "command"])

    @patch("subprocess.run")
    def test_run_subprocess_network_error(self, mock_run: MagicMock) -> None:
        """Should raise IsolationError on network issues."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Connection refused",
        )
        manager = IsolationManager("requests")

        with pytest.raises(IsolationError, match="Network error"):
            manager._run_subprocess(["uvx", "command"])

    @patch("subprocess.run")
    def test_run_subprocess_generic_error(self, mock_run: MagicMock) -> None:
        """Should raise IsolationError with details for generic failures."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Some unexpected error",
        )
        manager = IsolationManager("requests")

        with pytest.raises(IsolationError, match="Some unexpected error"):
            manager._run_subprocess(["uvx", "command"])

    @patch.object(IsolationManager, "_run_subprocess")
    def test_run_check_success(self, mock_run: MagicMock) -> None:
        """Should return PackageMetadata on successful check."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps({
                "success": True,
                "metadata": {
                    "name": "requests",
                    "version": "2.28.0",
                    "functions": [],
                    "classes": [],
                    "resources": [],
                    "prompts": [],
                },
            }),
            stderr="",
        )
        manager = IsolationManager("requests")
        config = IsolationConfig(package_name="requests")

        result = manager.run_check(config)

        assert result.name == "requests"

    @patch.object(IsolationManager, "_run_subprocess")
    def test_run_check_invalid_json(self, mock_run: MagicMock) -> None:
        """Should raise IsolationError on invalid JSON output."""
        mock_run.return_value = MagicMock(stdout="not json", stderr="")
        manager = IsolationManager("requests")
        config = IsolationConfig(package_name="requests")

        with pytest.raises(IsolationError, match="invalid output"):
            manager.run_check(config)

    @patch.object(IsolationManager, "_run_subprocess")
    def test_run_check_worker_failure(self, mock_run: MagicMock) -> None:
        """Should raise IsolationError on worker failure."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"success": False, "error": "Import failed"}),
            stderr="",
        )
        manager = IsolationManager("requests")
        config = IsolationConfig(package_name="requests")

        with pytest.raises(IsolationError, match="Import failed"):
            manager.run_check(config)

    @patch.object(IsolationManager, "_run_subprocess")
    def test_run_generate_success(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Should return output path on successful generate."""
        output_file = tmp_path / "server.py"
        mock_run.return_value = MagicMock(
            stdout=json.dumps({
                "success": True,
                "output_path": str(output_file),
                "server_name": "requests-mcp-server",
            }),
            stderr="",
        )
        manager = IsolationManager("requests")
        config = IsolationConfig(package_name="requests")

        result = manager.run_generate(config, output_file)

        assert result == output_file

    @patch.object(IsolationManager, "_run_subprocess")
    def test_run_generate_invalid_json(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Should raise IsolationError on invalid JSON output."""
        mock_run.return_value = MagicMock(stdout="not json", stderr="error")
        manager = IsolationManager("requests")
        config = IsolationConfig(package_name="requests")

        with pytest.raises(IsolationError, match="invalid output"):
            manager.run_generate(config, tmp_path / "server.py")

    @patch("os.execvp")
    def test_run_serve_calls_execvp(self, mock_exec: MagicMock) -> None:
        """Should call os.execvp to replace process."""
        manager = IsolationManager("requests")
        config = IsolationConfig(package_name="requests")

        manager.run_serve(config)

        mock_exec.assert_called_once()
        args = mock_exec.call_args[0]
        assert args[0] == "uvx"
        assert "uvx" in args[1]

    @patch("subprocess.Popen")
    def test_run_serve_subprocess(self, mock_popen: MagicMock) -> None:
        """Should create Popen process for serve subprocess."""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        manager = IsolationManager("requests")
        config = IsolationConfig(package_name="requests")

        result = manager.run_serve_subprocess(config)

        assert result == mock_process
        mock_popen.assert_called_once()


# ============================================================================
# Tests for isolation/worker.py
# ============================================================================


class TestOutputResult:
    """Tests for _output_result function."""

    def test_success_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should output success JSON."""
        _output_result(success=True)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["success"] is True

    def test_success_with_data(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should include data in output."""
        _output_result(success=True, data={"key": "value"})
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["success"] is True
        assert result["key"] == "value"

    def test_failure_with_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should include error in failure output."""
        _output_result(success=False, error="Something went wrong")
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["success"] is False
        assert result["error"] == "Something went wrong"

    def test_output_is_flushed(self) -> None:
        """Should flush output immediately."""
        # This test verifies the flush=True behavior indirectly
        # by ensuring output appears immediately
        import io
        original_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            _output_result(success=True)
            output = sys.stdout.getvalue()
            assert len(output) > 0
        finally:
            sys.stdout = original_stdout


class TestWorkerCheck:
    """Tests for worker_check function."""

    @patch("auto_mcp.isolation.worker.PackageAnalyzer")
    def test_success(
        self,
        mock_analyzer_class: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Should output success with metadata."""
        mock_metadata = MagicMock()
        mock_metadata.to_dict.return_value = {
            "name": "requests",
            "version": "2.28.0",
            "functions": [],
            "classes": [],
            "resources": [],
            "prompts": [],
        }
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_package.return_value = mock_metadata
        mock_analyzer_class.return_value = mock_analyzer

        config = IsolationConfig(package_name="requests")
        config_json = json.dumps(config.to_dict())

        worker_check(config_json)

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["success"] is True
        assert "metadata" in result

    @patch("auto_mcp.isolation.worker.PackageAnalyzer")
    def test_import_error(
        self,
        mock_analyzer_class: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Should output error on import failure."""
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_package.side_effect = ImportError("Cannot import module")
        mock_analyzer_class.return_value = mock_analyzer

        config = IsolationConfig(package_name="nonexistent")
        config_json = json.dumps(config.to_dict())

        with pytest.raises(SystemExit) as exc_info:
            worker_check(config_json)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["success"] is False
        assert "Cannot import" in result["error"]

    @patch("auto_mcp.isolation.worker.PackageAnalyzer")
    def test_generic_error(
        self,
        mock_analyzer_class: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Should output error on generic exception."""
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_package.side_effect = ValueError("Something went wrong")
        mock_analyzer_class.return_value = mock_analyzer

        config = IsolationConfig(package_name="requests")
        config_json = json.dumps(config.to_dict())

        with pytest.raises(SystemExit) as exc_info:
            worker_check(config_json)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["success"] is False
        assert "Something went wrong" in result["error"]


class TestWorkerGenerate:
    """Tests for worker_generate function."""

    def test_missing_output_path(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should fail when output_path is missing."""
        config = IsolationConfig(package_name="requests")
        config_json = json.dumps(config.to_dict())

        with pytest.raises(SystemExit) as exc_info:
            worker_generate(config_json)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["success"] is False
        assert "output_path is required" in result["error"]

    @patch("auto_mcp.core.generator.MCPGenerator")
    def test_success(
        self,
        mock_generator_class: MagicMock,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Should output success with output path."""
        output_file = tmp_path / "server.py"
        mock_generator = MagicMock()
        mock_generator.generate_standalone_from_package.return_value = output_file
        mock_generator_class.return_value = mock_generator

        config = IsolationConfig(
            package_name="requests",
            output_path=str(output_file),
        )
        config_json = json.dumps(config.to_dict())

        worker_generate(config_json)

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["success"] is True
        assert result["output_path"] == str(output_file)

    @patch("auto_mcp.core.generator.MCPGenerator")
    def test_import_error(
        self,
        mock_generator_class: MagicMock,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Should output error on import failure."""
        mock_generator = MagicMock()
        mock_generator.generate_standalone_from_package.side_effect = ImportError("Cannot import")
        mock_generator_class.return_value = mock_generator

        config = IsolationConfig(
            package_name="nonexistent",
            output_path=str(tmp_path / "server.py"),
        )
        config_json = json.dumps(config.to_dict())

        with pytest.raises(SystemExit) as exc_info:
            worker_generate(config_json)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["success"] is False

    @patch("auto_mcp.core.generator.MCPGenerator")
    def test_uses_config_options(
        self,
        mock_generator_class: MagicMock,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Should pass config options to generator."""
        output_file = tmp_path / "server.py"
        mock_generator = MagicMock()
        mock_generator.generate_standalone_from_package.return_value = output_file
        mock_generator_class.return_value = mock_generator

        config = IsolationConfig(
            package_name="requests",
            output_path=str(output_file),
            server_name="my-custom-server",
            include_private=True,
            max_depth=3,
            enable_sessions=True,
        )
        config_json = json.dumps(config.to_dict())

        worker_generate(config_json)

        # Verify generator was created with correct config
        call_args = mock_generator_class.call_args
        gen_config = call_args.kwargs["config"]
        assert gen_config.server_name == "my-custom-server"
        assert gen_config.include_private is True
        assert gen_config.max_depth == 3
        assert gen_config.enable_sessions is True


class TestWorkerServe:
    """Tests for worker_serve function."""

    @patch("auto_mcp.core.generator.MCPGenerator")
    def test_success(self, mock_generator_class: MagicMock) -> None:
        """Should create and run server."""
        mock_server = MagicMock()
        mock_generator = MagicMock()
        mock_generator.create_server_from_package.return_value = mock_server
        mock_generator_class.return_value = mock_generator

        config = IsolationConfig(package_name="requests")
        config_json = json.dumps(config.to_dict())

        worker_serve(config_json)

        mock_server.run.assert_called_once_with(transport="stdio")

    @patch("auto_mcp.core.generator.MCPGenerator")
    def test_import_error(
        self,
        mock_generator_class: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Should print error to stderr on import failure."""
        mock_generator = MagicMock()
        mock_generator.create_server_from_package.side_effect = ImportError("Cannot import")
        mock_generator_class.return_value = mock_generator

        config = IsolationConfig(package_name="nonexistent")
        config_json = json.dumps(config.to_dict())

        with pytest.raises(SystemExit) as exc_info:
            worker_serve(config_json)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Cannot import" in captured.err

    @patch("auto_mcp.core.generator.MCPGenerator")
    def test_generic_error(
        self,
        mock_generator_class: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Should print error to stderr on generic exception."""
        mock_generator = MagicMock()
        mock_generator.create_server_from_package.side_effect = RuntimeError("Server failed")
        mock_generator_class.return_value = mock_generator

        config = IsolationConfig(package_name="requests")
        config_json = json.dumps(config.to_dict())

        with pytest.raises(SystemExit) as exc_info:
            worker_serve(config_json)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Server failed" in captured.err

    @patch("auto_mcp.core.generator.MCPGenerator")
    def test_uses_transport_from_config(self, mock_generator_class: MagicMock) -> None:
        """Should use transport from config."""
        mock_server = MagicMock()
        mock_generator = MagicMock()
        mock_generator.create_server_from_package.return_value = mock_server
        mock_generator_class.return_value = mock_generator

        config = IsolationConfig(package_name="requests", transport="sse")
        config_json = json.dumps(config.to_dict())

        worker_serve(config_json)

        mock_server.run.assert_called_once_with(transport="sse")
