from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_name: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_timeout: float = 120.0
    llm_max_retries: int = 5

    db_path: Path = Path("data/suva.db")
    corpus_path: Path = Path("data/corpus/rulings.jsonl")
    llm_cache_dir: Path = Path("data/cache/llm")


@lru_cache
def get_settings() -> Settings:
    return Settings()
