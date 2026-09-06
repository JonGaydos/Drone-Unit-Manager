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
    SECRET_KEY: str = ""  # JWT signing key (resolved in model_post_init)
    DATABASE_URL: str = ""  # SQLite connection string (auto-generated if blank)
    TELEMETRY_DATABASE_URL: str = ""  # Separate DB for high-volume telemetry data
    DATA_DIR: Path = Path(__file__).parent.parent / "data"  # Root data directory
    UPLOAD_DIR: Path = Path("")  # File upload storage path
    MEDIA_CACHE_DIR: Path = Path("")  # Cached media (thumbnails, etc.)
    SESSION_EXPIRE_MINUTES: int = 1440  # JWT token lifetime (24 hours)
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50 MB, one file
    # A bulk archive is a different thing from a single upload. A full
    # Airdata export runs to hundreds of megabytes and is the first thing a
    # new unit imports, so capping it at the single-file limit means it
    # cannot be imported at all. Safe because the archive is streamed to
    # disk and its entries are read one at a time, so memory tracks the
    # largest entry rather than the archive.
    MAX_ARCHIVE_SIZE: int = 500 * 1024 * 1024  # 500 MB, a bulk archive
    # One file inside an archive. A flight log is under a megabyte; this is
    # generous and stops an archive that claims to decompress to gigabytes.
    MAX_ARCHIVE_ENTRY_SIZE: int = 50 * 1024 * 1024
    TRUST_PROXY_HEADERS: bool = True  # Honor X-Forwarded-For/X-Real-IP (behind a trusted reverse proxy)

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
        self._resolve_secret_key()

    def _resolve_secret_key(self) -> None:
        """Resolve the JWT signing key without failing open.

        Order of precedence:
        1. SECRET_KEY from the environment (set by entrypoint.sh in prod) — used
           as-is. The "change-me-in-production" placeholder is treated as unset.
        2. A persisted key file at DATA_DIR/.secret_key (shared with
           entrypoint.sh) — read it so the key is stable across restarts.
        3. Generate a key and persist it to that file (dev convenience). Unlike
           the old per-process random default, this stays stable across restarts
           and is shared by any worker reading the same DATA_DIR.
        """
        if self.SECRET_KEY and self.SECRET_KEY != "change-me-in-production":
            return

        key_file = self.DATA_DIR / ".secret_key"
        if key_file.exists():
            try:
                stored = key_file.read_text().strip()
                if stored:
                    self.SECRET_KEY = stored
                    return
            except OSError:
                pass

        generated = secrets.token_hex(32)
        try:
            key_file.write_text(generated + "\n")
        except OSError:
            # Read-only data dir: still better than a per-process key that
            # diverges across workers. Use the generated key for this process.
            pass
        self.SECRET_KEY = generated


settings = Settings()
