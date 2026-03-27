"""Application configuration loaded from environment variables and .env file."""

import os
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the Drone Unit Manager backend.

    All fields can be overridden via environment variables or a .env file.
    Directories are created automatically on startup.
    """

    APP_NAME: str = "Drone Unit Manager"
    SECRET_KEY: str = os.getenv("SECRET_KEY", secrets.token_hex(32))  # JWT signing key
    DATABASE_URL: str = ""  # SQLite connection string (auto-generated if blank)
    TELEMETRY_DATABASE_URL: str = ""  # Separate DB for high-volume telemetry data
    DATA_DIR: Path = Path(__file__).parent.parent / "data"  # Root data directory
    UPLOAD_DIR: Path = Path("")  # File upload storage path
    MEDIA_CACHE_DIR: Path = Path("")  # Cached media (thumbnails, etc.)
    SESSION_EXPIRE_MINUTES: int = 1440  # JWT token lifetime (24 hours)
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50 MB max upload

    model_config = {"env_file": ".env", "extra": "ignore"}

    def model_post_init(self, __context):
        """Derive default paths from DATA_DIR and ensure all directories exist."""
        if not self.DATABASE_URL:
            self.DATABASE_URL = f"sqlite:///{self.DATA_DIR / 'drone_unit_manager.db'}"
        if not self.TELEMETRY_DATABASE_URL:
            self.TELEMETRY_DATABASE_URL = f"sqlite:///{self.DATA_DIR / 'telemetry.db'}"
        if not self.UPLOAD_DIR or str(self.UPLOAD_DIR) == ".":
            self.UPLOAD_DIR = self.DATA_DIR / "uploads"
        if not self.MEDIA_CACHE_DIR or str(self.MEDIA_CACHE_DIR) == ".":
            self.MEDIA_CACHE_DIR = self.DATA_DIR / "media_cache"
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
