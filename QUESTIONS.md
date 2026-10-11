# Questions for Fini

This log keeps three things separate: what I asked, what Fini answered, and what I assumed in the meantime. An assumption here is my own default, not something Fini approved.

**Status:** sent to Deep by email on 2026-10-12 at 00:21 IST (10 questions; the "Sent as" column maps each one to its number in the email). Q6, Q7 and Q12 were not asked; they are assumptions only. Answers: none yet. The email said the defaults stand if there's no reply by Tuesday evening, 2026-10-13.

| # | Sent as | Question | Why it matters | Answer | Assumption used until answered |
|---|---|---|---|---|---|
| Q1 | 1 | `get_customer` always returns `verified: false` and there's no verify tool. Is verification the in-chat check, tracked in session state? | Decides who owns the verified flag | — | Session state; set true only when the email resolves and the last 4 match, compared in code |
| Q2 | 2 | If the email or last 4 is wrong, may the agent say which one? | Saying "no account with that email" leaks who is a customer | — | Generic "those details don't match"; lock and escalate on the 3rd failure |
| Q3 | 3 | Is exactly $75.00 auto-approved? Is a 30-day-old charge allowed? Transaction or settlement date, which timezone? | Boundary cases are the easiest place to fail | — | $75.00 is in; age 0–29 days is in, 30+ escalates; transaction date, UTC |
| Q4 | 4 | Can pending transactions be refunded? | A pending charge may still drop off | — | No; explain it's pending |
| Q5 | 5 | Can a customer ask for part of a charge (e.g. $70 of $120) to stay under $75? | Classic way to game the limit | — | No; the limit applies to the full transaction amount, so escalate |
| Q6 | not asked | Is there a cap per customer per day across several refunds? | Several small refunds in one chat | — | No cap in the policy; not enforced. Flagging 3+ refunds in one chat for review is listed as a next step |
| Q7 | not asked | Is a "refund" a Paylane goodwill credit, or should merchant disputes go elsewhere? | Changes what the agent promises | — | A Paylane-issued refund to the card |
| Q8 | 6 | Frozen cards: the API gives no freeze reason. Where does "explain why" come from? Can a frozen-card customer still get a refund? | The agent might invent a reason | — | General reasons only, never a guess. No auto-refund while frozen; escalate the whole request |
| Q9 | 7 | Must every unauthorized-charge claim be escalated, including under $500? Verify first, or escalate immediately? | The policy only names fraud over $500 | — | Escalate every fraud claim immediately, with no refund and no verification required; priority if over $500 |
| Q10 | 8 | Someone threatens legal action before verifying, but `escalate_to_human` takes a `customer_id`. | Can't escalate without an id | — | Escalate with `customer_id: null` and the details given |
| Q11 | 9 | Should the agent tell customers the $75 / 30-day rules? | Stating them invites splitting | — | Say "this one needs a teammate to review", not the exact threshold |
| Q12 | not asked | Channels and languages: chat only? English only? | Scope of tests | — | Chat, English |
| Q13 | 10 | There's no tool to search a customer's transactions, and customers rarely know transaction IDs. May I add a customer-scoped `find_transactions` tool? | Without it, "the coffee charge" can't be found reliably | — | Added as a clearly labeled extension; the 4 spec tools are unchanged |

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
