import logging
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Every evaluation in docs/ ran on this model; it is used when LLM_NAME is empty.
DEFAULT_MODEL = "apertus-v1-5-70b"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_name: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    # Not streamed: a 3000-token reply at the 10 tokens/s of a busy gateway takes over 5 minutes.
    llm_timeout: float = 600.0
    llm_max_retries: int = 5

    agent_model: str = ""  # the side-panel agent; empty uses `model`
    agent_max_steps: int = 10  # tool calls per user message before the agent must answer

    db_path: Path = Path("data/suva.db")
    corpus_path: Path = Path("data/corpus/rulings.jsonl.gz")
    llm_cache_dir: Path = Path("data/cache/llm")
    examples_path: Path = Path("data/eval/examples.jsonl")

    @property
    def model(self) -> str:
        """The model every LLM step uses: LLM_NAME, or DEFAULT_MODEL when it is empty."""
        return self.llm_name or DEFAULT_MODEL


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    for model in {settings.model, settings.agent_model or settings.model}:
        if "thinking" in model.lower():
            logging.getLogger(__name__).warning(
                "Model %s looks like a thinking variant; the triage, classification and summary "
                "evaluations all used the regular model (%s).",
                model,
                DEFAULT_MODEL,
            )
    return settings
