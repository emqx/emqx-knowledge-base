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
    database_url: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/knowledge_base")

    # OpenAI
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "1536"))

    # Slack
    slack_bot_token: Optional[str] = os.getenv("SLACK_BOT_TOKEN")
    slack_app_token: Optional[str] = os.getenv("SLACK_APP_TOKEN")
    slack_signing_secret: Optional[str] = os.getenv("SLACK_SIGNING_SECRET")
    slack_team_id: Optional[str] = os.getenv("SLACK_TEAM_ID")

    # EMQX
    emqx_base_url: Optional[str] = os.getenv("EMQX_BASE_URL", "http://localhost:18083/api/v5")
    emqx_username: Optional[str] = os.getenv("EMQX_USR_NAME", "admin")
    emqx_password: Optional[str] = os.getenv("EMQX_PWD", "public")

    # LlamaIndex
    llama_index_verbose: bool = os.getenv("LLAMA_INDEX_VERBOSE", "false").lower() == "true"

    # Application
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Server
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "3000"))

    # File uploads
    upload_folder: str = os.getenv("UPLOAD_FOLDER", "uploads")
    max_upload_size: int = int(os.getenv("MAX_UPLOAD_SIZE", "10485760"))  # 10MB

    # Logging
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_date_format: str = "%Y-%m-%d %H:%M:%S"

    # Security
    cors_origins: list = os.getenv("CORS_ORIGINS", "*").split(",")

    # Performance
    workers: int = int(os.getenv("WORKERS", "1"))

    # Features
    enable_slack: bool = os.getenv("ENABLE_SLACK", "false").lower() == "true"
    enable_log_analysis: bool = os.getenv("ENABLE_LOG_ANALYSIS", "true").lower() == "true"

    def validate_config(self) -> List[str]:
        """Validate the configuration and return a list of missing required values."""
        missing = []

        # Check for required OpenAI API key
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")

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

        # Check for required EMQX credentials if log analysis is enabled
        if self.enable_log_analysis:
            if not self.emqx_base_url:
                missing.append("EMQX_BASE_URL")
            if not self.emqx_username:
                missing.append("EMQX_USR_NAME")
            if not self.emqx_password:
                missing.append("EMQX_PWD")

        return missing


# Create a global config instance
config = Config()
