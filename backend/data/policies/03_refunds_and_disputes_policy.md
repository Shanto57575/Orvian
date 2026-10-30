---
doc_key: DOC-REFUNDS
title: Billing Disputes, Credit Memos & Customer Refund Policy
category: refunds
version: v1.2
effective_date: 2026-03-01
---

<!-- page: 1 -->
## Section 1: Billing Dispute Filing Window
Customers must submit formal billing disputes (pricing discrepancies, tax calculation errors, or duplicate billing claims) in writing within **15 calendar days of the invoice `issue_date`**.
- Disputes submitted within the 15-day window pause late-fee accrual on the disputed line item while AR investigates (target resolution SLA: **5 business days**).
- Invoices older than 15 days from `issue_date` are deemed accepted as accurate unless a physical delivery shortage is documented on the signed carrier bill of lading.

## Section 2: Defective Goods & Return Merchandise Authorization (RMA)
Claims for damaged or defective physical supplies must be filed within **30 calendar days of the invoice `issue_date`**.
- An approved RMA number is required before returning merchandise.
- Standard restocking fee for non-defective discretionary returns is **15% of the item subtotal**, waived only when the return results from a Brightline fulfillment error.

<!-- page: 2 -->
## Section 3: Credit Memo vs. Cash Refund Rules
- **Unpaid / Partially Paid Invoices**: Valid adjustments on open invoices are resolved via a **Credit Memo** applied directly against the open invoice balance (or by marking an erroneous uncollected invoice `void` under `DOC-OPS-SOP`).
- **Paid Invoices (`status = 'paid'`)**: When a customer has already remitted cash in excess of the adjusted total:
  - Overpayments or credits **under `500.00 USD`** default to an account credit applied to the customer's next invoice unless the customer requests a cash refund in writing.
  - Overpayments or approved refunds of **`500.00 USD` or more** are eligible for direct cash refund via `ach` or `bank_transfer` within **10 business days** of approval.

## Section 4: Refund and Credit Approval Matrix
All credit memos, billing write-downs, and cash refunds require documented authorization based on the total adjustment amount in USD:
- **Up to `2,500.00 USD`**: Approved by the **Accounts Receivable (AR) Manager**.
- **`2,500.01 USD` to `25,000.00 USD`**: Requires joint approval by the **Controller** or **VP of Finance**.
- **Above `25,000.00 USD`**: Requires explicit sign-off by the **Chief Financial Officer (CFO)**.
