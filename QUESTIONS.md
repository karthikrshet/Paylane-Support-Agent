# Questions for Fini

This log keeps three things separate: what I asked, what Fini answered, and what I assumed in the meantime. An assumption here is my own default, not something Fini approved.

**Status:** questions drafted on 2026-10-11, not yet sent. Answers: none yet.

| # | Question | Why it matters | Answer | Assumption used until answered |
|---|---|---|---|---|
| Q1 | `get_customer` always returns `verified: false` and there's no verify tool. Is verification the in-chat check, tracked in session state? | Decides who owns the verified flag | — | Session state; set true only when the email resolves and the last 4 match, compared in code |
| Q2 | If the email or last 4 is wrong, may the agent say which one? | Saying "no account with that email" leaks who is a customer | — | Generic "those details don't match"; lock and escalate on the 3rd failure |
| Q3 | Is exactly $75.00 auto-approved? Is a 30-day-old charge allowed? Transaction or settlement date, which timezone? | Boundary cases are the easiest place to fail | — | $75.00 is in; age 0–29 days is in, 30+ escalates; transaction date, UTC |
| Q4 | Can pending transactions be refunded? | A pending charge may still drop off | — | No; explain it's pending |
| Q5 | Can a customer ask for part of a charge (e.g. $70 of $120) to stay under $75? | Classic way to game the limit | — | No; the limit applies to the full transaction amount, so escalate |
| Q6 | Is there a cap per customer per day across several refunds? | Several small refunds in one chat | — | No cap in the policy; not enforced. Flagging 3+ refunds in one chat for review is listed as a next step |
| Q7 | Is a "refund" a Paylane goodwill credit, or should merchant disputes go elsewhere? | Changes what the agent promises | — | A Paylane-issued refund to the card |
| Q8 | Frozen cards: the API gives no freeze reason. Where does "explain why" come from? Can a frozen-card customer still get a refund? | The agent might invent a reason | — | General reasons only, never a guess. No auto-refund while frozen; escalate the whole request |
| Q9 | Must every unauthorized-charge claim be escalated, including under $500? Verify first, or escalate immediately? | The policy only names fraud over $500 | — | Escalate every fraud claim immediately, with no refund and no verification required; priority if over $500 |
| Q10 | Someone threatens legal action before verifying, but `escalate_to_human` takes a `customer_id`. | Can't escalate without an id | — | Escalate with `customer_id: null` and the details given |
| Q11 | Should the agent tell customers the $75 / 30-day rules? | Stating them invites splitting | — | Say "this one needs a teammate to review", not the exact threshold |
| Q12 | Channels and languages: chat only? English only? | Scope of tests | — | Chat, English |
| Q13 | There's no tool to search a customer's transactions, and customers rarely know transaction IDs. May I add a customer-scoped `find_transactions` tool? | Without it, "the coffee charge" can't be found reliably | — | Added as a clearly labeled extension; the 4 spec tools are unchanged |

## Email to send

> **Subject:** Paylane assignment – a few questions before I build
>
> Hi Deep,
>
> Thanks for reopening the process. I'm starting on the Paylane agent and have a few questions. I'll build on the defaults in brackets unless you tell me otherwise.
>
> 1. Verification: `get_customer` always returns `verified: false`. Should I treat verification as the in-chat check (email + last 4) tracked in session? [Yes]
> 2. Boundaries: is exactly $75.00 auto-approved, and is a 30-day-old charge in or out? Which date counts? [$75.00 in; 30 days out; transaction date, UTC]
> 3. Pending charges: refundable? [No]
> 4. Partial refunds: can a customer ask for $70 of a $120 charge? [No, the limit is on the full charge]
> 5. Frozen cards: the API has no freeze reason. Where should "explain why" come from? [General reasons only, never a guess] And can a frozen-card customer still get an otherwise eligible refund? [No; escalate it]
> 6. Fraud: should every unauthorized-charge claim be escalated, and immediately rather than after verification? [Yes to both; over $500 marked priority]
> 7. Legal threats before verification: escalate without a customer id? [Yes, with the email given]
> 8. Should the agent state the $75 / 30-day rules to customers? [No] Also: customers rarely know transaction IDs and there's no search tool. May I add a customer-scoped `find_transactions` tool, marked as an extension? [Yes, marked as an extension]
>
> Thanks, Karthik
