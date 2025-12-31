"""File watcher for hot-reload functionality."""

from __future__ import annotations

import importlib
import importlib.util
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from auto_mcp.utils.logging import get_logger

logger = get_logger(__name__)


class ModuleReloader:
    """Handles reloading of Python modules when their source changes."""

    def __init__(self) -> None:
        """Initialize the reloader."""
        self._module_paths: dict[str, Path] = {}

    def register_module(self, module: ModuleType) -> Path | None:
        """Register a module for watching.

        Args:
            module: The module to register

        Returns:
            The path to the module file, or None if not determinable
        """
        if hasattr(module, "__file__") and module.__file__:
            path = Path(module.__file__).resolve()
            self._module_paths[module.__name__] = path
            return path
        return None

    def get_module_path(self, module_name: str) -> Path | None:
        """Get the path for a registered module.

        Args:
            module_name: Name of the module

        Returns:
            Path to the module file, or None if not registered
        """
        return self._module_paths.get(module_name)

    def reload_module(self, module_name: str) -> ModuleType | None:
        """Reload a module by name.

        Args:
            module_name: Name of the module to reload

        Returns:
            The reloaded module, or None if reload failed
        """
        if module_name not in sys.modules:
            logger.warning(f"Module {module_name} not in sys.modules, cannot reload")
            return None

        try:
            module = sys.modules[module_name]
            reloaded = importlib.reload(module)
            logger.info(f"Reloaded module: {module_name}")
            return reloaded
        except Exception as e:
            logger.error(f"Failed to reload module {module_name}: {e}")
            return None

    def reload_from_path(self, path: Path) -> ModuleType | None:
        """Reload the module associated with a file path.

        Args:
            path: Path to the Python file

        Returns:
            The reloaded module, or None if not found or reload failed
        """
        path = path.resolve()
        for module_name, module_path in self._module_paths.items():
            if module_path == path:
                return self.reload_module(module_name)
        return None


class ChangeHandler(FileSystemEventHandler):
    """Handles file system events for Python files."""

    def __init__(
        self,
        callback: Callable[[Path], None],
        debounce_seconds: float = 0.5,
    ) -> None:
        """Initialize the handler.

        Args:
            callback: Function to call when a Python file changes
            debounce_seconds: Minimum time between callbacks for same file
        """
        super().__init__()
        self._callback = callback
        self._debounce_seconds = debounce_seconds
        self._last_event_times: dict[str, float] = {}
        self._lock = threading.Lock()

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events.

        Args:
            event: The file system event
        """
        if event.is_directory:
            return

        path = Path(str(event.src_path))
        if path.suffix != ".py":
            return

        self._handle_change(path)

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events.

        Args:
            event: The file system event
        """
        if event.is_directory:
            return

        path = Path(str(event.src_path))
        if path.suffix != ".py":
            return

        self._handle_change(path)

    def _handle_change(self, path: Path) -> None:
        """Handle a file change with debouncing.

        Args:
            path: Path to the changed file
        """
        path_str = str(path)
        current_time = time.time()

        with self._lock:
            last_time = self._last_event_times.get(path_str, 0)
            if current_time - last_time < self._debounce_seconds:
                return
            self._last_event_times[path_str] = current_time

        logger.debug(f"File changed: {path}")
        self._callback(path)


