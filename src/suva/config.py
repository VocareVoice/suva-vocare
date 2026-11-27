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

    # The side-panel agent runs on the instruct model; the pipelines use `llm_name`.
    agent_model: str = "apertus-v1-5-70b"
    agent_max_steps: int = 10  # tool calls per user message before the agent must answer

    db_path: Path = Path("data/suva.db")
    corpus_path: Path = Path("data/corpus/rulings.jsonl.gz")
    llm_cache_dir: Path = Path("data/cache/llm")
    examples_path: Path = Path("data/eval/examples.jsonl")


@lru_cache
def get_settings() -> Settings:
    return Settings()
