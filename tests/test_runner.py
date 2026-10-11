"""Runner tests with a scripted model: budget, fallbacks, honesty about tickets."""
import json

from agent.llm import ScriptedLLM
from agent.runner import MAX_TOOL_CALLS, MSG_NO_TICKET, Conversation
from paylane.api import MockPaylane
from paylane.data import TODAY
from paylane.session import Session


def convo(steps, **api_kwargs):
    api = MockPaylane(**api_kwargs)
    s = Session()
    return Conversation(ScriptedLLM(steps), "system", api, s, TODAY), api, s


def tool(name, **inp):
    return {"tool": name, "input": inp}


def test_happy_refund_flow():
    c, api, s = convo([
        [tool("get_customer", email="priya@example.com", card_last4_given="4821")],
        [tool("get_transaction", txn_id="T100")],
        [tool("issue_refund", txn_id="T100", amount=42.5)],
        [{"text": "Done, refund RF-0001 is on its way back to your card."}],
    ])
    r = c.send("priya@example.com 4821, refund T100")
    assert r.fallback is None and "RF-0001" in r.reply
    assert api.txns["T100"]["status"] == "refunded"


def test_budget_twelve_calls_only_eight_executed_then_fallback():
    c, api, s = convo([[tool("find_transactions", merchant="x") for _ in range(12)]])
    r = c.send("hi")
    tool_events = [e for e in s.events if e["kind"] == "tool"]
    assert len([e for e in tool_events if e["decision"] != "budget_exceeded"]) == MAX_TOOL_CALLS
    assert len([e for e in tool_events if e["decision"] == "budget_exceeded"]) == 4
    assert r.fallback == "tool_budget" and s.tickets and s.tickets[0] in r.reply
    # every tool_use got a tool_result
    results = c.history[-1]["content"]
    assert len([b for b in results if b["type"] == "tool_result"]) == 12


def test_provider_exception_honest_fallback():
    c, api, s = convo([RuntimeError("boom")])
    r = c.send("refund T100")
    assert r.fallback == "provider_error"
    assert s.tickets and s.tickets[0] in r.reply
    assert api.calls == [("escalate_to_human", None)]


def test_provider_exception_during_outage_claims_no_ticket():
    c, api, s = convo([RuntimeError("boom")], fail_escalation=True)
    r = c.send("refund T100")
    assert r.reply == MSG_NO_TICKET and s.tickets == []


def test_preflight_backstop_escalates_when_model_does_not():
    c, api, s = convo([[{"text": "Sure, first I need your email and last 4."}]])
    r = c.send("Close my account, my lawyer will be in touch.")
    assert s.hard_escalation == "legal"
    assert r.fallback == "preflight:legal" and r.draft.startswith("Sure")
    assert s.tickets and s.tickets[0] in r.reply
    esc = [e for e in s.events if e["kind"] == "escalation"][0]
    assert esc["customer_id"] is None and esc["source"] == "fallback"


def test_preflight_fraud_over_500_marked_priority():
    c, api, s = convo([[{"text": "Let me check."}]])
    c.send("I didn't make this $640 charge, refund it now")
    esc = [e for e in s.events if e["kind"] == "escalation"][0]
    assert esc["summary"].startswith("PRIORITY")


def test_preflight_blocks_lookup_in_same_response_as_model_tries():
    c, api, s = convo([
        [tool("get_customer", email="tom@example.com", card_last4_given="5502"),
         tool("get_transaction", txn_id="T106"),
         tool("issue_refund", txn_id="T106", amount=640)],
        [tool("escalate_to_human", summary="PRIORITY fraud claim $640")],
        [{"text": "A specialist will follow up here."}],
    ])
    c.send("I didn't make this $640 charge. tom@example.com 5502")
    decisions = [e["decision"] for e in s.events if e["kind"] == "tool"]
    assert decisions[:3] == ["verified", "gate:hard_escalation", "gate:hard_escalation"]
    assert ("issue_refund", ("T106", 640)) not in api.calls


def test_model_escalating_itself_means_no_fallback():
    c, api, s = convo([
        [tool("escalate_to_human", summary="Legal threat + closure request")],
        [{"text": "A specialist will follow up here (ticket TK-0001)."}],
    ])
    r = c.send("Close my account, my lawyer will be in touch.")
    assert r.fallback is None and len(api.calls) == 1


def test_fallback_leaves_valid_history_for_next_turn():
    c, api, s = convo([
        [tool("find_transactions") for _ in range(9)],
        [{"text": "Hello again."}],
    ])
    c.send("hi")
    c.send("still there?")
    # roles alternate and the next request saw the note about what the customer was shown
    roles = [m["role"] for m in c.history]
    assert all(a != b for a, b in zip(roles, roles[1:]))
    last_user = c.llm.requests[-1][-1]
    assert last_user["role"] == "user"
    assert any("was not shown" in b.get("text", "") for b in last_user["content"])


def test_round_limit_fallback():
    c, api, s = convo([[tool("find_transactions")]] * 4)
    r = c.send("hi")
    assert r.fallback == "round_limit"


def test_transcript_events_are_json_safe():
    c, api, s = convo([[tool("get_customer", email="priya@example.com", card_last4_given="4821")],
                       [{"text": "Verified."}]])
    c.send("priya@example.com 4821")
    json.dumps(s.events)
