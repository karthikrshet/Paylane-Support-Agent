"""Regression tests for: refund exception -> no retry, minimal verification result,
integer-cent search, and the hard-escalation gate."""
import json

import pytest

from paylane.api import MockPaylane


# a. refund that raises after it may have gone through: outcome unknown, never retried

def test_refund_exception_is_outcome_unknown_and_never_retried(priya, monkeypatch):
    priya.look("T100")
    calls = []

    def flaky_refund(txn_id, amount):
        calls.append(txn_id)
        priya.api.txns["T100"]["status"] = "refunded"   # it went through...
        raise TimeoutError("processor timed out")        # ...but we never heard back

    monkeypatch.setattr(priya.api, "issue_refund", flaky_refund)
    first = priya.refund("T100", 42.50)
    assert first["ok"] is False and first["reason"] == "refund_outcome_unknown"
    assert "Do not retry" in first["next_step"]

    second = priya.refund("T100", 42.50)
    assert second["reason"] == "POLICY_DENIED: refund_failed_escalate"
    assert calls == ["T100"]                              # API invoked exactly once

    kinds = [e["kind"] for e in priya.s.events]
    assert "refund_outcome_unknown" in kinds
    ev = next(e for e in priya.s.events if e["kind"] == "refund_outcome_unknown")
    assert ev["txn_id"] == "T100" and ev["error"] == "TimeoutError"
    refund_events = [e for e in priya.s.events if e["kind"] == "tool" and e["tool"] == "issue_refund"]
    assert refund_events[0]["decision"] == "error:refund_outcome_unknown"
    assert not any(e["result"].get("ok") for e in refund_events)   # never reported as success


# b. verification result is minimal

@pytest.mark.parametrize("email,last4", [("priya@example.com", "4821"), ("aisha@example.com", "7710")])
def test_verification_result_has_no_id_email_or_digits(h, email, last4):
    out = h.verify(email, last4)
    assert out["verified"] is True
    assert set(out) == {"name", "status", "verified"}
    dump = json.dumps(out)
    assert last4 not in dump and "@" not in dump and "C00" not in dump
    assert " " not in out["name"]                          # first name only
    assert h.s.customer_id is not None                     # id lives in session state


# c. search compares integer cents

def test_find_transactions_amount_uses_integer_cents():
    api = MockPaylane()
    hits = lambda amount: [m["txn_id"] for m in api.find_transactions("C004", amount=amount)["matches"]]
    assert hits("18.99") == ["T108"]
    assert hits(18.99) == ["T108"]
    assert hits(54) == hits("54.00") == ["T109"]
    assert hits("18.990") == []          # to_cents rejects more than 2 decimals -> matches nothing
    assert hits(18.989) == []


def test_router_rejects_invalid_search_amount(h):
    h.verify("tom@example.com", "5502")
    assert h.call("find_transactions", amount=18.999)["error"] == "invalid_amount"
    assert h.call("find_transactions", amount=18.99)["matches"][0]["txn_id"] == "T108"


# d. hard-escalation gate

def test_hard_escalation_gate_allows_only_verification_and_escalation(h):
    h.s.hard_escalation = "fraud"
    assert h.call("get_transaction", txn_id="T106")["error"] == "HARD_ESCALATION"
    assert h.call("find_transactions", merchant="orion")["error"] == "HARD_ESCALATION"
    assert h.call("issue_refund", txn_id="T106", amount=640)["error"] == "HARD_ESCALATION"
    assert h.verify("tom@example.com", "5502")["verified"] is True
    assert h.call("escalate_to_human", summary="PRIORITY fraud claim, $640")["ticket_id"]
    # still gated after verifying
    assert h.call("get_transaction", txn_id="T106")["error"] == "HARD_ESCALATION"
    assert [c[0] for c in h.api.calls] == ["get_customer", "escalate_to_human"]
    esc = next(e for e in h.s.events if e["kind"] == "escalation")
    assert esc["customer_id"] == "C004"                   # verification let the ticket carry identity
