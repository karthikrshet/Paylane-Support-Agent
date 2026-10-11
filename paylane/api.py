"""Mock Paylane API: Fini's four spec tools plus one labeled extension.

Integrity rules only (does the transaction exist, is the amount right, is it already
refunded). Business rules ($75, 30 days, verification, frozen) live in paylane/guard.py.

One instance per conversation, built from a deep copy of the seed, so runs never
affect each other. Ids come from a counter so runs are comparable; eval checks still
never assert on a specific id.
"""
import copy
import itertools

from paylane.data import CUSTOMERS, TXNS
from paylane.money import to_cents


class MockPaylane:
    def __init__(self, fail_escalation: bool = False, fail_refund=()):
        self.customers = copy.deepcopy(CUSTOMERS)
        self.txns = copy.deepcopy(TXNS)
        self.fail_escalation = fail_escalation   # simulate an escalation outage
        self.fail_refund = set(fail_refund)      # txn ids whose refund the processor rejects
        self._ids = itertools.count(1)
        self.calls = []                          # (tool, args) actually executed, for tests

    def get_customer(self, email: str) -> dict:
        self.calls.append(("get_customer", email))
        c = self.customers.get(str(email).strip().lower())
        if not c:
            return {"error": "not_found"}
        return {"id": c["id"], "name": c["name"], "card_last4": c["last4"],
                "status": c["status"], "verified": False}

    def get_transaction(self, customer_id: str, txn_id: str) -> dict:
        self.calls.append(("get_transaction", txn_id))
        t = self.txns.get(str(txn_id).strip().upper())
        if not t or t["customer_id"] != customer_id:
            return {"error": "not_found"}      # same answer for unknown and not-yours
        return {"amount": t["cents"] / 100, "date": t["date"],
                "merchant": t["merchant"], "status": t["status"]}

    # EXTENSION, not in Fini's spec (see QUESTIONS.md Q13). Customer-scoped, max 5 results.
    def find_transactions(self, customer_id, merchant=None, amount=None, date=None) -> dict:
        self.calls.append(("find_transactions", (merchant, amount, date)))
        hits = [(k, t) for k, t in self.txns.items() if t["customer_id"] == customer_id
                and (merchant is None or merchant.lower() in t["merchant"].lower())
                and (amount is None or round(float(amount) * 100) == t["cents"])
                and (date is None or t["date"] == date)]
        return {"matches": [{"txn_id": k, "amount": t["cents"] / 100, "date": t["date"],
                             "merchant": t["merchant"], "status": t["status"]}
                            for k, t in hits[:5]]}

    def issue_refund(self, txn_id: str, amount) -> dict:
        self.calls.append(("issue_refund", (txn_id, amount)))
        key = str(txn_id).strip().upper()
        t = self.txns.get(key)
        if t is None:                      return {"ok": False, "reason": "unknown_transaction"}
        if key in self.fail_refund:        return {"ok": False, "reason": "processor_error"}
        if t["status"] == "refunded":      return {"ok": False, "reason": "already_refunded"}
        if t["status"] != "settled":       return {"ok": False, "reason": "not_settled"}
        if to_cents(amount) != t["cents"]: return {"ok": False, "reason": "amount_mismatch"}
        t["status"] = "refunded"
        return {"ok": True, "refund_id": f"RF-{next(self._ids):04d}"}

    def escalate_to_human(self, customer_id, summary: str) -> dict:
        self.calls.append(("escalate_to_human", customer_id))
        if self.fail_escalation:
            return {"error": "escalation_unavailable"}
        if not summary or not str(summary).strip():
            return {"error": "empty_summary"}
        return {"ticket_id": f"TK-{next(self._ids):04d}"}
