"""Tests for logging utilities."""

import logging

import pytest

from auto_mcp.utils.logging import (
    get_logger,
    log_debug,
    log_error,
    log_info,
    log_warning,
    print_error,
    print_success,
    print_warning,
    setup_logging,
)


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_default(self) -> None:
        """Test setup_logging with default level."""
        logger = setup_logging()
        assert logger is not None
        assert logger.name == "auto_mcp"
        assert logger.level == logging.INFO

    def test_setup_logging_custom_level(self) -> None:
        """Test setup_logging with custom level."""
        logger = setup_logging(level=logging.DEBUG)
        assert logger.level == logging.DEBUG


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_default(self) -> None:
        """Test get_logger with default name."""
        logger = get_logger()
        assert logger.name == "auto_mcp"

    def test_get_logger_custom_name(self) -> None:
        """Test get_logger with custom name."""
        logger = get_logger("custom_logger")
        assert logger.name == "custom_logger"


class TestLogFunctions:
    """Tests for log_* functions."""

    def test_log_info(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test log_info function."""
        with caplog.at_level(logging.INFO, logger="auto_mcp"):
            log_info("Test info message")
        assert "Test info message" in caplog.text

    def test_log_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test log_warning function."""
        with caplog.at_level(logging.WARNING, logger="auto_mcp"):
            log_warning("Test warning message")
        assert "Test warning message" in caplog.text

    def test_log_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test log_error function."""
        with caplog.at_level(logging.ERROR, logger="auto_mcp"):
            log_error("Test error message")
        assert "Test error message" in caplog.text

    def test_log_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test log_debug function."""
        with caplog.at_level(logging.DEBUG, logger="auto_mcp"):
            log_debug("Test debug message")
        assert "Test debug message" in caplog.text


class TestPrintFunctions:
    """Tests for print_* functions."""

    def test_print_success(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test print_success function."""
        print_success("Success message")
        captured = capsys.readouterr()
        assert "Success message" in captured.out

    def test_print_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test print_error function."""
        print_error("Error message")
        captured = capsys.readouterr()
        assert "Error message" in captured.err

    def test_print_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test print_warning function."""
        print_warning("Warning message")
        captured = capsys.readouterr()
        assert "Warning message" in captured.out
