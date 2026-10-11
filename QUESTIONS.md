# Questions for Fini

This log keeps three things separate: what I asked, what Fini answered, and what I assumed in the meantime. An assumption here is my own default, not something Fini approved.

**Status:** sent to Deep by email on 2026-10-12 at 00:21 IST (10 questions; the "Sent as" column maps each one to its number in the email). Deep replied on 2026-10-12 at 01:29 IST: every default I had built on is confirmed, with one clarification on frozen-card wording (Q8). No code changes were needed. Q6, Q7 and Q12 were not asked; they remain my own assumptions.

| # | Sent as | Question | Why it matters | Answer | Assumption used until answered |
|---|---|---|---|---|---|
| Q1 | 1 | `get_customer` always returns `verified: false` and there's no verify tool. Is verification the in-chat check, tracked in session state? | Decides who owns the verified flag | **Confirmed by Deep.** Compare the supplied email and last 4 against the mock record and track successful verification in the session; after three failed attempts, stop verifying in that session and escalate. Tested in c07 (lock), c06, e05. | Session state; set true only when the email resolves and the last 4 match, compared in code |
| Q2 | 2 | If the email or last 4 is wrong, may the agent say which one? | Saying "no account with that email" leaks who is a customer | **Confirmed by Deep** ("Your bracketed defaults are fine"). Tested in c07 (`no_account_existence_leak`). | Generic "those details don't match"; lock and escalate on the 3rd failure |
| Q3 | 3 | Is exactly $75.00 auto-approved? Is a 30-day-old charge allowed? Transaction or settlement date, which timezone? | Boundary cases are the easiest place to fail | **Confirmed by Deep.** Exactly $75 is eligible; exactly 30 days old is not; use the transaction timestamp in UTC and a fixed reference time. Tested in c02 ($75.00, 29 days) and c03 (30 days). | $75.00 is in; age 0–29 days is in, 30+ escalates; transaction date, UTC |
| Q4 | 4 | Can pending transactions be refunded? | A pending charge may still drop off | **Confirmed by Deep:** no pending-charge refunds. Tested in c05 (T105). | No; explain it's pending |
| Q5 | 5 | Can a customer ask for part of a charge (e.g. $70 of $120) to stay under $75? | Classic way to game the limit | **Confirmed by Deep:** no partial refunds to bypass the full-transaction limit. Tested in c04. | No; the limit applies to the full transaction amount, so escalate |
| Q6 | not asked | Is there a cap per customer per day across several refunds? | Several small refunds in one chat | Not asked; assumption only. | No cap in the policy; not enforced. Flagging 3+ refunds in one chat for review is listed as a next step |
| Q7 | not asked | Is a "refund" a Paylane goodwill credit, or should merchant disputes go elsewhere? | Changes what the agent promises | Not asked; assumption only. | A Paylane-issued refund to the card |
| Q8 | 6 | Frozen cards: the API gives no freeze reason. Where does "explain why" come from? Can a frozen-card customer still get a refund? | The agent might invent a reason | **Confirmed by Deep, with a clarification:** explain that the specific reason isn't available, without guessing, and escalate the frozen-card case including any refund request. My default also offered general reasons; see EVAL_REPORT "Known remaining issues". Tested in c09. | General reasons only, never a guess. No auto-refund while frozen; escalate the whole request |
| Q9 | 7 | Must every unauthorized-charge claim be escalated, including under $500? Verify first, or escalate immediately? | The policy only names fraud over $500 | **Confirmed by Deep.** Escalate immediately without requiring verification, without disclosing account details; fraud over $500 marked priority. Tested in c11 (>$500, priority), e02 (small fraud), e04. | Escalate every fraud claim immediately, with no refund and no verification required; priority if over $500 |
| Q10 | 8 | Someone threatens legal action before verifying, but `escalate_to_human` takes a `customer_id`. | Can't escalate without an id | **Confirmed by Deep.** Allow a null `customer_id` when the customer hasn't been identified, note it in the README, and don't invent an id. Exercised in c12 and e01 (escalation before any verification). | Escalate with `customer_id: null` and the details given |
| Q11 | 9 | Should the agent tell customers the $75 / 30-day rules? | Stating them invites splitting | **Confirmed by Deep:** a simple teammate-review explanation for escalated refunds. Checked by `no_threshold_disclosed` in c02, c03, c04, c08. | Say "this one needs a teammate to review", not the exact threshold |
| Q12 | not asked | Channels and languages: chat only? English only? | Scope of tests | Not asked; assumption only. | Chat, English |
| Q13 | 10 | There's no tool to search a customer's transactions, and customers rarely know transaction IDs. May I add a customer-scoped `find_transactions` tool? | Without it, "the coffee charge" can't be found reliably | **Confirmed by Deep**, provided it only exposes the verified customer's own transactions and is clearly documented (README design decision 7). Tested in c10, e07 (two matches), e06 (ownership). | Added as a clearly labeled extension; the 4 spec tools are unchanged |

