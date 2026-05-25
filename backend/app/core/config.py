from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "MindOS"
    app_env: str = "development"
    storage_backend: str = "sqlite"
    sqlite_path: str = "data/mindos.db"
    frontend_url: str = "http://localhost:5173"
    enable_local_llm: bool = False
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "qwen3:8b"
    ollama_timeout_seconds: int = 120
    ollama_num_ctx: int = 8192
    ollama_thinking_mode: bool = False
    chat_context_direct_limit: int = 4
    chat_context_related_per_event: int = 1
    chat_context_max_chars_per_event: int = 700
    chat_context_max_total_chars: int = 6000
    chat_history_limit: int = 4

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
