---
doc_key: DOC-OPS-SOP
title: Accounts Receivable Ledger, Tax & Cash Application Operating Procedures
category: operating_procedures
version: v1.3
effective_date: 2026-02-15
---

<!-- page: 1 -->
## Section 1: Invoice Issuance, Numbering & Tax Calculation
All Brightline Supply Co. invoices follow strict ledger integrity controls:
- **Monetary Precision**: All ledger calculations (`subtotal_cents`, `tax_cents`, `total_cents`) are stored in exact integer minor units (cents) where `total_cents = subtotal_cents + tax_cents`.
- **Standard Sales Tax Rate**: Unless an active tax-exemption certificate is on file, standard commercial supply invoices apply an **8.0% sales tax** (`tax = subtotal * 0.08`).
- **Invoice Statuses**: Every invoice has one of three statuses:
  - `open`: Issued and awaiting full settlement (`outstanding = total - paid > 0.00 USD`).
  - `paid`: Paid in full (`outstanding == 0.00 USD`).
  - `void`: Cancelled prior to collection; excluded from invoiced revenue and open receivables.

<!-- page: 2 -->
## Section 2: Cash Application & Remittance Posting SLAs
Incoming customer payments must be matched to a specific `invoice_number` and posted to the ledger within the following Service Level Agreements (SLAs):
- **Electronic Settlements (`ach` and `bank_transfer`)**: Posted within **24 hours (1 business day)** of bank settlement receipt.
- **Card Settlements (`card`)**: Posted within **24 hours** of processor batch capture.
- **Paper Checks (`check`)**: Posted within **3 business days** of lockbox receipt.
- **Partial Payments**: Partial payments reduce the invoice's `outstanding` balance (`total - paid`), but the invoice status remains `open` and continues to age from its original `due_date` until the remaining balance reaches `0.00 USD`.

## Section 3: Invoice Voiding Rules & Month-End Close Cutoff
- **Void Eligibility (`status = 'void'`)**: An invoice may be marked `void` **only** if:
  1. Zero cash payments have been applied (`paid == 0.00 USD`), AND
  2. The void occurs within **30 calendar days of `issue_date`**, AND
  3. The Controller approves the void reason (e.g., duplicate issuance or pre-shipment order cancellation).
- **Post-30-Day Adjustments**: Invoices older than 30 days from `issue_date` or with partial payments cannot be voided; they must be adjusted via a formal Credit Memo under `DOC-REFUNDS`.
- **Month-End Close Cutoff**: The AR subledger closes on the **3rd business day of the following calendar month** at 17:00 UTC.
