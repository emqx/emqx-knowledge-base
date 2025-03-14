"""Configuration module for the application."""
import os
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables from .env file
load_dotenv()


class Config(BaseModel):
    """Application configuration."""

    # Slack API credentials
    slack_bot_token: str = Field(default_factory=lambda: os.getenv("SLACK_BOT_TOKEN", ""))
    slack_app_token: str = Field(default_factory=lambda: os.getenv("SLACK_APP_TOKEN", ""))
    slack_signing_secret: str = Field(default_factory=lambda: os.getenv("SLACK_SIGNING_SECRET", ""))

    # OpenAI API credentials
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))

    # PostgreSQL database configuration
    database_url: str = Field(default_factory=lambda: os.getenv("DATABASE_URL", ""))

    # Application settings
    embedding_model: str = Field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    )
    response_model: str = Field(default_factory=lambda: os.getenv("RESPONSE_MODEL", "gpt-4o"))
    embedding_dimension: int = 1536  # Dimension for text-embedding-3-small
    save_emoji: str = "books"  # Emoji to trigger saving a thread

    # EMQX Documentation URLs
    emqx_docs_latest: str = "https://docs.emqx.com/en/emqx/latest/"
    emqx_docs_enterprise_base: str = "https://docs.emqx.com/en/enterprise/"
    emqx_docs_opensource_base: str = "https://docs.emqx.com/en/emqx/"
    emqx_release_notes: str = "https://docs.emqx.com/en/emqx/latest/changes/changes-ee-v5.html"
    emqx_operator_docs: str = "https://docs.emqx.com/en/emqx-operator/latest/"

    def validate_config(self) -> list[str]:
        """Validate the configuration and return a list of missing required values."""
        missing = []
        if not self.slack_bot_token:
            missing.append("SLACK_BOT_TOKEN")
        if not self.slack_app_token:
            missing.append("SLACK_APP_TOKEN")
        if not self.slack_signing_secret:
            missing.append("SLACK_SIGNING_SECRET")
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.database_url:
            missing.append("DATABASE_URL")
        return missing


# Create a global config instance
config = Config() 
