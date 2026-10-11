"""Hard-escalation preflight: a deterministic pattern check on every customer message.

A backstop for obvious phrasing, not a complete classifier. Known misses and false
positives are listed in RULEBOOK.md: paraphrases ("my solicitor"), other languages,
and denials ("I'm not suing") which flag anyway. A false positive costs one human
review, which is accepted.
"""
import re

# Checked in this order; the first hit wins.
PATTERNS = [
    ("legal", re.compile(
        r"\b(lawyers?|attorneys?|su(e|ed|ing)|lawsuit|legal action|court|regulators?|ombudsman)\b", re.I)),
    ("closure", re.compile(
        r"\b(close|closing|cancel|cancelling|canceling|delete|deleting)\s+(my\s+|the\s+)?(paylane\s+)?account\b", re.I)),
    ("fraud", re.compile(
        r"\b(didn'?t|did not|never)\s+make\b|\b(don'?t|do not)\s+recogni[sz]e\b|\bunauthori[sz]ed\b"
        r"|\bfraud|\bstolen\b|\bsomeone (else )?used my card\b", re.I)),
]

AMOUNT_RE = re.compile(r"\$\s?(\d[\d,]*(?:\.\d{1,2})?)")
PRIORITY_OVER_DOLLARS = 500


def _norm(text: str) -> str:
    return (text or "").replace("’", "'").replace("‘", "'")


def detect(text: str) -> str | None:
    t = _norm(text)
    for flag, rx in PATTERNS:
        if rx.search(t):
            return flag
    return None


def stated_amounts(text: str) -> list[float]:
    out = []
    for m in AMOUNT_RE.finditer(_norm(text)):
        try:
            out.append(float(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return out


def is_priority(flag: str | None, texts: list[str]) -> bool:
    """Fraud over $500, judged from amounts the customer stated."""
    return flag == "fraud" and any(a > PRIORITY_OVER_DOLLARS for t in texts for a in stated_amounts(t))
