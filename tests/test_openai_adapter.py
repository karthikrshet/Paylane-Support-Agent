"""OpenAI adapter: message/tool translation and a full runner flow against a fake client."""
import json
from types import SimpleNamespace as NS

from agent.llm import OpenAILLM
from agent.runner import Conversation
from agent.tools import TOOL_SCHEMAS
from paylane.api import MockPaylane
from paylane.data import TODAY
from paylane.session import Session


def tc(i, name, args):
    return NS(id=f"call_{i}", type="function",
              function=NS(name=name, arguments=args if isinstance(args, str) else json.dumps(args)))


def resp(text=None, calls=None, finish="stop"):
    msg = NS(content=text, tool_calls=calls, refusal=None)
    return NS(choices=[NS(message=msg, finish_reason="tool_calls" if calls else finish)], model="fake-gpt")


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.requests.append(kw)
        return self.responses.pop(0)


def test_tools_translate_to_functions():
    tools = OpenAILLM.to_openai_tools(TOOL_SCHEMAS)
    assert [t["function"]["name"] for t in tools] == [t["name"] for t in TOOL_SCHEMAS]
    assert tools[0]["type"] == "function" and tools[0]["function"]["parameters"]["required"]


def test_full_refund_flow_through_runner():
    client = FakeClient([
        resp(calls=[tc(1, "get_customer", {"email": "priya@example.com", "card_last4_given": "4821"})]),
        resp(calls=[tc(2, "get_transaction", {"txn_id": "T100"})]),
        resp(calls=[tc(3, "issue_refund", {"txn_id": "T100", "amount": 42.5})]),
        resp(text="Done, refunded $42.50 (RF-0001)."),
        resp(text="You're welcome!"),
    ])
    llm = OpenAILLM("fake-gpt", client=client)
    api, s = MockPaylane(), Session()
    c = Conversation(llm, "SYSTEM PROMPT", api, s, TODAY)
    r = c.send("priya@example.com 4821, refund T100")
    assert "RF-0001" in r.reply and api.txns["T100"]["status"] == "refunded"
    c.send("thanks")

    msgs = client.requests[-1]["messages"]
    assert msgs[0] == {"role": "system", "content": "SYSTEM PROMPT"}
    roles = [m["role"] for m in msgs]
    assert roles == ["system", "user", "assistant", "tool", "assistant", "tool", "assistant", "tool",
                     "assistant", "user"]
    # every tool message answers the assistant tool_call right before it
    for i, m in enumerate(msgs):
        if m["role"] == "tool":
            assert msgs[i - 1]["tool_calls"][0]["id"] == m["tool_call_id"]
    assert "temperature" not in client.requests[0] and "reasoning_effort" not in client.requests[0]


def test_unparseable_arguments_are_rejected_not_executed():
    client = FakeClient([resp(calls=[tc(1, "issue_refund", "{not json")]), resp(text="Sorry.")])
    llm = OpenAILLM("fake-gpt", client=client)
    api, s = MockPaylane(), Session()
    Conversation(llm, "sys", api, s, TODAY).send("refund T100")
    ev = [e for e in s.events if e["kind"] == "tool"][0]
    assert ev["decision"] == "invalid:schema" and api.calls == []


def test_finish_reasons_map_to_fallbacks():
    client = FakeClient([resp(text="partial", finish="length")])
    llm = OpenAILLM("fake-gpt", client=client)
    api, s = MockPaylane(), Session()
    r = Conversation(llm, "sys", api, s, TODAY).send("hi")
    assert r.fallback == "max_tokens" and r.draft == "partial"
