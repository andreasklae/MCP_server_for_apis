"""Configuration loading from environment and YAML files."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Authentication
    mcp_auth_token: str = ""
    
    # OpenAI API (for chat agent) - supports both direct OpenAI and Azure OpenAI
    openai_api_key: str = ""
    
    # Azure OpenAI settings (if using Azure instead of OpenAI direct)
    azure_openai_endpoint: str = ""  # e.g., https://your-resource.openai.azure.com
    azure_openai_deployment: str = "gpt-4o"  # deployment name in Azure
    azure_openai_api_version: str = "2024-02-15-preview"

    # Rate limiting
    rate_limit_enabled: bool = False
    rate_limit_per_minute: int = 60
    
    # Chat rate limiting (separate from MCP rate limiting)
    chat_rate_limit_per_hour: int = 50  # Messages per hour per IP

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Timeouts
    default_timeout: int = 30
    geo_api_timeout: int = 60

    # Server info
    server_name: str = "kulturarv-mcp-server"
    server_version: str = "1.0.0"

    # Host and port
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def auth_enabled(self) -> bool:
        """Check if authentication is enabled."""
        return bool(self.mcp_auth_token)
    
    @property
    def chat_enabled(self) -> bool:
        """Check if chat agent is enabled (OpenAI or Azure OpenAI configured)."""
        return bool(self.openai_api_key)
    
    @property
    def use_azure_openai(self) -> bool:
        """Check if Azure OpenAI should be used instead of direct OpenAI."""
        return bool(self.azure_openai_endpoint)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def load_api_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """
    Load API configuration from YAML file.
    
    Args:
        config_path: Path to the config file. If None, uses default location.
    
    Returns:
        Dictionary with configuration data.
    """
    if config_path is None:
        # Try to find config relative to project root
        possible_paths = [
            Path("config/apis.yaml"),
            Path(__file__).parent.parent.parent.parent / "config" / "apis.yaml",
        ]
        for path in possible_paths:
            if path.exists():
                config_path = path
                break
        else:
            # Return default empty config if file not found
            return {"enabled_providers": ["example"], "providers": {}}

    config_path = Path(config_path)
    if not config_path.exists():
        return {"enabled_providers": ["example"], "providers": {}}

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    return config


def get_enabled_providers(config: dict[str, Any] | None = None) -> list[str]:
    """Get list of enabled provider names."""
    if config is None:
        config = load_api_config()
    return config.get("enabled_providers", ["example"])


def get_provider_config(provider_name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Get configuration for a specific provider."""
    if config is None:
        config = load_api_config()
    providers = config.get("providers", {})
    return providers.get(provider_name, {})

