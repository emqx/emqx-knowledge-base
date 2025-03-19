"""Configuration for the application."""

import os
from typing import Optional, List

from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables from .env file
load_dotenv()


class Config(BaseModel):
    """Configuration for the application."""

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/knowledge_base"
    )

    # LLM Configuration
    llm_api_key: Optional[str] = os.getenv("LLM_API_KEY")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "1536"))

    # Slack
    slack_bot_token: Optional[str] = os.getenv("SLACK_BOT_TOKEN")
    slack_app_token: Optional[str] = os.getenv("SLACK_APP_TOKEN")
    slack_signing_secret: Optional[str] = os.getenv("SLACK_SIGNING_SECRET")
    slack_team_id: Optional[str] = os.getenv("SLACK_TEAM_ID")

    # LlamaIndex
    llama_index_verbose: bool = (
        os.getenv("LLAMA_INDEX_VERBOSE", "false").lower() == "true"
    )

    # Application
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Server
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "3000"))

    # WebSocket
    websocket_ping_interval: int = int(
        os.getenv("WEBSOCKET_PING_INTERVAL", "20")
    )  # seconds
    websocket_timeout: int = int(os.getenv("WEBSOCKET_TIMEOUT", "60"))  # seconds
    websocket_max_message_size: int = int(
        os.getenv("WEBSOCKET_MAX_MESSAGE_SIZE", "1048576")
    )  # 1MB

    # File uploads
    upload_folder: str = os.getenv("UPLOAD_FOLDER", "uploads")
    max_upload_size: int = int(os.getenv("MAX_UPLOAD_SIZE", "10485760"))  # 10MB

    # Logging
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_date_format: str = "%Y-%m-%d %H:%M:%S"

    # Environment
    environment: str = os.getenv("ENVIRONMENT", "production")

    # Security
    cors_origins: list = os.getenv("CORS_ORIGINS", "*").split(",")
    secret_key: str = os.getenv("SECRET_KEY", "supersecretkey")
    jwt_secret: str = os.getenv(
        "JWT_SECRET", secret_key
    )  # Secret key for validating JWTs

    # Features
    enable_slack: bool = os.getenv("ENABLE_SLACK", "false").lower() == "true"

    def validate_config(self) -> List[str]:
        """Validate the configuration and return a list of missing required values."""
        missing = []

        # Check for required LLM API key
        if not self.llm_api_key:
            missing.append("LLM_API_KEY")

        # Check for required Slack credentials if Slack is enabled
        if self.enable_slack:
            if not self.slack_bot_token:
                missing.append("SLACK_BOT_TOKEN")
            if not self.slack_app_token:
                missing.append("SLACK_APP_TOKEN")
            if not self.slack_signing_secret:
                missing.append("SLACK_SIGNING_SECRET")
            if not self.slack_team_id:
                missing.append("SLACK_TEAM_ID")

        return missing

    def __init__(self, **data):
        super().__init__(**data)


# Create a global config instance
config = Config()

# Print environment information for debugging
print(f"[CONFIG] Running in environment: {config.environment}")

# Export settings for easier imports
settings = config
