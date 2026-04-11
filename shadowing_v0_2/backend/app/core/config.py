from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILES = (
    BACKEND_DIR / ".env",
    BACKEND_DIR / ".env.local",
    BACKEND_DIR / ".env.example",
)

# Centralized configuration management using Pydantic's BaseSettings, loading from .env files and providing convenient properties for file paths.
class Settings(BaseSettings):
    app_name: str = "Shadowing Trainer"
    debug: bool = True # Default to True for development, but can be overridden by environment variable.
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: List[str] | str = ["http://localhost:5173"]

    data_dir: str = "./data"
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_api_key: str = ""

    # Max total concurrent DeepSeek requests allowed in this backend process.
    translation_concurrency: int = 5
    translation_request_timeout_seconds: float = 60.0
    translation_max_retries: int = 2
    translation_retry_base_seconds: float = 0.8
    translation_max_connections: int = 200
    translation_max_keepalive_connections: int = 50
    processing_lock_timeout_seconds: int = 1800
    processing_lock_heartbeat_seconds: int = 10

    model_config = SettingsConfigDict( #replace with Config in older Pydantic versions
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
    )

    # Custom validators to handle flexible input formats for debug and CORS origins settings.
    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_value(cls, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on", "debug", "development", "dev"}:
                return True
            if lowered in {"0", "false", "no", "off", "release", "production", "prod"}:
                return False
        return value

    # Custom validator to allow CORS origins to be specified as a comma-separated string or a list of strings.
    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "translation_concurrency",
        "translation_max_connections",
        "translation_max_keepalive_connections",
        "processing_lock_timeout_seconds",
        "processing_lock_heartbeat_seconds",
    )
    @classmethod
    def validate_positive_int_settings(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Value must be >= 1.")
        return value

    @field_validator("translation_max_retries")
    @classmethod
    def validate_non_negative_retries(cls, value: int) -> int:
        if value < 0:
            raise ValueError("translation_max_retries must be >= 0.")
        return value

    @field_validator("translation_request_timeout_seconds", "translation_retry_base_seconds")
    @classmethod
    def validate_positive_float_settings(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Value must be > 0.")
        return value

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def materials_dir(self) -> Path:
        return self.data_path / "materials"

    @property
    def audio_dir(self) -> Path:
        return self.data_path / "audio"

    @property
    def sentence_audio_dir(self) -> Path:
        return self.audio_dir / "sentences"

    @property
    def recordings_dir(self) -> Path:
        return self.data_path / "recordings"

    @property
    def cache_dir(self) -> Path:
        return self.data_path / "cache"

    @property
    def db_path(self) -> Path:
        return self.data_path / "app.db"


settings = Settings()
