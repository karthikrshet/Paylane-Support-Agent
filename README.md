# Paylane Support Agent

A chat support agent for Paylane that handles refunds, verification, frozen cards and escalations per policy. A code-level guard means it can't issue a refund the policy forbids, whatever the model says.

**Result:** the eval has not been run against the live model yet. Once it has, the score, the refund safety numbers and the failure-and-fix writeup will be in [EVAL_REPORT.md](EVAL_REPORT.md), and this line will be regenerated from that output.

## Run it

```
git clone <repo> && cd paylane-agent
cp .env.example .env          # add ANTHROPIC_API_KEY
make install                  # pip install -r requirements.txt
make test                     # policy, router, runner and check tests (no API key needed)
make eval                     # runs all 21 conversations, writes transcripts/ and results/, prints the score
make chat                     # talk to the agent yourself
```

No `make` (e.g. on Windows)? Run the commands directly: `python -m pytest -q`, `python -m eval.run_eval`, `python chat.py`. Useful flags: `--runs 3`, `--judge` (LLM wording judge), `--only c04,c10` (quick look, written to `results/scratch/`), `--prompt v2`.

## What's where

- `RULEBOOK.md`: the policy as an ordered decision table, plus what the preflight misses
- `agent/prompt.py`: system prompt, versioned (v1 stays frozen once evaluated; fixes go in v2)
- `agent/tools.py`: tool schemas, the router (the only path from model to API) and the single escalation wrapper
- `agent/runner.py`: the hand-written tool loop, with budget and honest fallback
- `paylane/guard.py`: the refund guard; `paylane/preflight.py`: the hard-escalation pattern check
- `paylane/api.py`, `paylane/data.py`: the mock API (the 4 spec tools plus 1 extension) and synthetic seed data
- `conversations/`: 12 core scenarios plus 9 extra edge cases, each with why it was chosen and its checks
- `eval/`: the check library, an independent policy oracle for the safety metrics, the judge, and the runner
- `transcripts/`, `results/`: generated per prompt version and per run
- `QUESTIONS.md`: what I asked Fini, the answers, and the assumptions used meanwhile

## Design decisions

1. **The policy is enforced twice.** The prompt teaches the rules, and a deterministic guard blocks any `issue_refund` that breaks them.
2. **The model never sees card digits.** The router compares the last 4 in code and returns only `verified: true/false`. The model can't leak what it never received.
3. **Hard escalations come before verification.** Legal threats, any fraud claim and closure requests go straight to a person. A pattern check enforces this in code; its limits are documented in RULEBOOK.md.
4. **Session state is the source of truth, not the model's memory.** It has a customer-specific part, cleared on an identity switch, and a session-wide part (failed attempts, lock, tickets, audit log) that is kept.
5. **The eval scores what the model tried, not only what got through.** A refund the guard blocked still fails `no_refund_attempted`. "Forbidden attempts" comes from an independent policy oracle in `eval/metrics.py`, not from the guard's own verdicts. Safety text checks also read model drafts that a fallback hid.
6. **A ticket is claimed only after one is returned.** One escalation wrapper serves the model, the lock, the preflight and the fallback; it records a ticket only on a non-empty `ticket_id`.
7. **`find_transactions` is an extension** beyond the 4 spec tools (QUESTIONS.md, Q13). It is customer-scoped, and its results are candidates only: a refund needs an exact-ID `get_transaction` first.
8. **No sampling parameters.** Current Claude models (default `claude-sonnet-5-5`) reject `temperature`. Determinism comes from seeded data, a fixed "today" (2026-10-11) and repeated runs, and the report says how many runs each result held for.
9. **Refusal fallback is on.** Requests use the Claude API's server-side refusal fallback (`ANTHROPIC_FALLBACKS=0` turns it off). A refusal that still comes back ends in the honest fallback escalation.

## Scope

A mock support agent on synthetic data. It is not a production payment system and must not be pointed at real cardholder data.

## Known limits / what I'd do next

- The preflight is a regex backstop: it misses paraphrases and other languages, and it flags denials. See RULEBOOK.md.
- Conversations are scripted, so a customer turn can't react to an unexpected agent reply. The checks are written to tolerate reasonable variation in wording.
- Text checks for ticket claims, promises and leaks are regex heuristics. Wording quality is left to the optional LLM judge, which can never override a deterministic fail.
- There is no per-chat refund cap (QUESTIONS.md, Q6). Flagging 3+ refunds in one chat for review would be the next guard rule.
- Only an Anthropic adapter ships. The runner is provider-agnostic (`agent/llm.py`), but no second provider is wired up.
