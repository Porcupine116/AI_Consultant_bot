from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(validation_alias="BOT_TOKEN")
    openrouter_api_key: str = Field(validation_alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="openai/gpt-4o-mini", validation_alias="OPENROUTER_MODEL")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", validation_alias="OPENROUTER_BASE_URL")

    http_proxy: Optional[str] = Field(default=None, validation_alias="HTTP_PROXY")
    https_proxy: Optional[str] = Field(default=None, validation_alias="HTTPS_PROXY")

    default_language: str = Field(default="ru", validation_alias="DEFAULT_LANGUAGE")
    default_tone: str = Field(default="естественный, спокойный, уверенный", validation_alias="DEFAULT_TONE")

    admin_chat_id: Optional[int] = Field(default=None, validation_alias="ADMIN_CHAT_ID")
    lead_channel_id: Optional[str] = Field(default=None, validation_alias="LEAD_CHANNEL_ID")

    database_path: Path = Field(default=Path("data/bot.sqlite3"), validation_alias="DATABASE_PATH")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    request_timeout: float = Field(default=60.0, validation_alias="REQUEST_TIMEOUT")
    request_retries: int = Field(default=3, validation_alias="REQUEST_RETRIES")
    max_history_messages: int = Field(default=12, validation_alias="MAX_HISTORY_MESSAGES")
    ai_temperature: float = Field(default=0.35, validation_alias="AI_TEMPERATURE")
    ai_max_output_tokens: int = Field(default=900, validation_alias="AI_MAX_OUTPUT_TOKENS")
    app_name: str = Field(default="AI Consultant Telegram Bot", validation_alias="APP_NAME")

    def proxy_url(self) -> Optional[str]:
        return self.http_proxy or self.https_proxy


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
