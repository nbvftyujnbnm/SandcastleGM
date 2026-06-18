import json

import pytest

from sandcastlegm.gm.providers import (
    AnthropicProvider,
    GeminiProvider,
    OpenRouterProvider,
    make_default_provider,
    make_provider,
)
from sandcastlegm.gm.providers.base import ToolResult
from sandcastlegm.gm.tools import TOOL_SPECS


# --- a fake OpenAI-compatible client -----------------------------------------
class _FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, id, name, arguments):
        self.id = id
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, message):
        self.choices = [_FakeChoice(message)]


class _FakeOpenAI:
    """Records requests; returns a tool call, then narration."""

    def __init__(self):
        self.chat = self
        self.completions = self
        self.requests = []
        self._calls = 0

    def create(self, **kwargs):
        self.requests.append(kwargs)
        self._calls += 1
        if self._calls == 1:
            return _FakeResponse(
                _FakeMessage(
                    content=None,
                    tool_calls=[
                        _FakeToolCall("c1", "roll_dice", json.dumps({"expression": "2d6"}))
                    ],
                )
            )
        return _FakeResponse(_FakeMessage(content="A six and a three: nine."))


def test_openrouter_translates_tools_and_parses_calls():
    fake = _FakeOpenAI()
    provider = OpenRouterProvider(model="test/model", client=fake)
    assert provider.available is True

    provider.add_user("roll some dice")
    resp = provider.generate("SYSTEM PROMPT", TOOL_SPECS)

    # Tools were translated into OpenAI function-call shape.
    sent_tools = fake.requests[0]["tools"]
    assert sent_tools[0]["type"] == "function"
    assert sent_tools[0]["function"]["parameters"] == TOOL_SPECS[0]["input_schema"]
    # System prompt is the first message.
    assert fake.requests[0]["messages"][0]["role"] == "system"

    # The tool call was parsed with arguments as a dict.
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "roll_dice"
    assert resp.tool_calls[0].args == {"expression": "2d6"}


def test_openrouter_history_round_trip():
    fake = _FakeOpenAI()
    provider = OpenRouterProvider(model="test/model", client=fake)
    provider.add_user("go")
    resp1 = provider.generate("SYS", TOOL_SPECS)
    provider.add_tool_results([ToolResult(id=resp1.tool_calls[0].id, name="roll_dice", content="9")])
    resp2 = provider.generate("SYS", TOOL_SPECS)

    assert resp2.text == "A six and a three: nine."
    # Second request carried the assistant tool_call and the tool result.
    second_messages = fake.requests[1]["messages"]
    roles = [m["role"] for m in second_messages]
    assert "assistant" in roles and "tool" in roles


