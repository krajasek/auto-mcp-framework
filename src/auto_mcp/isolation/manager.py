"""Isolation manager for running package analysis in uvx subprocess."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from auto_mcp.core.package import PackageMetadata


class IsolationError(Exception):
    """Error during isolated execution."""

    pass


class PackageNotFoundError(IsolationError):
    """Package not found on PyPI."""

    pass


def get_auto_mcp_source_dir() -> Path | None:
    """Get the source directory if running from a development installation.

    Returns:
        Path to the project root if running from editable install, None otherwise.
    """
    try:
        import auto_mcp

        # Check if this is an editable installation by looking for pyproject.toml
        # next to the package
        package_dir = Path(auto_mcp.__file__).parent
        # Editable installs: src/auto_mcp/__init__.py -> project root is ../..
        project_root = package_dir.parent.parent
        pyproject = project_root / "pyproject.toml"

        if pyproject.exists():
            # Verify it's actually the auto-mcp project
            content = pyproject.read_text()
            if 'name = "auto-mcp-tool"' in content or "name = 'auto-mcp-tool'" in content:
                return project_root

        return None
    except Exception:
        return None


def is_development_install() -> bool:
    """Check if auto-mcp is running from a development/editable installation.

    Returns:
        True if running from source, False if installed from PyPI.
    """
    return get_auto_mcp_source_dir() is not None


def check_uvx_available() -> bool:
    """Check if uvx is available in PATH.

    Returns:
        True if uvx is available, False otherwise.
    """
    return shutil.which("uvx") is not None


def check_auto_mcp_on_pypi() -> bool:
    """Check if auto-mcp is available on PyPI.

    This is a quick check to avoid confusing errors when the package
    isn't published yet.

    Returns:
        True if auto-mcp appears to be on PyPI, False otherwise.
    """
    try:
        result = subprocess.run(
            ["uvx", "--help"],  # Just check uvx works
            capture_output=True,
            text=True,
            timeout=5,
        )
        # For now, assume it's available if uvx works
        # A full PyPI check would require network access
        return result.returncode == 0
    except Exception:
        return False


def is_package_installed(package_name: str) -> bool:
    """Check if a package is installed in the current environment.

    Args:
        package_name: Package name (may include version specifier)

    Returns:
        True if installed, False otherwise.
    """
    # Strip version specifier if present
    base_name = package_name.split("==")[0].split(">=")[0].split("<=")[0].split("<")[0].split(">")[0].split("[")[0]

    spec = importlib.util.find_spec(base_name)
    return spec is not None


def parse_package_spec(package_spec: str) -> tuple[str, str | None]:
    """Parse a package specification into name and version.

    Args:
        package_spec: Package spec like 'requests', 'requests==2.28.0'

    Returns:
        Tuple of (package_name, version_or_none)
    """
    # Handle various version specifiers
    for sep in ("==", ">=", "<=", ">", "<"):
        if sep in package_spec:
            parts = package_spec.split(sep, 1)
            return parts[0], sep + parts[1]

    return package_spec, None


@dataclass
class IsolationConfig:
    """Configuration for isolated execution."""

    package_name: str
    version: str | None = None
    max_depth: int | None = None
    include_private: bool = False
    include_reexports: bool = False
    include_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None
    public_api_only: bool = False

    # For generate command
    server_name: str | None = None
    output_path: str | None = None
    enable_sessions: bool = False
    session_ttl: int = 3600
    max_sessions: int = 100

    # For serve command
    transport: str = "stdio"
    host: str = "localhost"
    port: int = 8000

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "package_name": self.package_name,
            "version": self.version,
            "max_depth": self.max_depth,
            "include_private": self.include_private,
            "include_reexports": self.include_reexports,
            "include_patterns": self.include_patterns,
            "exclude_patterns": self.exclude_patterns,
            "public_api_only": self.public_api_only,
            "server_name": self.server_name,
            "output_path": self.output_path,
            "enable_sessions": self.enable_sessions,
            "session_ttl": self.session_ttl,
            "max_sessions": self.max_sessions,
            "transport": self.transport,
            "host": self.host,
            "port": self.port,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IsolationConfig":
        """Create from dictionary."""
        return cls(
            package_name=data["package_name"],
            version=data.get("version"),
            max_depth=data.get("max_depth"),
            include_private=data.get("include_private", False),
            include_reexports=data.get("include_reexports", False),
            include_patterns=data.get("include_patterns"),
            exclude_patterns=data.get("exclude_patterns"),
            public_api_only=data.get("public_api_only", False),
            server_name=data.get("server_name"),
            output_path=data.get("output_path"),
            enable_sessions=data.get("enable_sessions", False),
            session_ttl=data.get("session_ttl", 3600),
            max_sessions=data.get("max_sessions", 100),
            transport=data.get("transport", "stdio"),
            host=data.get("host", "localhost"),
            port=data.get("port", 8000),
        )


class IsolationManager:
    """Manages isolated execution of package analysis via uvx."""

    # Timeout for check/generate operations (5 minutes)
    DEFAULT_TIMEOUT = 300

    def __init__(
        self,
        package_name: str,
        version: str | None = None,
        force_local: bool = False,
    ) -> None:
        """Initialize the isolation manager.

        Args:
            package_name: Name of the package (e.g., 'requests', 'requests==2.28.0')
            version: Optional version specification (overrides version in package_name)
            force_local: If True, fail if not installed locally (--no-isolated)
        """
        # Parse package name for embedded version
        base_name, embedded_version = parse_package_spec(package_name)
        self.package_name = base_name
        self.version = version or embedded_version
        self.force_local = force_local

    def is_locally_installed(self) -> bool:
        """Check if the package is installed in the current environment."""
        return is_package_installed(self.package_name)

    def should_use_isolation(self) -> bool:
        """Determine if uvx isolation should be used.

        Returns:
            True if package is not locally installed and not force_local.
        """
        if self.force_local:
            return False
        return not self.is_locally_installed()

    def get_package_spec(self) -> str:
        """Get the full package specification for uvx.

        Returns:
            Package spec like 'requests' or 'requests==2.28.0'
        """
        if self.version:
            # Handle version that already includes operator
            if self.version.startswith(("==", ">=", "<=", ">", "<")):
                return f"{self.package_name}{self.version}"
            return f"{self.package_name}=={self.version}"
        return self.package_name

    def _build_uvx_command(self, worker_cmd: str, config_json: str, extra_args: list[str] | None = None) -> list[str]:
        """Build the uvx command for subprocess execution.

        Args:
            worker_cmd: The worker command (check, generate, serve)
            config_json: JSON-encoded configuration
            extra_args: Additional arguments to pass

        Returns:
            List of command arguments for subprocess

        Note:
            The command structure is:
            uvx --from auto-mcp --with <package> auto-mcp internal-worker <cmd> --config <json>

            - --from auto-mcp: specifies the tool to run (or path for dev installs)
            - --with <package>: adds the package to analyze as a dependency

            For development installations, we use --from <path> to use the local source.
        """
        # Determine the source for auto-mcp
        source_dir = get_auto_mcp_source_dir()
        if source_dir:
            # Development mode: use local source
            auto_mcp_source = str(source_dir)
        else:
            # Production mode: use PyPI
            auto_mcp_source = "auto-mcp-tool"

        cmd = [
            "uvx",
            "--from", auto_mcp_source,
            "--with", self.get_package_spec(),
            "auto-mcp-tool",
            "internal-worker",
            worker_cmd,
            "--config", config_json,
        ]

        if extra_args:
            cmd.extend(extra_args)

        return cmd

    def _run_subprocess(self, cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
        """Run a subprocess and handle common errors.

        Args:
            cmd: Command to run
            timeout: Optional timeout in seconds

        Returns:
            Completed process result

        Raises:
            IsolationError: On subprocess failure
            PackageNotFoundError: If package not found on PyPI
        """
        timeout = timeout or self.DEFAULT_TIMEOUT

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise IsolationError(
                f"Analysis of '{self.package_name}' timed out after {timeout}s. "
                "The package may be too large or have complex dependencies."
            ) from e
        except FileNotFoundError as e:
            raise IsolationError(
                "uvx is not available. Install uv: https://docs.astral.sh/uv/"
            ) from e

        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()

            # First, check if stdout contains a worker JSON error response
            # The worker outputs {"success": false, "error": "..."} on failure
            if stdout:
                try:
                    worker_output = json.loads(stdout)
                    if isinstance(worker_output, dict) and not worker_output.get("success"):
                        error_msg = worker_output.get("error", "Unknown worker error")
                        raise IsolationError(f"Worker error: {error_msg}")
                except json.JSONDecodeError:
                    pass  # Not JSON, continue with other error checks

            # Check for auto-mcp-tool not found (tool not published or available)
            if "auto-mcp-tool" in stderr and ("not found" in stderr.lower() or "No such" in stderr):
                raise IsolationError(
                    "auto-mcp-tool is not available on PyPI or cannot be installed via uvx.\n"
                    "This feature requires auto-mcp-tool to be published. For local development,\n"
                    "install the package you want to analyze directly: pip install <package>"
                )

            # Check for internal-worker command not found
            if "internal-worker" in stderr or "No such command" in stderr:
                raise IsolationError(
                    "The installed version of auto-mcp-tool does not support isolated execution.\n"
                    "Please upgrade auto-mcp-tool: pip install --upgrade auto-mcp-tool"
                )

            # Check for target package not found on PyPI
            if self.package_name in stderr and ("not found" in stderr.lower() or "No such package" in stderr):
                raise PackageNotFoundError(
                    f"Package '{self.package_name}' not found on PyPI"
                )

            # Generic "not found" for the target package
            if "Could not find a version" in stderr or "No matching version" in stderr:
                if self.version:
                    raise IsolationError(
                        f"Version '{self.version}' not available for package '{self.package_name}'"
                    )
                raise PackageNotFoundError(
                    f"Package '{self.package_name}' not found on PyPI"
                )

            if "Connection" in stderr or "Network" in stderr or "Timeout" in stderr:
                raise IsolationError(
                    f"Network error while fetching '{self.package_name}'. "
                    "Check your internet connection or use --no-isolated with a locally installed package."
                )

            # Generic error with full output for debugging
            error_details = stderr or stdout or "No error details available"
            raise IsolationError(f"uvx execution failed:\n{error_details}")

        return result

    def run_check(self, config: IsolationConfig) -> PackageMetadata:
        """Run package check in isolation.

        Args:
            config: Configuration for the check operation

        Returns:
            PackageMetadata with analysis results
        """
        config_json = json.dumps(config.to_dict())
        cmd = self._build_uvx_command("check", config_json)

        result = self._run_subprocess(cmd)

        # Parse JSON output
        try:
            output_data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise IsolationError(
                f"Worker produced invalid output: {result.stdout[:200]}... stderr: {result.stderr}"
            ) from e

        if not output_data.get("success"):
            raise IsolationError(output_data.get("error", "Unknown worker error"))

        return PackageMetadata.from_dict(output_data["metadata"])

    def run_generate(self, config: IsolationConfig, output_path: Path) -> Path:
        """Run package generation in isolation.

        Args:
            config: Configuration for the generate operation
            output_path: Path to write the generated server file

        Returns:
            Path to the generated file
        """
        config.output_path = str(output_path.absolute())
        config_json = json.dumps(config.to_dict())
        cmd = self._build_uvx_command("generate", config_json)

        result = self._run_subprocess(cmd)

        # Parse JSON output
        try:
            output_data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise IsolationError(
                f"Worker produced invalid output: {result.stdout[:200]}... stderr: {result.stderr}"
            ) from e

        if not output_data.get("success"):
            raise IsolationError(output_data.get("error", "Unknown worker error"))

        return Path(output_data["output_path"])

    def run_serve(self, config: IsolationConfig) -> NoReturn:
        """Run package serve in isolation.

        This replaces the current process with the uvx subprocess.

        Args:
            config: Configuration for the serve operation

        Note:
            This function does not return - it exec's into the subprocess.
        """
        config_json = json.dumps(config.to_dict())
        cmd = self._build_uvx_command("serve", config_json)

        # Use os.execvp to replace current process
        # This is the cleanest approach for stdio transport
        os.execvp("uvx", cmd)

    def run_serve_subprocess(self, config: IsolationConfig) -> subprocess.Popen[str]:
        """Run package serve as a subprocess (alternative to exec).

        This is useful when you want to manage the subprocess yourself.

        Args:
            config: Configuration for the serve operation

        Returns:
            The subprocess handle
        """
        config_json = json.dumps(config.to_dict())
        cmd = self._build_uvx_command("serve", config_json)

        return subprocess.Popen(
            cmd,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True,
        )
