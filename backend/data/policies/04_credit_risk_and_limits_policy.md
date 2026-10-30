---
doc_key: DOC-CREDIT
title: Commercial Credit Risk & Exposure Limits Policy
category: credit_policy
version: v2.0
effective_date: 2026-01-15
---

<!-- page: 1 -->
## Section 1: Standard Credit Exposure Limits by Segment
Brightline Supply Co. assigns a maximum aggregate open accounts-receivable credit limit (`outstanding` balance across all open invoices) based on the customer's commercial segment:
- **SMB Segment (`smb`)**: Standard aggregate credit limit of **`15,000.00 USD`**.
- **Mid-Market Segment (`mid_market`)**: Standard aggregate credit limit of **`50,000.00 USD`**.
- **Enterprise Segment (`enterprise`)**: Standard aggregate credit limit of **`200,000.00 USD`**.

A customer's current credit utilization is defined as their total `outstanding` balance across all open invoices divided by their segment credit limit.

<!-- page: 2 -->
## Section 2: Credit Breach & Automatic Credit Suspension Triggers
A customer is in **Credit Policy Violation** and subject to automatic credit suspension if **any** of the following conditions occur:
1. **Credit Limit Breach**: Total `outstanding` balance exceeds **100%** of the segment credit limit (`> 15,000.00 USD` for `smb`, `> 50,000.00 USD` for `mid_market`, or `> 200,000.00 USD` for `enterprise`).
2. **High Overdue Ratio**: Total `overdue_outstanding` balance exceeds **50%** of the customer's segment credit limit (`> 7,500.00 USD` for `smb`, `> 25,000.00 USD` for `mid_market`, or `> 100,000.00 USD` for `enterprise`).
3. **Aged Delinquency Trigger**: The customer has **any single open invoice more than 60 calendar days overdue** (`days_overdue > 60`, corresponding to the `61-90` or `90+` aging buckets).

## Section 3: Credit Reinstatement & Limit Increase Procedure
- **Reinstatement after Suspension**: To lift a credit suspension, the customer must pay down all invoices over 30 days overdue (`days_overdue > 30`) and reduce total `outstanding` exposure below **80%** of their segment limit.
- **Temporary Credit Limit Increase**: Prompt-paying customers (`overdue_outstanding == 0.00 USD`) may request a temporary 60-day credit limit uplift of up to **25%** above their standard segment cap with Controller approval, or up to **50%** with CFO approval.