def test_openrouter_without_key_is_unavailable(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    provider = OpenRouterProvider(model="x")
    assert provider.available is False


def test_provider_selection(monkeypatch):
    monkeypatch.delenv("SANDCASTLEGM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    assert isinstance(make_default_provider(), OpenRouterProvider)

    monkeypatch.setenv("SANDCASTLEGM_PROVIDER", "anthropic")
    assert isinstance(make_default_provider(), AnthropicProvider)

    assert isinstance(make_provider("openrouter"), OpenRouterProvider)


def test_provider_selection_none_without_keys(monkeypatch):
    for var in ("SANDCASTLEGM_PROVIDER", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
                "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert make_default_provider() is None


def test_gemini_provider(monkeypatch):
    for var in ("SANDCASTLEGM_PROVIDER", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
                "GOOGLE_API_KEY", "SANDCASTLEGM_MODEL"):
        monkeypatch.delenv(var, raising=False)

    # Drives the shared OpenAI-compatible tool loop against a fake client.
    fake = _FakeOpenAI()
    provider = GeminiProvider(model="gemini-flash", client=fake)
    assert provider.name == "gemini"
    assert provider.model == "gemini-2.5-flash"  # preset resolved
    provider.add_user("hi")
    resp = provider.generate("SYS", TOOL_SPECS)
    assert resp.tool_calls[0].name == "roll_dice"

    # Selection: a Gemini key (and no OpenRouter key) picks the Gemini provider.
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    assert isinstance(make_default_provider(), GeminiProvider)
    assert isinstance(make_provider("gemini"), GeminiProvider)

    # Pass-through for full model ids.
    assert GeminiProvider(model="gemini-2.0-flash", client=fake).model == "gemini-2.0-flash"


def test_model_presets_resolve():
    from sandcastlegm.gm.models import (
        DEFAULT_OPENROUTER_MODEL,
        RECOMMENDED_OPENROUTER_MODELS,
        resolve_model,
    )

    assert resolve_model("gemma3-27b") == "google/gemma-3-27b-it"
    assert DEFAULT_OPENROUTER_MODEL == "google/gemma-3-27b-it"
    # A full id passes through unchanged; unknown strings too.
    assert resolve_model("mistralai/mistral-medium-3.1") == "mistralai/mistral-medium-3.1"
    assert resolve_model(None) is None
    assert RECOMMENDED_OPENROUTER_MODELS[0].key == "gemma3-27b"


def test_provider_retries_on_rate_limit():
    import httpx
    import openai

    class _RateThenOK:
        def __init__(self):
            self.chat = self
            self.completions = self
            self.calls = 0

        def create(self, **kw):
            self.calls += 1
            if self.calls < 3:
                raise openai.RateLimitError(
                    "rate limited",
                    response=httpx.Response(429, request=httpx.Request("POST", "http://x")),
                    body=None,
                )
            return _FakeResponse(_FakeMessage(content="recovered"))

    fake = _RateThenOK()
    # retry_base_delay=0 keeps the test instant.
    provider = OpenRouterProvider(model="m", client=fake, max_retries=5, retry_base_delay=0)
    provider.add_user("go")
    resp = provider.generate("SYS", TOOL_SPECS)
    assert resp.text == "recovered"
    assert fake.calls == 3  # two 429s, then success


def test_provider_gives_up_after_max_retries():
    import httpx
    import openai

    class _AlwaysRate:
        def __init__(self):
            self.chat = self
            self.completions = self
            self.calls = 0

        def create(self, **kw):
            self.calls += 1
            raise openai.RateLimitError(
                "rate limited",
                response=httpx.Response(429, request=httpx.Request("POST", "http://x")),
                body=None,
            )

    fake = _AlwaysRate()
    provider = OpenRouterProvider(model="m", client=fake, max_retries=2, retry_base_delay=0)
    provider.add_user("go")
    with pytest.raises(openai.RateLimitError):
        provider.generate("SYS", TOOL_SPECS)
    assert fake.calls == 3  # initial + 2 retries


def test_openrouter_resolves_preset_key():
    fake = _FakeOpenAI()
    provider = OpenRouterProvider(model="mistral-medium", client=fake)
    assert provider.model == "mistralai/mistral-medium-3.1"


def test_free_suffix_resolution():
    from sandcastlegm.gm.models import resolve_model

    assert resolve_model("gemma3-27b:free") == "google/gemma-3-27b-it:free"
    assert resolve_model("google/gemma-3-27b-it:free") == "google/gemma-3-27b-it:free"
    # preset still works without the suffix
    assert resolve_model("gemma3-27b") == "google/gemma-3-27b-it"


def test_probe_judge_error_is_nonfatal():
    from sandcastlegm.probe import ProbeRunner

    def model_chat(system, user):
        return (
            "Ash drifts through the lantern glow as you step into the soot-choked "
            "market; stalls hiss with steam and the crowd parts. What do you do?"
        )

    def bad_judge(system, user):
        raise RuntimeError("402 insufficient credits")

    runner = ProbeRunner(model_chat, bad_judge)
    report = runner.run(model="m")
    assert runner.judge_errors == len(report.results)  # every judge call failed
    assert all(r.judge is None for r in report.results)
    assert report.judge_means == {}
    # Auto-scoring still produced verdicts.
    assert sum(report.auto_counts.values()) == len(report.results)
