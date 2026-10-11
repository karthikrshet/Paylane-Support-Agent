"""Redaction for everything that is logged or written to a transcript.

- Emails become p***@example.com.
- 12-19 digit runs (card-number shaped) are removed.
- Standalone 4-digit runs become ****. Runs inside dates (2026-10-11), ids
  (TK-0001, RF-0001), times and money ($1200, 1200.00) are left alone. A bare year
  in prose ("in 2026") is masked too; that's an accepted false positive.
- Any dict value under a key containing "last4" is masked whatever its type.
"""
import re

EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b")
LONG_DIGITS_RE = re.compile(r"(?<!\d)(?:\d[ -]?){11,18}\d(?!\d)")
FOUR_DIGITS_RE = re.compile(r"(?<![\d\-/.$:])\d{4}(?![\d\-/:]|\.\d)")
MASK = "****"


def mask_email(s: str) -> str:
    return EMAIL_RE.sub(r"\1***@\2", s)


def redact_text(s: str) -> str:
    s = mask_email(s)
    s = LONG_DIGITS_RE.sub("[card number removed]", s)
    return FOUR_DIGITS_RE.sub(MASK, s)


def redact(obj, _key: str = ""):
    if "last4" in _key.lower() and obj is not None:
        return MASK
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        return {k: redact(v, str(k)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [redact(v) for v in obj]
    return obj
