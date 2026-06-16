import json

from sandcastlegm.gm.providers import (
    AnthropicProvider,
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
    monkeypatch.delenv("SANDCASTLEGM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert make_default_provider() is None
