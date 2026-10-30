---
doc_key: DOC-PAY-TERMS
title: Brightline Supply Co. Standard Payment Terms & Billing Policy
category: payment_terms
version: v2.1
effective_date: 2026-01-15
---

<!-- page: 1 -->
## Section 1: Purpose and Scope
This policy establishes the standard commercial payment terms, grace periods, accepted settlement methods, and late-payment fee schedules for all Brightline Supply Co. ("Brightline") accounts-receivable customers. All invoices are denominated and settled in United States Dollars (USD) unless an executive foreign-currency addendum is executed. This policy is synthetic demo documentation for Orvian operations analysis.

## Section 2: Standard Payment Terms by Customer Segment
Brightline assigns every customer to one of three commercial segments (`smb`, `mid_market`, or `enterprise`). Standard net payment terms are measured in calendar days from the invoice `issue_date` to the `due_date`:
- **SMB Segment (`smb`)**: Standard terms are **Net 30** (payment due 30 calendar days after `issue_date`).
- **Mid-Market Segment (`mid_market`)**: Standard terms are **Net 30** (payment due 30 calendar days after `issue_date`).
- **Enterprise Segment (`enterprise`)**: Standard terms are **Net 45** (payment due 45 calendar days after `issue_date`).

Any invoice with an open balance (`outstanding > 0.00 USD`) after its `due_date` is classified as **overdue**, with `days_overdue` calculated as `as_of - due_date`.

<!-- page: 2 -->
## Section 3: Grace Period and Late Payment Fees
Brightline grants a **5-calendar-day grace period** (`days_overdue` between 1 and 5) after the contractual `due_date` to accommodate interbank clearing delays. No collection penalties apply during the 5-day grace period, although the invoice still appears in the `1-30` aging bucket.

Once an unpaid invoice exceeds **15 calendar days overdue** (`days_overdue > 15`), Brightline reserves the right to assess a contractual late finance charge of **1.5% per month** (18.0% APR, pro-rated daily) on the unpaid principal balance. Late fee waivers up to `500.00 USD` may be approved by the Accounts Receivable (AR) Manager for prompt-paying customers experiencing a first-time administrative delay.

## Section 4: Accepted Payment Methods and Restrictions
Brightline accepts four payment methods recorded in the ledger: `ach`, `bank_transfer` (wire), `card`, and `check`. To minimize settlement risk and processing fees, the following mandatory payment method rules apply:
- **Enterprise Segment (`enterprise`)**: Must remit via **`ach`** or **`bank_transfer`**. Paper `check` and `card` settlements are prohibited for Enterprise accounts without Controller sign-off.
- **Paper Check Cap (`check`)**: Paper checks are restricted to invoices with a total of **`10,000.00 USD` or less**. Any single invoice exceeding `10,000.00 USD` must be settled via `ach` or `bank_transfer`.
- **Credit Card Cap (`card`)**: Card payments are accepted for `smb` and `mid_market` invoices up to **`25,000.00 USD`**.
- **Prohibited Instruments**: Brightline does **not** accept cryptocurrency, physical cash, money orders, or third-party bearer notes under any circumstances.
