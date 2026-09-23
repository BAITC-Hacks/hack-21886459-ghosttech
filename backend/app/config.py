from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")
    database_url: str = ""
    frontend_origins: list[str] = ["http://127.0.0.1:8080", "http://localhost:8080"]
    ai_mode: Literal["auto", "openai", "demo"] = "auto"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = Field(default="gpt-5.4-mini", min_length=1)
    ai_timeout_seconds: float = Field(default=60, gt=0, le=180)

    @property
    def assistant_mode(self) -> Literal["openai", "demo"]:
        if self.ai_mode == "auto":
            return "openai" if self.openai_api_key.get_secret_value().strip() else "demo"
        return self.ai_mode
