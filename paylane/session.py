from dataclasses import dataclass, field


@dataclass
class Session:
    """Per-conversation state. This, not the model's memory, is the source of truth."""
    # customer-specific: cleared by reset_identity()
    verified: bool = False
    customer_id: str | None = None
    customer_email: str | None = None      # normalized; masked in logs
    customer_status: str | None = None
    transactions_seen: dict = field(default_factory=dict)  # exact-ID lookups only: {cents, date, status}
    candidates: list = field(default_factory=list)         # find_transactions results
    refunded_txn_ids: set = field(default_factory=set)
    failed_refund_txn_ids: set = field(default_factory=set)
    # session-wide: kept across an identity switch
    failed_attempts: int = 0
    locked: bool = False
    hard_escalation: str | None = None     # "legal" | "closure" | "fraud"
    tickets: list = field(default_factory=list)   # only real, non-empty ticket ids
    events: list = field(default_factory=list)    # redacted audit trail
    turn: int = 0

    def reset_identity(self):
        self.verified = False
        self.customer_id = self.customer_email = self.customer_status = None
        self.transactions_seen.clear()
        self.candidates.clear()
        self.refunded_txn_ids.clear()
        self.failed_refund_txn_ids.clear()

    def log(self, kind: str, **data):
        """Callers pass already-redacted data."""
        self.events.append({"turn": self.turn, "kind": kind, **data})
