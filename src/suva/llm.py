"""Thin OpenAI-compatible chat client for Apertus with an on-disk response cache."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any, NamedTuple

from openai import OpenAI

from suva.config import Settings, get_settings

Message = dict[str, str]


class TokenLogprob(NamedTuple):
    token: str
    top: dict[str, float]  # alternative token -> logprob, including the chosen token


class Completion(NamedTuple):
    content: str
    logprobs: list[TokenLogprob] | None = None


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class LLMClient:
    def __init__(self, settings: Settings | None = None, *, cache: bool = True) -> None:
        self.settings = settings or get_settings()
        self.model = self.settings.llm_name
        self.cache_dir: Path | None = self.settings.llm_cache_dir if cache else None
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            # openai retries 408/409/429/5xx and connection errors with exponential backoff.
            self._client = OpenAI(
                base_url=self.settings.llm_base_url,
                api_key=self.settings.llm_api_key,
                timeout=self.settings.llm_timeout,
                max_retries=self.settings.llm_max_retries,
            )
        return self._client

    def chat(self, messages: list[Message], **params: Any) -> str:
        """Return the assistant message content. `params` go to chat.completions.create."""
        return self.complete(messages, **params).content

    def complete(self, messages: list[Message], **params: Any) -> Completion:
        """Like `chat`, but also returns token logprobs when `logprobs=True` is passed."""
        params.setdefault("temperature", 0.0)
        cache_file = self._cache_file(messages, params)
        if cache_file and cache_file.exists():
            cached = json.loads(cache_file.read_text())
            logprobs = cached.get("logprobs")
            return Completion(
                cached["content"], [TokenLogprob(*t) for t in logprobs] if logprobs else None
            )

        response = self.client.chat.completions.create(
            model=self.model, messages=messages, **params
        )
        choice = response.choices[0]
        logprobs = None
        if choice.logprobs and choice.logprobs.content:
            logprobs = [
                TokenLogprob(t.token, {top.token: top.logprob for top in t.top_logprobs or []})
                for t in choice.logprobs.content
            ]
        completion = Completion(choice.message.content or "", logprobs)

        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(completion._asdict(), ensure_ascii=False))
        return completion

    def chat_json(self, messages: list[Message], **params: Any) -> Any:
        """Chat and parse the reply as JSON, tolerating code fences and surrounding prose."""
        return parse_json(self.chat(messages, **params))

    def _cache_file(self, messages: list[Message], params: dict[str, Any]) -> Path | None:
        if self.cache_dir is None:
            return None
        key = json.dumps(
            {"model": self.model, "messages": messages, "params": params},
            sort_keys=True,
            ensure_ascii=False,
        )
        return self.cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()}.json"


def parse_json(text: str) -> Any:
    if fenced := _JSON_FENCE.search(text):
        text = fenced.group(1)
    # strict=False: models sometimes put raw newlines or tabs inside JSON strings.
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
        if not starts:
            raise
        start = min(starts)
        end = max(text.rfind("}"), text.rfind("]"))
        return json.loads(text[start : end + 1], strict=False)
