# Merchant Scenarios

Who this connector is for, what it changes for them, and how I would find out whether it works.

All data in the demo is fictional. Nothing below has been validated with a real merchant; where I describe impact, it is a hypothesis to test, not a result.

## The user

A support or operations person at a small online merchant that takes payments through a gateway. They are not technical. Customers ask them things like:

- "My payment failed. Was I charged?"
- "Where is my refund?"
- "Which plan costs what, and is it still available?"

Today each question means opening the WooCommerce admin, finding the order, reading its status, transaction ID and refund amounts, and sometimes cross-checking the gateway dashboard.

## The real problem (hypothesis)

Access to data is not the problem; the admin already has it. The cost is the lookup loop: find the right order, interpret the status correctly, answer consistently. Some states are easy to misread. In the demo data, order 25 is `completed` but has a partial refund (₹1,000 of ₹4,999). Anyone filtering on `status = refunded` misses it.

My working hypothesis is that most repeat contact comes from payment-failed and refund-status questions. I would confirm that with real ticket data before building anything further.

## Scenarios the connector supports

| Question | Tools used | What the agent can answer | What it cannot |
|---|---|---|---|
| "A customer says their payment failed on order 21." | `woo_get_order`, `woo_list_orders` (status = failed) | Status, total, payment method, transaction ID | The gateway's failure reason. In the demo, reasons appear only inside fixture transaction IDs; a real deployment needs gateway-side data. It cannot retry the payment. |
| "Which orders have refunds, and how much?" | `woo_list_orders` | Refund total vs order total, including partial refunds on completed orders | Itemized refund lines or dates. It cannot issue a refund. |
| "Find the order for transaction `pay_fail_011_otp_timeout`." | `woo_search_orders` | The matching order | A guarantee of which fields search covers. It uses WooCommerce's native `search` parameter; transaction-ID matching was observed on the demo store, not documented behavior. |
| "What do the plans cost?" | `woo_list_products`, `woo_search_products` | Names, prices, stock state | Currency per product; the demo assumes an INR store. |
| "What failed orders do we have, and what is at risk?" | `woo_list_orders` (status = failed) | The failed orders and their combined value (₹6,498 in the demo data) | Retrying or contacting customers. |

## Out of scope by design

- No writes of any kind: no refunds, edits, retries or deletes.
- No customer contact details. Emails are masked; phone, address and customer notes are not returned.
- No date-range, amount or sort parameters in the current tools. The agent can only fetch a page of orders and inspect them itself. See 'Known findings' in the README: in evaluation it handled this inconsistently, so questions such as 'last week's failed orders' should not be trusted until server-side filtering exists.
- The connector does not know the current date. An agent host normally supplies current date and time context; relative-date questions depend on that and are outside this connector's scope.
- Counting or analytics across many orders works only by paging through results. That is fine at 12 orders and not at thousands.

## Discovery questions for a real merchant

1. What are the five questions your support team answers most often?
2. For payment failures and refunds, where do they look today, and how long does an answer take?
3. Which answers have been wrong or inconsistent in the past, and what did that cost?
4. Who is allowed to see customer contact details, and who must not?
5. Which actions (refund, retry, cancel) must always have a human approve them?
6. Which systems besides WooCommerce hold the answer (gateway dashboard, shipping, CRM)?

## How I would measure impact

Proposed metrics. None have been measured.

| Metric | How to measure |
|---|---|
| Time to answer a payment or refund question | Baseline a sample of recent tickets, then compare with agent-assisted answers |
| Answer accuracy | A human checks a sample of agent answers against the admin (shadow mode) |
| Repeat contacts per payment issue | Count follow-up tickets on the same order before and after |
| Escalations to engineering or finance | Count before and after |

## Rollout path

1. **Shadow mode.** The agent answers, a human verifies against the admin, accuracy is logged. No customer sees agent output. Shadow mode should specifically track answers to date-bounded and amount-bounded questions, since these are the ones the current tools cannot filter.
2. **Read-only assist.** Support uses the agent directly, with the human still responsible for the reply.
3. **Remote deployment.** The current connector runs over local stdio. Production needs a remote MCP transport with authentication.
4. **Gateway connector.** Add gateway-side data for failure reasons, since WooCommerce alone cannot supply them.
5. **Write actions** (refund, retry) only behind explicit human approval.

## Risks

- **Wrong answers about money.** Mitigation: read-only access, structured data instead of free text, grounding checks in the evaluation, and shadow mode before any customer-facing use.
- **Customer data sent to a third-party model.** Customer names are included in tool results. A real deployment needs a data-handling decision on this.
- **Prompt injection through merchant text.** Product descriptions and order text are untrusted. The strongest protections are the read-only tool surface and minimal returned fields; the model instruction to treat that text as data is defense in depth, not a guarantee.
- **Model dependence.** Evaluation results apply to the model tested, not to any model.
