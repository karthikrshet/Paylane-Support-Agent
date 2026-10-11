"""Synthetic seed data. Every row exists to drive at least one conversation.

Amounts are integer cents internally; the API converts to dollars at its boundary.
"Today" is fixed so transaction ages never drift between runs.
"""
from datetime import date

TODAY = date(2026, 10, 11)

# keyed by normalized email
CUSTOMERS = {
    "priya@example.com":  {"id": "C001", "name": "Priya Raman", "last4": "4821", "status": "active"},
    "marcus@example.com": {"id": "C002", "name": "Marcus Bell", "last4": "1934", "status": "active"},
    "aisha@example.com":  {"id": "C003", "name": "Aisha Khan",  "last4": "7710", "status": "frozen"},
    "tom@example.com":    {"id": "C004", "name": "Tom Ellis",   "last4": "5502", "status": "active"},
}

TXNS = {
    # id      customer          cents  date          merchant              status       drives
    "T100": {"customer_id": "C001", "cents": 4250,  "date": "2026-10-03", "merchant": "Northwind Books",   "status": "settled"},   # simple refund (8d)
    "T101": {"customer_id": "C001", "cents": 7500,  "date": "2026-09-12", "merchant": "Lumen Electronics", "status": "settled"},   # $75.00, 29d: both edges in
    "T102": {"customer_id": "C001", "cents": 3000,  "date": "2026-09-11", "merchant": "Cedar Grocers",     "status": "settled"},   # 30d: age out
    "T103": {"customer_id": "C002", "cents": 12000, "date": "2026-10-05", "merchant": "Atlas Outdoor",     "status": "settled"},   # over limit
    "T104": {"customer_id": "C002", "cents": 6000,  "date": "2026-10-01", "merchant": "Pixel Streaming",   "status": "refunded"},  # double refund
    "T105": {"customer_id": "C002", "cents": 2500,  "date": "2026-10-10", "merchant": "Metro Transit",     "status": "pending"},   # pending
    "T106": {"customer_id": "C004", "cents": 64000, "date": "2026-10-08", "merchant": "Orion Travel",      "status": "settled"},   # fraud > $500
    "T107": {"customer_id": "C003", "cents": 4000,  "date": "2026-10-02", "merchant": "Fernway Pharmacy",  "status": "settled"},   # frozen card
    "T108": {"customer_id": "C004", "cents": 1899,  "date": "2026-10-06", "merchant": "Brightline Coffee", "status": "settled"},   # clarifying (same merchant
    "T109": {"customer_id": "C004", "cents": 5400,  "date": "2026-09-28", "merchant": "Brightline Coffee", "status": "settled"},   #  as T109 on purpose)
}
