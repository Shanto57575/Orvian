---
doc_key: DOC-COLLECTIONS
title: Accounts Receivable Collections & Escalation Standard Operating Procedure
category: collections
version: v1.4
effective_date: 2026-02-01
---

<!-- page: 1 -->
## Section 1: Collections Aging Buckets and Escalation Framework
Brightline Supply Co. monitors unpaid invoices across five standard aging buckets based on `days_overdue` (`as_of - due_date`):
- **`current`** (`days_overdue <= 0`): Open invoice not yet past its `due_date`.
- **`1-30`** (1 to 30 days overdue): **Tier 1 — Early Reminder & Outreach**.
- **`31-60`** (31 to 60 days overdue): **Tier 2 — Soft Credit Hold & Account Escalation**.
- **`61-90`** (61 to 90 days overdue): **Tier 3 — Hard Shipment Hold & Formal Demand**.
- **`90+`** (91 or more days overdue): **Tier 4 — Third-Party Collections / Legal Review or Write-Off**.

## Section 2: Tier 1 (1–30 Days Overdue) & Tier 2 (31–60 Days Overdue) Actions
- **Tier 1 Protocol (`1-30` days overdue)**:
  - **Day 7 Overdue**: Automated dunning notice sent to the customer's billing email (`ap@...`).
  - **Day 15 Overdue**: AR Specialist performs direct phone/email outreach to confirm invoice receipt and expected remittance date.
- **Tier 2 Protocol (`31-60` days overdue)**:
  - **Day 31 Overdue**: The customer account is automatically placed on **Soft Credit Hold**. New orders require AR Manager review before fulfillment.
  - **Day 45 Overdue**: Escalated to the assigned Commercial Account Manager to obtain a written payment commitment schedule.

<!-- page: 2 -->
## Section 3: Tier 3 (61–90 Days Overdue) Hard Hold & Demand Notice
When any open invoice reaches **61 to 90 days overdue** (`61-90` bucket):
1. **Mandatory Hard Shipment Hold**: Effective at **61 days overdue**, all pending shipments and new order releases for the customer are suspended immediately.
2. **Formal Demand Notice**: If the customer's overdue balance in Tier 3 (`61-90` days overdue) is **`5,000.00 USD` or greater**, the AR Manager must issue a Formal 10-Day Demand Notice warning of external collection escalation.

## Section 4: Tier 4 (90+ Days Overdue) External Collections & Write-Off Thresholds
Any open invoice exceeding **90 calendar days overdue** (`days_overdue > 90`, `90+` aging bucket) is in **Severe Delinquency (Tier 4)** and violates Brightline's maximum aging tolerance:
- **Mandatory External Collections / Legal Referral**: Any invoice or customer account with `days_overdue > 90` and an overdue outstanding balance of **`10,000.00 USD` or more** must be referred to Brightline's external commercial collections agency or legal counsel within 5 business days.
- **Standard Collection Workout (`1,000.00 USD` to `9,999.99 USD`)**: Invoices over 90 days past due with an outstanding balance between `1,000.00 USD` and `9,999.99 USD` require a final settlement demand and VP of Finance review before external referral.
- **Small-Balance Write-Off Review (`< 1,000.00 USD`)**: Uncollected balances over 90 days overdue totaling **less than `1,000.00 USD`** are eligible for bad-debt write-off approval by the Controller rather than external legal action.
