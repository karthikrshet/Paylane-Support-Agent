"""Tool schemas the model sees, the router (the only path from model to API), and the
single escalation wrapper used by model calls, the lock, the preflight and the fallback.

Router contract:
1. Unknown tool names and schema-invalid arguments are rejected unexecuted.
2. Gates, in order: locked -> only escalation. hard_escalation -> only get_customer
   and escalation. Not verified -> no transaction tools.
3. get_customer compares last 4 in code; the model never receives card digits.
4. Transaction tools always use session.customer_id, never a model-supplied id.
5. issue_refund goes through the guard, then the API; state updates before the next call.
6. One redacted event per call. The eval reads only these events.
"""
import re
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, ValidationError

from paylane.guard import NEXT_STEP, check_refund
from paylane.money import to_cents
from paylane.redact import mask_email, redact

LAST4_RE = re.compile(r"^\d{4}$")
TXN_TOOLS = {"find_transactions", "get_transaction", "issue_refund"}
MAX_FAILED_ATTEMPTS = 3

TOOL_SCHEMAS = [
    {
        "name": "get_customer",
        "description": (
            "Verify the customer. Pass the email they gave and the last 4 card digits they gave. "
            "The comparison happens in code. Returns {id, name, status, verified: true} on a match, "
            "otherwise {verified: false} only, whatever was wrong."),
        "input_schema": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Email the customer gave."},
                "card_last4_given": {"type": "string", "description": "Exactly the 4 digits the customer typed."},
            },
            "required": ["email", "card_last4_given"],
            "additionalProperties": False,
        },
    },
    {
        "name": "find_transactions",
        "description": (
            "EXTENSION (not in the original spec). Search the verified customer's own transactions. "
            "All filters optional: merchant (case-insensitive substring), amount (dollars), "
            "date (YYYY-MM-DD). Returns up to 5 matches. Matches are candidates only: call "
            "get_transaction on the exact ID before any refund."),
        "input_schema": {
            "type": "object",
            "properties": {
                "merchant": {"type": "string"},
                "amount": {"type": "number"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_transaction",
        "description": "Look up one of the verified customer's transactions by exact ID. Returns amount, date, merchant, status.",
        "input_schema": {
            "type": "object",
            "properties": {"txn_id": {"type": "string"}},
            "required": ["txn_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "issue_refund",
        "description": (
            "Refund a transaction in full. A policy check runs first; if it fails you get "
            "{ok: false, reason: 'POLICY_DENIED: ...', next_step}. Never retry a denied or failed refund."),
        "input_schema": {
            "type": "object",
            "properties": {
                "txn_id": {"type": "string"},
                "amount": {"type": "number", "description": "Full transaction amount in dollars."},
            },
            "required": ["txn_id", "amount"],
            "additionalProperties": False,
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Open a ticket for a human teammate. Write a summary: who, what they want, what you "
            "checked, why you escalated. Returns {ticket_id} or {error}. Works before verification."),
        "input_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
    },
]


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GetCustomerArgs(_Args):
    email: StrictStr = Field(max_length=254)
    card_last4_given: StrictStr = Field(max_length=32)


class FindTransactionsArgs(_Args):
    merchant: Optional[StrictStr] = Field(None, max_length=100)
    amount: Optional[Union[StrictInt, StrictFloat]] = None
    date: Optional[StrictStr] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class GetTransactionArgs(_Args):
    txn_id: StrictStr = Field(max_length=32)


class IssueRefundArgs(_Args):
    txn_id: StrictStr = Field(max_length=32)
    amount: Union[StrictInt, StrictFloat, StrictStr]   # validity checked by the guard


class EscalateArgs(_Args):
    summary: StrictStr = Field(max_length=4000)


ARG_MODELS = {
    "get_customer": GetCustomerArgs,
    "find_transactions": FindTransactionsArgs,
    "get_transaction": GetTransactionArgs,
    "issue_refund": IssueRefundArgs,
    "escalate_to_human": EscalateArgs,
}


# ---------------------------------------------------------------- escalation wrapper

def escalate(s, api, summary: str, source: str) -> dict:
    """The one escalation path. Reuses an existing ticket; records only real ticket ids."""
    if s.tickets:
        s.log("escalation", source=source, api_called=False, reused=True,
              ticket_id=s.tickets[0], summary=redact(summary))
        return {"ticket_id": s.tickets[0], "note": "already_open"}
    try:
        result = api.escalate_to_human(s.customer_id, summary)
    except Exception as e:  # API exception -> honest failure, never a ticket
        result = {"error": f"escalation_exception:{type(e).__name__}"}
    tid = result.get("ticket_id") if isinstance(result, dict) else None
    tid = tid.strip() if isinstance(tid, str) and tid.strip() else None
    if tid:
        s.tickets.append(tid)
    s.log("escalation", source=source, api_called=True, reused=False, customer_id=s.customer_id,
          ticket_id=tid, result=redact(result), summary=redact(summary))
    return {"ticket_id": tid} if tid else {"error": (result or {}).get("error", "escalation_failed")}


# ---------------------------------------------------------------- handlers

def _get_customer(a, s, api, today):
    given = a.card_last4_given.strip()
    if not LAST4_RE.match(given):
        return "rejected:last4_format", {
            "error": "invalid_last4_format",
            "message": "Ask for exactly the 4 last digits of the card. This did not count as an attempt."}
    email = a.email.strip().lower()
    if s.verified and email != s.customer_email:
        s.reset_identity()
        s.log("identity_switch")
    c = api.get_customer(email)
    if "error" not in c and c.get("card_last4") == given:
        s.verified, s.customer_id = True, c["id"]
        s.customer_email, s.customer_status = email, c["status"]
        return "verified", {"id": c["id"], "name": c["name"], "status": c["status"], "verified": True}

    # Unknown email and wrong digits produce exactly the same result.
    if s.verified:
        s.reset_identity()
    s.failed_attempts += 1
    out = {"verified": False}
    if s.failed_attempts >= MAX_FAILED_ATTEMPTS:
        s.locked = True
        s.log("lock", failed_attempts=s.failed_attempts)
        res = escalate(s, api, (
            f"Session locked after {s.failed_attempts} failed verification attempts. "
            f"Last email tried: {email}. Customer may need help proving identity, or this may be "
            f"an attempt to access someone else's account."), source="lock")
        out["locked"] = True
        if res.get("ticket_id"):
            out["ticket_id"] = res["ticket_id"]
        else:
            out["escalation_error"] = res.get("error")
    return "verification_failed", out


def _find_transactions(a, s, api, today):
    if a.amount is not None and to_cents(a.amount) is None:
        return "rejected:invalid_amount", {"error": "invalid_amount"}
    r = api.find_transactions(s.customer_id, a.merchant, a.amount, a.date)
    s.candidates = [m["txn_id"] for m in r["matches"]]
    return "executed", r


def _get_transaction(a, s, api, today):
    key = a.txn_id.strip().upper()
    r = api.get_transaction(s.customer_id, key)
    if "error" not in r:
        s.transactions_seen[key] = {"cents": to_cents(r["amount"]), "date": r["date"], "status": r["status"]}
    return "executed", r


def _issue_refund(a, s, api, today):
    key = a.txn_id.strip().upper()
    ok, reason = check_refund(s, key, a.amount, today)
    if not ok:
        return f"guard:{reason}", {"ok": False, "reason": f"POLICY_DENIED: {reason}",
                                   "next_step": NEXT_STEP.get(reason, "Do not retry. Call escalate_to_human.")}
    r = api.issue_refund(key, a.amount)
    if r.get("ok"):
        s.refunded_txn_ids.add(key)
        s.transactions_seen[key]["status"] = "refunded"
    else:
        s.failed_refund_txn_ids.add(key)
        r = {**r, "next_step": NEXT_STEP["refund_failed_escalate"]}
    return "executed", r


def _escalate_to_human(a, s, api, today):
    return "executed", escalate(s, api, a.summary, source="model")


HANDLERS = {
    "get_customer": _get_customer,
    "find_transactions": _find_transactions,
    "get_transaction": _get_transaction,
    "issue_refund": _issue_refund,
    "escalate_to_human": _escalate_to_human,
}


# ---------------------------------------------------------------- router

def _gate(name, s):
    if s.locked and name != "escalate_to_human":
        return "gate:locked", {"error": "LOCKED", "message": (
            "Too many failed verification attempts. Account actions are disabled for this chat; "
            "it has been escalated. Do not ask for more details.")}
    if s.hard_escalation and name not in ("get_customer", "escalate_to_human"):
        return "gate:hard_escalation", {"error": "HARD_ESCALATION", "message": (
            "This conversation must go to a human specialist. Do not look up or refund anything. "
            "Call escalate_to_human if you haven't, then tell the customer a specialist will follow up.")}
    if not s.verified and name in TXN_TOOLS:
        return "gate:not_verified", {"error": "NOT_VERIFIED", "message": (
            "Verify first: ask for the account email and the last 4 digits of the card.")}
    return None


def _txn_status(api, args):
    if isinstance(args, dict) and isinstance(args.get("txn_id"), str):
        t = api.txns.get(args["txn_id"].strip().upper())
        return t["status"] if t else None
    return None


def route(name, args, s, api, today, source="model") -> dict:
    model = ARG_MODELS.get(name)
    if model is None:
        decision, out = "invalid:unknown_tool", {"error": "invalid_tool_call", "detail": "unknown tool"}
    else:
        try:
            parsed = model.model_validate(args)
        except ValidationError as e:
            detail = "; ".join(f"{'.'.join(map(str, err['loc'])) or 'args'}: {err['type']}" for err in e.errors())
            decision, out = "invalid:schema", {"error": "invalid_tool_call", "detail": detail}
        else:
            gated = _gate(name, s)
            if gated:
                decision, out = gated
            else:
                try:
                    decision, out = HANDLERS[name](parsed, s, api, today)
                except Exception as e:  # API or handler failure: logged, never a success
                    decision, out = f"error:{type(e).__name__}", {"error": "internal_error"}
    s.log("tool", source=source, tool=name, args=redact(args), decision=decision,
          result=redact(out), txn_status_after=_txn_status(api, args))
    return out


__all__ = ["TOOL_SCHEMAS", "route", "escalate", "mask_email"]
