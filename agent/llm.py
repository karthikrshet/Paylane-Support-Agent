"""Provider adapters. Each one turns a provider response into an LLMReply; the runner
never touches a provider SDK directly. History is kept in Anthropic message format.

Sampling note: current Claude models (Sonnet 5.5 and newer) reject temperature/top_p,
so determinism comes from seeded data, a fixed date and repeated runs, not temperature 0.
"""
from dataclasses import dataclass, field


class ProviderError(Exception):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class LLMReply:
    content: list                  # appended to history unchanged (keeps thinking blocks intact)
    text: str
    tool_calls: list = field(default_factory=list)
    stop_reason: str | None = None
    model: str | None = None


class AnthropicLLM:
    REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(self, model: str, effort: str = "medium", fallbacks: bool = True, max_tokens: int = 8000):
        import anthropic
        self._anthropic = anthropic
        self.client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY or an `ant auth login` profile
        self.model, self.effort, self.fallbacks, self.max_tokens = model, effort, fallbacks, max_tokens

    def create(self, system: str, tools: list, messages: list) -> LLMReply:
        kwargs = dict(model=self.model, max_tokens=self.max_tokens, system=system,
                      tools=tools, messages=messages)
        body = {"output_config": {"effort": self.effort}}
        try:
            if self.fallbacks:
                body["fallbacks"] = "default"
                resp = self.client.beta.messages.create(
                    betas=[self.REFUSAL_FALLBACK_BETA], extra_body=body, **kwargs)
            else:
                resp = self.client.messages.create(extra_body=body, **kwargs)
        except self._anthropic.APIError as e:
            raise ProviderError(type(e).__name__) from e
        calls = [ToolCall(b.id, b.name, b.input) for b in resp.content if b.type == "tool_use"]
        text = "".join(b.text for b in resp.content if b.type == "text")
        return LLMReply(content=list(resp.content), text=text, tool_calls=calls,
                        stop_reason=resp.stop_reason, model=resp.model)


class ScriptedLLM:
    """Deterministic stand-in for tests. Each step is a list of blocks
    ({"text": ...} or {"tool": name, "input": {...}}) or an Exception to raise."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.requests = []
        self._n = 0

    def create(self, system, tools, messages) -> LLMReply:
        self.requests.append(list(messages))
        if not self.steps:
            return LLMReply(content=[{"type": "text", "text": "(script ended)"}], text="(script ended)")
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise ProviderError(type(step).__name__) from step
        content, calls, text = [], [], ""
        for b in step:
            if "tool" in b:
                self._n += 1
                tid = f"toolu_{self._n:03d}"
                content.append({"type": "tool_use", "id": tid, "name": b["tool"], "input": b.get("input", {})})
                calls.append(ToolCall(tid, b["tool"], b.get("input", {})))
            else:
                content.append({"type": "text", "text": b["text"]})
                text += b["text"]
        return LLMReply(content=content, text=text, tool_calls=calls,
                        stop_reason="tool_use" if calls else "end_turn", model="scripted")


def make_llm(provider: str, model: str, effort: str, fallbacks: bool):
    if provider == "anthropic":
        return AnthropicLLM(model, effort=effort, fallbacks=fallbacks)
    raise SystemExit(f"Unknown PROVIDER {provider!r}. Add an adapter in agent/llm.py.")
