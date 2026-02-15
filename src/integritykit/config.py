"""Configuration management using Pydantic Settings."""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application settings
    app_name: str = Field(
        default="IntegrityKit",
        description="Application name",
    )
    app_version: str = Field(
        default="0.4.0",
        description="Application version",
    )
    debug: bool = Field(
        default=False,
        description="Debug mode",
    )

    # MongoDB settings
    mongodb_uri: str = Field(
        default="mongodb://localhost:27017",
        description="MongoDB connection URI",
    )
    mongodb_database: str = Field(
        default="integritykit",
        description="MongoDB database name",
    )

    # Slack settings
    slack_bot_token: str = Field(
        ...,
        description="Slack bot token (xoxb-...)",
    )
    slack_app_token: Optional[str] = Field(
        default=None,
        description="Slack app token for Socket Mode (xapp-...)",
    )
    slack_signing_secret: str = Field(
        ...,
        description="Slack signing secret for request verification",
    )
    slack_workspace_id: str = Field(
        ...,
        description="Slack workspace/team ID",
    )
    slack_monitored_channels: Optional[str] = Field(
        default=None,
        description="Comma-separated list of channel IDs to monitor",
    )
    slack_filter_bot_messages: bool = Field(
        default=True,
        description="Filter out bot messages from ingestion",
    )

    # Slack retry settings
    slack_retry_max_attempts: int = Field(
        default=3,
        description="Maximum number of retry attempts for Slack API calls",
    )
    slack_retry_initial_delay: float = Field(
        default=1.0,
        description="Initial delay in seconds before first retry",
    )
    slack_retry_max_delay: float = Field(
        default=60.0,
        description="Maximum delay in seconds between retries",
    )

    # ChromaDB settings
    chromadb_host: str = Field(
        default="localhost",
        description="ChromaDB host",
    )
    chromadb_port: int = Field(
        default=8000,
        description="ChromaDB port",
    )
    chromadb_collection: str = Field(
        default="signals",
        description="ChromaDB collection name for signal embeddings",
    )

    # OpenAI settings (for embeddings)
    openai_api_key: str = Field(
        ...,
        description="OpenAI API key",
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model to use",
    )

    # Anthropic settings (for LLM operations)
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key for Claude models",
    )

    # Data retention settings
    default_retention_days: int = Field(
        default=90,
        description="Default TTL for signal retention in days",
    )

    @property
    def monitored_channels_list(self) -> Optional[list[str]]:
        """Parse monitored channels from comma-separated string.

        Returns:
            List of channel IDs or None if not configured
        """
        if self.slack_monitored_channels:
            return [
                ch.strip()
                for ch in self.slack_monitored_channels.split(",")
                if ch.strip()
            ]
        return None


# Global settings instance
settings = Settings()