class FileWatcher:
    """Watches Python files for changes and triggers callbacks.

    This class uses the watchdog library to monitor file system changes
    and can be used to implement hot-reload functionality.

    Example:
        >>> def on_change(path: Path) -> None:
        ...     print(f"File changed: {path}")
        ...
        >>> watcher = FileWatcher(on_change)
        >>> watcher.watch_path(Path("./src"))
        >>> watcher.start()
        >>> # ... later ...
        >>> watcher.stop()
    """

    def __init__(
        self,
        callback: Callable[[Path], None],
        debounce_seconds: float = 0.5,
    ) -> None:
        """Initialize the file watcher.

        Args:
            callback: Function to call when a Python file changes
            debounce_seconds: Minimum time between callbacks for same file
        """
        self._callback = callback
        self._debounce_seconds = debounce_seconds
        self._observer: Any = None  # Observer type not recognized by mypy
        self._watched_paths: list[Path] = []
        self._running = False

    def watch_path(self, path: Path, recursive: bool = True) -> None:
        """Add a path to watch.

        Args:
            path: Directory or file path to watch
            recursive: Whether to watch subdirectories
        """
        path = path.resolve()
        if path not in self._watched_paths:
            self._watched_paths.append(path)
            logger.debug(f"Added watch path: {path}")

            # If already running, add to observer
            if self._observer and self._running:
                handler = ChangeHandler(self._callback, self._debounce_seconds)
                watch_path = path.parent if path.is_file() else path
                self._observer.schedule(handler, str(watch_path), recursive=recursive)

    def watch_module(self, module: ModuleType) -> None:
        """Watch a module's source file.

        Args:
            module: The module to watch
        """
        if hasattr(module, "__file__") and module.__file__:
            path = Path(module.__file__).resolve()
            self.watch_path(path.parent)

    def start(self) -> None:
        """Start watching for file changes."""
        if self._running:
            return

        self._observer = Observer()
        handler = ChangeHandler(self._callback, self._debounce_seconds)

        for path in self._watched_paths:
            watch_path = path.parent if path.is_file() else path
            self._observer.schedule(handler, str(watch_path), recursive=True)
            logger.info(f"Watching: {watch_path}")

        self._observer.start()
        self._running = True
        logger.info("File watcher started")

    def stop(self) -> None:
        """Stop watching for file changes."""
        if not self._running or not self._observer:
            return

        self._observer.stop()
        self._observer.join(timeout=5.0)
        self._observer = None
        self._running = False
        logger.info("File watcher stopped")

    @property
    def is_running(self) -> bool:
        """Check if the watcher is running."""
        return self._running

    def __enter__(self) -> FileWatcher:
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit."""
        self.stop()


class HotReloadServer:
    """A server wrapper that supports hot-reloading on source changes.

    This class wraps an MCP server and watches source modules for changes.
    When a change is detected, it regenerates the server components.

    Example:
        >>> from auto_mcp import AutoMCP
        >>> import my_module
        >>>
        >>> auto = AutoMCP(use_llm=False)
        >>> hot_server = HotReloadServer(auto, [my_module])
        >>> hot_server.run()  # Blocks and watches for changes
    """

    def __init__(
        self,
        auto_mcp: Any,  # AutoMCP, but avoid circular import
        modules: list[ModuleType],
        debounce_seconds: float = 1.0,
    ) -> None:
        """Initialize the hot-reload server.

        Args:
            auto_mcp: The AutoMCP instance to use for generation
            modules: List of modules to expose and watch
            debounce_seconds: Time to wait before regenerating after changes
        """
        self._auto_mcp = auto_mcp
        self._modules = modules
        self._debounce_seconds = debounce_seconds
        self._reloader = ModuleReloader()
        self._watcher: FileWatcher | None = None
        self._server: object | None = None
        self._regenerate_lock = threading.Lock()
        self._should_stop = threading.Event()

        # Register modules for watching
        for module in modules:
            self._reloader.register_module(module)

    def _on_file_change(self, path: Path) -> None:
        """Handle a file change event.

        Args:
            path: Path to the changed file
        """
        logger.info(f"Detected change in: {path}")

        with self._regenerate_lock:
            # Reload the changed module
            reloaded = self._reloader.reload_from_path(path)
            if reloaded:
                # Update our module list with the reloaded module
                for i, module in enumerate(self._modules):
                    if module.__name__ == reloaded.__name__:
                        self._modules[i] = reloaded
                        break

                # Regenerate server
                self._regenerate_server()

    def _regenerate_server(self) -> None:
        """Regenerate the MCP server with updated modules."""
        try:
            logger.info("Regenerating server...")
            # Access create_server method (AutoMCP)
            if hasattr(self._auto_mcp, "create_server"):
                self._server = self._auto_mcp.create_server(self._modules)
                logger.info("Server regenerated successfully")
            else:
                logger.error("AutoMCP instance doesn't have create_server method")
        except Exception as e:
            logger.error(f"Failed to regenerate server: {e}")

    def start_watching(self) -> None:
        """Start watching for file changes."""
        self._watcher = FileWatcher(
            self._on_file_change,
            debounce_seconds=self._debounce_seconds,
        )

        for module in self._modules:
            self._watcher.watch_module(module)

        self._watcher.start()

    def stop_watching(self) -> None:
        """Stop watching for file changes."""
        if self._watcher:
            self._watcher.stop()
            self._watcher = None

    def create_server(self) -> Any:
        """Create the initial server.

        Returns:
            The FastMCP server instance
        """
        if hasattr(self._auto_mcp, "create_server"):
            self._server = self._auto_mcp.create_server(self._modules)
            return self._server
        raise RuntimeError("AutoMCP instance doesn't have create_server method")

    def run(self, transport: str = "stdio") -> None:
        """Run the server with hot-reload enabled.

        This method blocks and watches for file changes.

        Args:
            transport: The MCP transport to use (stdio, sse)
        """
        # Create initial server
        server = self.create_server()

        # Start watching
        self.start_watching()

        try:
            logger.info("Starting server with hot-reload enabled...")
            # Run the server (this blocks)
            server.run(transport=transport)
        finally:
            self.stop_watching()

    def __enter__(self) -> HotReloadServer:
        """Context manager entry."""
        self.start_watching()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit."""
        self.stop_watching()
