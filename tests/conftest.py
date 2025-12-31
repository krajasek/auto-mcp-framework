"""Pytest fixtures for the auto-mcp test suite."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from auto_mcp.config import Settings


@pytest.fixture
def mock_settings() -> Settings:
    """Create test settings."""
    return Settings(
        llm_provider="ollama",
        llm_model="qwen2.5-coder:7b",
        cache_enabled=False,
        server_name="test-server",
    )


@pytest.fixture
def mock_llm_response() -> str:
    """Create a mock LLM response for tool description."""
    return "A function that performs a specific operation."


@pytest.fixture
def sample_module_code() -> str:
    """Sample Python module code for testing."""
    return '''
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

def _private_helper():
    """This should not be exposed."""
    pass

async def fetch_data(url: str) -> dict:
    """Fetch data from a URL."""
    return {"url": url}

class Calculator:
    """A simple calculator class."""

    def multiply(self, x: int, y: int) -> int:
        """Multiply two numbers."""
        return x * y

    def _internal(self):
        """Internal method."""
        pass
'''


@pytest.fixture
def temp_module_file(tmp_path: Any, sample_module_code: str) -> Any:
    """Create a temporary Python module file."""
    module_file = tmp_path / "sample_module.py"
    module_file.write_text(sample_module_code)
    return module_file


@pytest.fixture
def mock_ollama_client() -> MagicMock:
    """Create a mock Ollama client."""
    client = MagicMock()
    client.chat.return_value = {
        "message": {"content": "A function that performs a specific operation."}
    }
    return client
