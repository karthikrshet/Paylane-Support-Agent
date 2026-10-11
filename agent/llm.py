"""Provider adapters. Each one turns a provider response into an LLMReply; the runner
never touches a provider SDK directly. History is kept in Anthropic message format.

Sampling note: current Claude models (Sonnet 5.5 and newer) reject temperature/top_p,
so determinism comes from seeded data, a fixed date and repeated runs, not temperature 0.
"""
import json
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


class OpenAILLM:
    """OpenAI Chat Completions adapter. History stays in Anthropic block format; this
    adapter translates it on the way out and translates the reply back, so the runner,
    router, guard and eval are identical for both providers.

    temperature / reasoning_effort are sent only when set (OPENAI_TEMPERATURE,
    OPENAI_REASONING_EFFORT), because some OpenAI models reject one or the other.
    """

    def __init__(self, model: str, temperature: float | None = None, reasoning_effort: str | None = None,
                 max_tokens: int = 4000, client=None):
        if client is None:
            from openai import OpenAI
            client = OpenAI()                 # reads OPENAI_API_KEY
        import openai
        self._openai = openai
        self.client = client
        self.model, self.temperature, self.reasoning_effort, self.max_tokens = \
            model, temperature, reasoning_effort, max_tokens

    @staticmethod
    def to_openai_tools(tools: list) -> list:
        return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                  "parameters": t["input_schema"]}} for t in tools]

    @staticmethod
    def to_openai_messages(system: str, messages: list) -> list:
        out = [{"role": "system", "content": system}]
        for m in messages:
            blocks = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
            blocks = [b if isinstance(b, dict) else b.model_dump() for b in blocks]
            if m["role"] == "assistant":
                text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
                calls = [{"id": b["id"], "type": "function",
                          "function": {"name": b["name"], "arguments": json.dumps(b.get("input", {}))}}
                         for b in blocks if b.get("type") == "tool_use"]
                msg = {"role": "assistant", "content": text or None}
                if calls:
                    msg["tool_calls"] = calls
                out.append(msg)
            else:
                # tool results first (they must follow the assistant's tool_calls), then any text
                for b in blocks:
                    if b.get("type") == "tool_result":
                        out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"]})
                text = "\n\n".join(b["text"] for b in blocks if b.get("type") == "text")
                if text:
                    out.append({"role": "user", "content": text})
        return out

    def create(self, system: str, tools: list, messages: list) -> LLMReply:
        kwargs = dict(model=self.model, messages=self.to_openai_messages(system, messages),
                      tools=self.to_openai_tools(tools), max_completion_tokens=self.max_tokens)
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except self._openai.APIError as e:
            raise ProviderError(type(e).__name__) from e
        choice = resp.choices[0]
        msg = choice.message
        text = msg.content or ""
        content, calls = [], []
        if text:
            content.append({"type": "text", "text": text})
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except ValueError:
                args = {"_unparseable_arguments": tc.function.arguments}   # router rejects it as invalid
            content.append({"type": "tool_use", "id": tc.id, "name": tc.function.name, "input": args})
            calls.append(ToolCall(tc.id, tc.function.name, args))
        stop = {"length": "max_tokens", "content_filter": "refusal",
                "tool_calls": "tool_use"}.get(choice.finish_reason, "end_turn")
        if getattr(msg, "refusal", None):
            stop = "refusal"
        return LLMReply(content=content, text=text, tool_calls=calls, stop_reason=stop, model=resp.model)


def make_llm(provider: str, model: str, effort: str, fallbacks: bool):
    if provider == "anthropic":
        return AnthropicLLM(model, effort=effort, fallbacks=fallbacks)
    if provider == "openai":
        import os
        temp = os.getenv("OPENAI_TEMPERATURE")
        return OpenAILLM(model, temperature=float(temp) if temp else None,
                         reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT") or None)
    raise SystemExit(f"Unknown PROVIDER {provider!r}. Use anthropic or openai.")
