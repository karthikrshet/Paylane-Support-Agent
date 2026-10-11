# Paylane Support Agent

A chat support agent for Paylane that handles refunds, verification, frozen cards and escalations per policy. A code-level guard means it can't issue a refund the policy forbids, whatever the model says.

**Result:** final prompt v3 on OpenAI `gpt-4.1`, 21 scenarios × 3 runs: 20, 18 and 17 of 21 fully passing (157/159, 155/159 and 149/159 checks). 0 policy-violating refunds executed in any version (v1, v2 or v3). Forbidden refund attempts went from 2 per run in v1 to 1, 1, 0 in v3, all blocked by the guard. See [EVAL_REPORT.md](EVAL_REPORT.md) for the failure I fixed (a fake "SYSTEM" message, 0/3 → 3/3), the regression that fix caused, and what's still open.

## Run it

```
git clone https://github.com/karthikrshet/Paylane-Support-Agent.git && cd Paylane-Support-Agent
cp .env.example .env          # add ANTHROPIC_API_KEY or OPENAI_API_KEY
make install                  # pip install -r requirements.txt
make test                     # policy, router, runner and check tests (no API key needed)
make eval                     # reruns all 21 conversations on prompt v3 (saved results are kept; see "Prompt version")
make chat                     # talk to the agent yourself
```

**Providers.** Anthropic is the default (`claude-sonnet-5-5`). If only `OPENAI_API_KEY` is set, it runs on OpenAI (`gpt-4.1` unless `MODEL` says otherwise); `PROVIDER=openai` forces it. Both adapters live in `agent/llm.py` behind one interface, so the prompt, router, guard and eval are identical, and every transcript records which provider and model produced it.

No `make` (e.g. on Windows)? Run the commands directly: `python -m pytest -q`, `python -m eval.run_eval`, `python chat.py`. Useful flags: `--runs 3`, `--judge` (LLM wording judge), `--only c04,c10` (quick look, written to `results/scratch/`), `--prompt v1`.

**Prompt version.** v3 is the final prompt and the default for `chat.py` and the eval (`PROMPT_VERSION` overrides it). The saved v1, v2 and v3 results are committed, and a full run refuses to overwrite them; to reproduce one, use `--only` for a quick look or `--overwrite` for a full rerun.

## What's where

- `RULEBOOK.md`: the policy as an ordered decision table, plus what the preflight misses
- `agent/prompt.py`: system prompt, versioned: v1 (frozen, first eval), v2 (injection fix), v3 (final; dispute escalation, no timelines)
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
2. **The model sees as little as possible.** The router compares the last 4 in code and gives the model only the customer's first name, card status and `verified: true/false`. It never sees card digits, the email on file or internal ids, and transaction tools take the customer id from session state. The model can't leak what it never received.
3. **Hard escalations come before verification.** Legal threats, any fraud claim and closure requests go straight to a person. A pattern check enforces this in code; its limits are documented in RULEBOOK.md.
4. **Session state is the source of truth, not the model's memory.** It has a customer-specific part, cleared on an identity switch, and a session-wide part (failed attempts, lock, tickets, audit log) that is kept.
5. **The eval scores what the model tried, not only what got through.** A refund the guard blocked still fails `no_refund_attempted`. "Forbidden attempts" comes from an independent policy oracle in `eval/metrics.py`, not from the guard's own verdicts. Safety text checks also read model drafts that a fallback hid.
6. **A ticket is claimed only after one is returned.** One escalation wrapper serves the model, the lock, the preflight and the fallback; it records a ticket only on a non-empty `ticket_id`.
7. **`find_transactions` is an extension** beyond the 4 spec tools (QUESTIONS.md, Q13). It is customer-scoped, and its results are candidates only: a refund needs an exact-ID `get_transaction` first.
8. **Determinism comes from seeded data, a fixed "today" (2026-10-11) and repeated runs,** and the report says how many runs each result held for. Sampling parameters are sent only when configured (`OPENAI_TEMPERATURE`), because support for them varies by model.
9. **Refusals end in the honest fallback.** On Anthropic, requests also use the Claude API's server-side refusal fallback (`ANTHROPIC_FALLBACKS=0` turns it off). On either provider, a refusal or a cut-off reply is never shown as an answer; the runner escalates instead.
10. **Model-agnostic.** One adapter per provider (`agent/llm.py`), with the history kept in one format and translated at the edge. Swapping the provider changes nothing the eval measures except the model.

## Scope

A mock support agent on synthetic data. It is not a production payment system and must not be pointed at real cardholder data.

## Known limits / what I'd do next

- The preflight is a regex backstop: it misses paraphrases and other languages, and it flags denials. See RULEBOOK.md.
- Conversations are scripted, so a customer turn can't react to an unexpected agent reply. The checks are written to tolerate reasonable variation in wording.
- Text checks for ticket claims, promises and leaks are regex heuristics. Wording quality is left to the optional LLM judge, which can never override a deterministic fail.
- There is no per-chat refund cap (QUESTIONS.md, Q6). Flagging 3+ refunds in one chat for review would be the next guard rule.
- Adapters exist for Anthropic and OpenAI; other providers need a new adapter in `agent/llm.py`.

## How I built this

I used Claude Code as a coding assistant. From my design plan it wrote and refactored
the code, tests and eval harness, ran the evaluations, and drafted the documentation,
which I reviewed and edited. The design decisions are mine: the two-layer policy
enforcement, the rulebook and its assumptions, the questions to Fini, the test
scenarios, and which failure to write up. The judge spot-check verdicts were drafted
with Claude Code from the transcripts and event log; I reviewed them and stand by
them. I reviewed the code and can walk through any part of it.
