"""Logging configuration for auto-mcp."""

import logging

from rich.console import Console
from rich.logging import RichHandler

console = Console()


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure logging with rich handler.

    Args:
        level: Logging level (default: INFO)

    Returns:
        Configured logger instance
    """
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=console,
                rich_tracebacks=True,
                show_path=False,
            )
        ],
    )

    logger = logging.getLogger("auto_mcp")
    logger.setLevel(level)

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name (default: auto_mcp)

    Returns:
        Logger instance
    """
    return logging.getLogger(name or "auto_mcp")


def log_info(message: str) -> None:
    """Log an info message."""
    get_logger().info(message)


def log_warning(message: str) -> None:
    """Log a warning message."""
    get_logger().warning(message)


def log_error(message: str) -> None:
    """Log an error message."""
    get_logger().error(message)


def log_debug(message: str) -> None:
    """Log a debug message."""
    get_logger().debug(message)


def print_success(message: str) -> None:
    """Print a success message to console."""
    console.print(f"[green]{message}[/green]")


def print_error(message: str) -> None:
    """Print an error message to console."""
    err_console = Console(stderr=True)
    err_console.print(f"[red]Error:[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message to console."""
    console.print(f"[yellow]Warning:[/yellow] {message}")