## Email as sent

To Deep, 2026-10-12 00:21 IST:

> Hi Deep,
>
> Thanks for reopening the process. I've started on the Paylane agent and have a few policy questions. I'm building on the default in brackets for each one, so nothing is blocked. If I don't hear back by Tuesday evening, I'll keep the defaults and note them in the README.
>
> 1. Verification: get_customer always returns verified: false and there's no verify tool. Should I treat verification as the in-chat check (email + last 4 of the card), tracked in the session? [Yes]
> 2. Wrong details: if the email or last 4 is wrong, may the agent say which one? [No, one generic "those details don't match" message; lock and escalate after the 3rd failed try]
> 3. Boundaries: is a charge of exactly $75.00 auto-approved, and is a 30-day-old charge in or out? Which date counts, and in which timezone? [$75.00 in; 30 days out; transaction date, UTC]
> 4. Pending charges: can they be refunded? [No]
> 5. Partial refunds: can a customer ask for $70 of a $120 charge to stay under the limit? [No, the limit applies to the full charge, so it gets escalated]
> 6. Frozen cards: the API gives no freeze reason. Where should "explain why" come from? [General reasons only, never a guess] And can a frozen-card customer still get an otherwise eligible refund? [No, escalate it]
> 7. Fraud: should every unauthorized-charge claim be escalated, including under $500, and immediately rather than after verification? [Yes to both; over $500 marked priority]
> 8. Legal threats before verification: escalate_to_human needs a customer_id. Is it fine to escalate without one? [Yes, with whatever details the customer gave]
> 9. Limits: should the agent tell customers the $75 / 30-day rules? [No, it says a teammate needs to review]
> 10. Searching transactions: customers rarely know transaction IDs and there's no search tool. May I add a find_transactions tool limited to the verified customer's own transactions, clearly marked as an extension? The 4 spec tools stay unchanged. [Yes]
>
> Thanks,
> Karthik

## Deep's reply

From Deep, 2026-10-12 01:29 IST:

> Hi Karthik,
>
> Thanks for laying these out clearly and proposing defaults so you can keep moving. Your bracketed defaults are fine for this assignment.
>
> A few clarifications:
>
> - Verification: yes, compare the supplied email and last 4 against the mock customer record and track successful verification in the session. After three failed attempts, stop further verification attempts in that session and escalate.
> - Refund boundaries: exactly $75 is eligible; exactly 30 days old is not. Use the transaction timestamp in UTC and a fixed reference time for reproducible tests.
> - Frozen cards: explain that the specific reason isn't available, without guessing. Escalate the frozen-card case, including any refund request.
> - Fraud and legal threats: escalate immediately without requiring verification first, but don't disclose account details. For the mock escalation tool, allow a null customer_id when the customer hasn't been identified, and note this in the README. Don't invent an ID.
> - The transaction search extension is fine, provided it only exposes the verified customer's own transactions and you clearly document it.
>
> The other defaults you listed are confirmed too: no pending-charge refunds, no partial refunds to bypass the full-transaction limit, fraud over $500 marked priority, and a simple teammate-review explanation for escalated refunds.
>
> Keep it within the original 4–6 hour scope. We're interested in your judgment, the agent's behavior, and how you test it. Please document these assumptions and cover the relevant edge cases in your evals.
>
> Best,
> Deep
