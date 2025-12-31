"""Tests for configuration management."""

import os
from unittest.mock import patch

import pytest

from auto_mcp.config import Settings, get_settings


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        settings = Settings()

        assert settings.llm_provider == "ollama"
        assert settings.llm_model == "qwen2.5-coder:7b"
        assert settings.cache_enabled is True
        assert settings.server_name == "auto-mcp-server"
        assert settings.transport == "stdio"
        assert settings.port == 8080
        assert settings.include_private is False

    def test_env_var_override(self) -> None:
        """Test that environment variables override defaults."""
        with patch.dict(
            os.environ,
            {
                "AUTO_MCP_LLM_PROVIDER": "openai",
                "AUTO_MCP_LLM_MODEL": "gpt-4o-mini",
                "AUTO_MCP_PORT": "9000",
                "AUTO_MCP_CACHE_ENABLED": "false",
            },
        ):
            settings = Settings()

            assert settings.llm_provider == "openai"
            assert settings.llm_model == "gpt-4o-mini"
            assert settings.port == 9000
            assert settings.cache_enabled is False

    def test_llm_provider_validation(self) -> None:
        """Test that invalid LLM provider raises error."""
        with (
            patch.dict(os.environ, {"AUTO_MCP_LLM_PROVIDER": "invalid"}),
            pytest.raises(ValueError),
        ):
            Settings()

    def test_transport_validation(self) -> None:
        """Test that invalid transport raises error."""
        with (
            patch.dict(os.environ, {"AUTO_MCP_TRANSPORT": "invalid"}),
            pytest.raises(ValueError),
        ):
            Settings()

    def test_api_keys_optional(self) -> None:
        """Test that API keys are optional."""
        settings = Settings()

        assert settings.openai_api_key is None
        assert settings.anthropic_api_key is None

    def test_api_keys_from_env(self) -> None:
        """Test loading API keys from environment."""
        with patch.dict(
            os.environ,
            {
                "AUTO_MCP_OPENAI_API_KEY": "sk-test-key",
                "AUTO_MCP_ANTHROPIC_API_KEY": "sk-ant-test",
            },
        ):
            settings = Settings()

            assert settings.openai_api_key == "sk-test-key"
            assert settings.anthropic_api_key == "sk-ant-test"


class TestGetSettings:
    """Tests for get_settings function."""

    def test_returns_settings_instance(self) -> None:
        """Test that get_settings returns a Settings instance."""
        settings = get_settings()
        assert isinstance(settings, Settings)
