"""Deterministic refund guard. Every issue_refund passes through here before the API,
whatever the model says. Order matters: the first failing rule names the denial.
"""
from datetime import date

from paylane.money import to_cents  # noqa: F401  (re-exported for callers)

LIMIT_CENTS, MAX_AGE_DAYS = 7500, 30


def check_refund(s, txn_id, amount, today: date) -> tuple[bool, str]:
    if s.locked:                             return False, "session_locked"
    if s.hard_escalation:                    return False, "hard_escalation_active"
    if not s.verified:                       return False, "not_verified"
    if s.customer_status == "frozen":        return False, "card_frozen_escalate"
    key = str(txn_id).strip().upper()
    t = s.transactions_seen.get(key)
    if t is None:                            return False, "transaction_not_looked_up_by_id"
    if key in s.failed_refund_txn_ids:       return False, "refund_failed_escalate"
    if key in s.refunded_txn_ids or t["status"] == "refunded":
                                             return False, "already_refunded"
    if t["status"] != "settled":             return False, "not_settled"
    cents = to_cents(amount)
    if cents is None:                        return False, "invalid_amount"
    if cents != t["cents"]:                  return False, "amount_must_equal_full_transaction"
    if t["cents"] > LIMIT_CENTS:             return False, "over_auto_limit_escalate"
    age = (today - date.fromisoformat(t["date"])).days
    if age < 0:                              return False, "future_dated_transaction"
    if age >= MAX_AGE_DAYS:                  return False, "too_old_escalate"
    return True, "ok"


# What the model is told to do after each denial. Never includes the thresholds.
NEXT_STEP = {
    "session_locked": "Stop account actions. The session is locked and has been escalated.",
    "hard_escalation_active": "Do not refund. Make sure escalate_to_human has been called and tell the customer a specialist will follow up.",
    "not_verified": "Ask for the account email and the last 4 digits of the card first.",
    "card_frozen_escalate": "No refunds while the card is frozen. Explain in general terms and call escalate_to_human.",
    "transaction_not_looked_up_by_id": "Call get_transaction with the exact ID first.",
    "refund_failed_escalate": "Do not retry. Apologize once and call escalate_to_human.",
    "already_refunded": "Tell the customer it has already been refunded. Escalate only if they dispute it.",
    "not_settled": "Tell the customer the charge hasn't settled yet, so it can't be refunded now.",
    "invalid_amount": "The refund amount is always the full transaction amount.",
    "amount_must_equal_full_transaction": "Partial refunds aren't possible. If the full amount isn't eligible, tell the customer a teammate needs to review it and call escalate_to_human.",
    "over_auto_limit_escalate": "Do not retry. Tell the customer a teammate needs to review it and call escalate_to_human.",
    "future_dated_transaction": "Treat as a data error. Do not refund. Call escalate_to_human.",
    "too_old_escalate": "Do not retry. Tell the customer a teammate needs to review it and call escalate_to_human.",
}
