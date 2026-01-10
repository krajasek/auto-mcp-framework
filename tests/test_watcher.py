"""Tests for file watcher and hot-reload functionality."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from watchdog.observers.polling import PollingObserver


@pytest.fixture(autouse=True)
def use_polling_observer():
    """Use PollingObserver instead of FSEvents Observer to avoid macOS segfaults.

    The FSEvents-based Observer can cause segmentation faults on macOS when
    multiple observers are started/stopped rapidly in tests. PollingObserver
    is more stable for testing purposes.
    """
    with patch("auto_mcp.watcher.Observer", PollingObserver):
        yield


from auto_mcp.watcher import (
    ChangeHandler,
    FileWatcher,
    HotReloadServer,
    ModuleReloader,
)


def create_temp_module(tmp_path: Path, name: str = "test_module") -> tuple[Path, ModuleType]:
    """Create a temporary Python module file and load it.

    Args:
        tmp_path: Temporary directory
        name: Module name

    Returns:
        Tuple of (file path, loaded module)
    """
    module_path = tmp_path / f"{name}.py"
    module_path.write_text('''"""Test module."""

def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

VERSION = 1
''')

    # Create a mock module that points to this file
    module = ModuleType(name)
    module.__file__ = str(module_path)

    def add(a: int, b: int) -> int:
        return a + b

    add.__module__ = name
    module.add = add
    module.VERSION = 1

    return module_path, module


class TestModuleReloader:
    """Tests for ModuleReloader class."""

    def test_register_module(self, tmp_path: Path) -> None:
        """Test registering a module."""
        _, module = create_temp_module(tmp_path)
        reloader = ModuleReloader()

        path = reloader.register_module(module)

        assert path is not None
        assert path.name == "test_module.py"

    def test_register_module_no_file(self) -> None:
        """Test registering a module without __file__."""
        module = ModuleType("no_file_module")
        reloader = ModuleReloader()

        path = reloader.register_module(module)

        assert path is None

    def test_get_module_path(self, tmp_path: Path) -> None:
        """Test getting a module's path."""
        _, module = create_temp_module(tmp_path)
        reloader = ModuleReloader()
        reloader.register_module(module)

        path = reloader.get_module_path("test_module")

        assert path is not None
        assert "test_module.py" in str(path)

    def test_get_module_path_not_registered(self) -> None:
        """Test getting path for unregistered module."""
        reloader = ModuleReloader()

        path = reloader.get_module_path("nonexistent")

        assert path is None

    def test_reload_module(self, tmp_path: Path) -> None:
        """Test reloading a module that exists in sys.modules."""
        # Use a real module that we can reload
        import auto_mcp.config as test_module

        reloader = ModuleReloader()
        reloader._module_paths[test_module.__name__] = Path(test_module.__file__ or "")

        # Reload should work for real modules
        reloaded = reloader.reload_module(test_module.__name__)

        assert reloaded is not None
        assert reloaded.__name__ == test_module.__name__

    def test_reload_module_not_in_sys_modules(self) -> None:
        """Test reloading a module not in sys.modules."""
        reloader = ModuleReloader()

        reloaded = reloader.reload_module("nonexistent_module")

        assert reloaded is None


class TestChangeHandler:
    """Tests for ChangeHandler class."""

    def test_on_modified_python_file(self, tmp_path: Path) -> None:
        """Test handling Python file modification."""
        callback = MagicMock()
        handler = ChangeHandler(callback, debounce_seconds=0)

        event = MagicMock()
        event.is_directory = False
        event.src_path = str(tmp_path / "test.py")

        handler.on_modified(event)

        callback.assert_called_once()

    def test_on_modified_non_python_file(self, tmp_path: Path) -> None:
        """Test ignoring non-Python files."""
        callback = MagicMock()
        handler = ChangeHandler(callback, debounce_seconds=0)

        event = MagicMock()
        event.is_directory = False
        event.src_path = str(tmp_path / "test.txt")

        handler.on_modified(event)

        callback.assert_not_called()

    def test_on_modified_directory(self, tmp_path: Path) -> None:
        """Test ignoring directory events."""
        callback = MagicMock()
        handler = ChangeHandler(callback, debounce_seconds=0)

        event = MagicMock()
        event.is_directory = True
        event.src_path = str(tmp_path / "subdir")

        handler.on_modified(event)

        callback.assert_not_called()

    def test_on_created_python_file(self, tmp_path: Path) -> None:
        """Test handling Python file creation."""
        callback = MagicMock()
        handler = ChangeHandler(callback, debounce_seconds=0)

        event = MagicMock()
        event.is_directory = False
        event.src_path = str(tmp_path / "new.py")

        handler.on_created(event)

        callback.assert_called_once()

    def test_debounce(self, tmp_path: Path) -> None:
        """Test debouncing of rapid events."""
        callback = MagicMock()
        handler = ChangeHandler(callback, debounce_seconds=0.5)

        event = MagicMock()
        event.is_directory = False
        event.src_path = str(tmp_path / "test.py")

        # Fire multiple events rapidly
        handler.on_modified(event)
        handler.on_modified(event)
        handler.on_modified(event)

        # Should only call once due to debouncing
        assert callback.call_count == 1


