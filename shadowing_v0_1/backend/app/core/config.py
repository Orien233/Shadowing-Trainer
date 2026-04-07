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


class Settings(BaseSettings):
    app_name: str = "Shadowing Trainer"
    debug: bool = True
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

    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
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
    def recordings_dir(self) -> Path:
        return self.data_path / "recordings"

    @property
    def cache_dir(self) -> Path:
        return self.data_path / "cache"

    @property
    def db_path(self) -> Path:
        return self.data_path / "app.db"


settings = Settings()
