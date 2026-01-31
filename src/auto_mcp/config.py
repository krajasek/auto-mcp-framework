"""Configuration management using Pydantic Settings."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="AUTO_MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # LLM settings
    llm_provider: Literal["ollama", "openai", "anthropic"] = "ollama"
    llm_model: str = "qwen2.5-coder:7b"
    llm_base_url: str | None = None  # For custom endpoints

    # OpenAI/Anthropic API keys (or set via standard env vars)
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # Generation settings
    include_private: bool = False
    generate_resources: bool = True
    generate_prompts: bool = True

    # Cache settings
    cache_enabled: bool = True
    cache_dir: str | None = None

    # Server settings
    server_name: str = "auto-mcp-server"
    transport: Literal["stdio", "sse", "streamable-http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = 8080

    # Hot reload
    watch: bool = False

    # Session settings
    enable_sessions: bool = False
    session_ttl: int = 3600  # Default 1 hour
    max_sessions: int = 100


def get_settings() -> Settings:
    """Get settings instance."""
    return Settings()