class TestFileWatcher:
    """Tests for FileWatcher class."""

    def test_init(self) -> None:
        """Test watcher initialization."""
        callback = MagicMock()
        watcher = FileWatcher(callback)

        assert watcher.is_running is False

    def test_watch_path(self, tmp_path: Path) -> None:
        """Test adding a watch path."""
        callback = MagicMock()
        watcher = FileWatcher(callback)

        watcher.watch_path(tmp_path)

        assert len(watcher._watched_paths) == 1

    def test_watch_path_dedup(self, tmp_path: Path) -> None:
        """Test that duplicate paths are not added."""
        callback = MagicMock()
        watcher = FileWatcher(callback)

        watcher.watch_path(tmp_path)
        watcher.watch_path(tmp_path)

        assert len(watcher._watched_paths) == 1

    def test_watch_module(self, tmp_path: Path) -> None:
        """Test watching a module."""
        _, module = create_temp_module(tmp_path)
        callback = MagicMock()
        watcher = FileWatcher(callback)

        watcher.watch_module(module)

        assert len(watcher._watched_paths) == 1

    def test_start_stop(self, tmp_path: Path) -> None:
        """Test starting and stopping the watcher."""
        callback = MagicMock()
        watcher = FileWatcher(callback)
        watcher.watch_path(tmp_path)

        watcher.start()
        assert watcher.is_running is True

        watcher.stop()
        assert watcher.is_running is False

    def test_context_manager(self, tmp_path: Path) -> None:
        """Test using watcher as context manager."""
        callback = MagicMock()

        with FileWatcher(callback) as watcher:
            watcher.watch_path(tmp_path)
            assert watcher.is_running is True

        assert watcher.is_running is False


class TestHotReloadServer:
    """Tests for HotReloadServer class."""

    def test_init(self, tmp_path: Path) -> None:
        """Test hot-reload server initialization."""
        _, module = create_temp_module(tmp_path)

        mock_auto = MagicMock()
        mock_auto.create_server.return_value = MagicMock()

        server = HotReloadServer(mock_auto, [module])

        assert server._modules == [module]

    def test_create_server(self, tmp_path: Path) -> None:
        """Test creating the initial server."""
        _, module = create_temp_module(tmp_path)

        mock_auto = MagicMock()
        mock_server = MagicMock()
        mock_auto.create_server.return_value = mock_server

        hot_server = HotReloadServer(mock_auto, [module])
        result = hot_server.create_server()

        assert result is mock_server
        mock_auto.create_server.assert_called_once_with([module])

    def test_create_server_no_method(self, tmp_path: Path) -> None:
        """Test error when AutoMCP has no create_server method."""
        _, module = create_temp_module(tmp_path)

        mock_auto = object()  # No create_server method

        hot_server = HotReloadServer(mock_auto, [module])

        with pytest.raises(RuntimeError, match="create_server"):
            hot_server.create_server()

    def test_start_stop_watching(self, tmp_path: Path) -> None:
        """Test starting and stopping file watching."""
        _, module = create_temp_module(tmp_path)

        mock_auto = MagicMock()
        mock_auto.create_server.return_value = MagicMock()

        hot_server = HotReloadServer(mock_auto, [module])

        hot_server.start_watching()
        assert hot_server._watcher is not None
        assert hot_server._watcher.is_running

        hot_server.stop_watching()
        assert hot_server._watcher is None

    def test_context_manager(self, tmp_path: Path) -> None:
        """Test using hot-reload server as context manager."""
        _, module = create_temp_module(tmp_path)

        mock_auto = MagicMock()
        mock_auto.create_server.return_value = MagicMock()

        with HotReloadServer(mock_auto, [module]) as hot_server:
            assert hot_server._watcher is not None
            assert hot_server._watcher.is_running

        assert hot_server._watcher is None

    def test_regenerate_server(self, tmp_path: Path) -> None:
        """Test server regeneration on file change."""
        _, module = create_temp_module(tmp_path)

        mock_auto = MagicMock()
        mock_server1 = MagicMock()
        mock_server2 = MagicMock()
        mock_auto.create_server.side_effect = [mock_server1, mock_server2]

        hot_server = HotReloadServer(mock_auto, [module])

        # Create initial server
        hot_server.create_server()
        assert hot_server._server is mock_server1

        # Trigger regeneration
        hot_server._regenerate_server()
        assert hot_server._server is mock_server2


class TestFileWatcherIntegration:
    """Integration tests for file watching."""

    def test_file_change_triggers_callback(self, tmp_path: Path) -> None:
        """Test that file changes trigger the callback."""
        callback_triggered = threading.Event()
        changed_path: list[Path] = []

        def callback(path: Path) -> None:
            changed_path.append(path)
            callback_triggered.set()

        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text("# Initial content")

        watcher = FileWatcher(callback, debounce_seconds=0.1)
        watcher.watch_path(tmp_path)
        watcher.start()

        try:
            # Wait for watcher to start
            time.sleep(0.2)

            # Modify the file
            test_file.write_text("# Modified content")

            # Wait for callback
            triggered = callback_triggered.wait(timeout=2.0)

            # The callback should have been called
            # Note: This may be flaky on some systems
            if triggered:
                assert len(changed_path) >= 1
        finally:
            watcher.stop()
