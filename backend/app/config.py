import os
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Drone Unit Manager"
    SECRET_KEY: str = os.getenv("SECRET_KEY", secrets.token_hex(32))
    DATABASE_URL: str = ""
    TELEMETRY_DATABASE_URL: str = ""
    DATA_DIR: Path = Path(__file__).parent.parent / "data"
    UPLOAD_DIR: Path = Path("")
    MEDIA_CACHE_DIR: Path = Path("")
    SESSION_EXPIRE_MINUTES: int = 1440  # 24 hours
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB

    model_config = {"env_file": ".env", "extra": "ignore"}

    def model_post_init(self, __context):
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
