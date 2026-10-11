"""The tool loop for one conversation. Hand-written, no framework, so every tool call
is visible.

Per customer turn: preflight -> model -> (tool calls, one at a time, through the router)
-> repeat until the model replies in text, within 4 model rounds and 8 executed tool
calls. Anything that goes wrong ends in the honest fallback: escalate through the same
wrapper and claim a ticket only if one was actually returned.
"""
import json
from dataclasses import dataclass

from agent.llm import ProviderError
from agent.tools import TOOL_SCHEMAS, escalate, route
from paylane.preflight import detect, is_priority
from paylane.redact import redact

MAX_ROUNDS, MAX_TOOL_CALLS = 4, 8

MSG_TICKET = "I've passed this to a teammate (ticket {tid}). They'll reply here."
MSG_NO_TICKET = ("Sorry, I couldn't sort this out, and I couldn't open a ticket "
                 "just now. Please try again in a few minutes.")


@dataclass
class TurnResult:
    reply: str                      # what the customer sees
    draft: str | None = None        # the model's own text when a fallback replaced it
    fallback: str | None = None     # reason, when the runner stepped in


class Conversation:
    def __init__(self, llm, system: str, api, session, today):
        self.llm, self.system, self.api, self.s, self.today = llm, system, api, session, today
        self.history: list = []
        self.customer_texts: list[str] = []
        self._pending_note: str | None = None

    # ------------------------------------------------------------ public

    def send(self, text: str) -> TurnResult:
        s = self.s
        s.turn += 1
        self.customer_texts.append(text)
        flag = detect(text)
        if flag:
            s.log("preflight", flag=flag, already_flagged=s.hard_escalation)
            if not s.hard_escalation:
                s.hard_escalation = flag

        blocks = []
        if self._pending_note:
            blocks.append({"type": "text", "text": self._pending_note})
            self._pending_note = None
        blocks.append({"type": "text", "text": text})
        self._append_user(blocks)

        used = 0
        for _ in range(MAX_ROUNDS):
            try:
                r = self.llm.create(self.system, TOOL_SCHEMAS, self.history)
            except ProviderError as e:
                s.log("provider_error", error=str(e))
                return self._fallback("provider_error")
            except Exception as e:  # anything unexpected from the adapter
                s.log("provider_error", error=type(e).__name__)
                return self._fallback("provider_error")

            self.history.append({"role": "assistant", "content": r.content})
            s.log("model_response", stop_reason=r.stop_reason, model=r.model,
                  tool_calls=[c.name for c in r.tool_calls])

            if r.stop_reason in ("refusal", "max_tokens"):
                return self._fallback(r.stop_reason, draft=r.text or None)

            if not r.tool_calls:
                if not r.text.strip():
                    return self._fallback("empty_reply")
                if (s.hard_escalation or s.locked) and not s.tickets:
                    reason = f"preflight:{s.hard_escalation}" if s.hard_escalation else "locked"
                    return self._fallback(reason, draft=r.text)
                return TurnResult(reply=r.text)

            results = []
            for c in r.tool_calls:                       # sequential, in order
                if used >= MAX_TOOL_CALLS:
                    out = {"error": "BUDGET_EXCEEDED"}   # every tool_use still gets a result
                    s.log("tool", source="model", tool=c.name, args=redact(c.input),
                          decision="budget_exceeded", result=out, txn_status_after=None)
                else:
                    used += 1
                    out = route(c.name, c.input, s, self.api, self.today)
                results.append({"type": "tool_result", "tool_use_id": c.id, "content": json.dumps(out)})
            self.history.append({"role": "user", "content": results})
            if used >= MAX_TOOL_CALLS:
                return self._fallback("tool_budget")
        return self._fallback("round_limit")

    # ------------------------------------------------------------ internals

    def _append_user(self, blocks: list):
        """Merge into a trailing user message (e.g. tool results left by a fallback)."""
        if self.history and self.history[-1]["role"] == "user":
            self.history[-1]["content"].extend(blocks)
        else:
            self.history.append({"role": "user", "content": blocks})

    def _close_open_tool_calls(self):
        """A fallback can leave tool_use blocks without results; the API requires results."""
        if not self.history or self.history[-1]["role"] != "assistant":
            return
        ids = [_get(b, "id") for b in self.history[-1]["content"] if _get(b, "type") == "tool_use"]
        if ids:
            self.history.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": i, "content": json.dumps({"error": "NOT_EXECUTED"})}
                for i in ids]})

    def _fallback(self, reason: str, draft: str | None = None) -> TurnResult:
        s = self.s
        self._close_open_tool_calls()
        prefix = "PRIORITY. " if is_priority(s.hard_escalation, self.customer_texts) else ""
        summary = (f"{prefix}Auto-escalation by the support runner ({reason}). "
                   f"Hard-escalation flag: {s.hard_escalation or 'none'}. Verified: {s.verified}. "
                   f"Last customer message: {self.customer_texts[-1] if self.customer_texts else ''}")
        res = escalate(s, self.api, summary, source="fallback")
        tid = res.get("ticket_id")
        reply = MSG_TICKET.format(tid=tid) if tid else MSG_NO_TICKET
        s.log("fallback", reason=reason, ticket_id=tid, draft=redact(draft) if draft else None)
        self._pending_note = ("[Note from the support system, not the customer: your previous reply was "
                              f"not shown. The customer was shown this instead: \"{reply}\"]")
        return TurnResult(reply=reply, draft=draft, fallback=reason)


def _get(block, key):
    return block.get(key) if isinstance(block, dict) else getattr(block, key, None)
