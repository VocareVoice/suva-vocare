from types import SimpleNamespace

from suva.config import Settings
from suva.llm import LLMClient, parse_json


class FakeCompletions:
    def __init__(self, reply, logprobs=None):
        self.reply = reply
        self.logprobs = logprobs
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        message = SimpleNamespace(content=self.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, logprobs=self.logprobs)])


def test_responses_are_cached_on_disk(tmp_path):
    completions = FakeCompletions('Sure:\n```json\n{"score": 80}\n```')
    llm = LLMClient(Settings(llm_name="apertus", llm_cache_dir=tmp_path))
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    messages = [{"role": "user", "content": "Bewerte"}]

    assert llm.chat_json(messages) == {"score": 80}
    assert llm.chat_json(messages) == {"score": 80}
    assert completions.calls == 1
    llm.chat(messages, temperature=0.7)
    assert completions.calls == 2


def test_parse_json_tolerates_prose():
    assert parse_json('Antwort: {"label": "relevant"} Ende') == {"label": "relevant"}
    assert parse_json("[1, 2]") == [1, 2]


def test_logprobs_survive_the_cache(tmp_path):
    top = [SimpleNamespace(token="7", logprob=-0.1), SimpleNamespace(token="6", logprob=-2.5)]
    token = SimpleNamespace(token="7", logprob=-0.1, top_logprobs=top)
    completions = FakeCompletions("7", SimpleNamespace(content=[token]))
    llm = LLMClient(Settings(llm_name="apertus", llm_cache_dir=tmp_path))
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    messages = [{"role": "user", "content": "Zahl?"}]

    fresh = llm.complete(messages, logprobs=True, top_logprobs=2)
    cached = llm.complete(messages, logprobs=True, top_logprobs=2)
    assert fresh == cached
    assert cached.logprobs[0].top == {"7": -0.1, "6": -2.5}
    assert completions.calls == 1
