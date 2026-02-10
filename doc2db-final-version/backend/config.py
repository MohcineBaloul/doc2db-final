"""App configuration from environment."""
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load .env from the backend folder (where this file lives), not from cwd
_BACKEND_DIR = Path(__file__).resolve().parent
_ENV_FILE = _BACKEND_DIR / ".env"
load_dotenv(_ENV_FILE)


class Settings(BaseSettings):
    """Settings loaded from environment."""

    openai_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./doc2db.db"
    max_upload_mb: int = 20

    class Config:
        env_file = str(_ENV_FILE) if _ENV_FILE.exists() else ".env"
        extra = "ignore"


settings = Settings()
