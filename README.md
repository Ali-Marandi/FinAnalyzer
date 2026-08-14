# FinAnalyzer Enterprise

> **Evidence-first financial controls for bank reconciliation and close readiness.**

FinAnalyzer Enterprise is a Windows desktop application for finance teams that need a controlled, auditable path from bank activity to period close. It is designed to complement an accounting system of record—not replace a full ERP, payroll, payments, or tax platform.

The current public release is **v2.7.0 — Controlled Bank Reconciliation**. It adds a dedicated review workspace, separation-of-duties enforcement, and close-readiness controls to the enterprise security and accounting foundations already in the product.

## Why FinAnalyzer

A bank feed is not evidence of a completed financial decision. Finance teams need to know which items remain unreviewed, who owns an exception, whether the reviewer is independent, whether the period is still open, and whether the close remains safe to execute.

FinAnalyzer turns those questions into an enforceable workflow:

| Control | What it provides |
|---|---|
| **Controlled reconciliation queue** | New or revised bank-feed mappings return to `needs_review`; raw provider payloads are not exposed in the desktop review queue. |
| **Contra-only classification** | Reconciliation updates only the eligible contra account on an existing balanced journal entry; it does not create a new entry or alter the amount, bank line, date, or line count. |
| **Separation of duties** | The person who flags an exception cannot resolve the same exception, even when both permissions exist. |
| **MFA and company scoping** | Sensitive actions require a valid authenticated principal, relevant permission, company membership, and fresh MFA. |
| **Close Readiness** | Open bank-reconciliation items block period close at both the request and approval/execution control points. |
| **Tamper-evident evidence** | Structured audit events are protected by an HMAC-SHA256 chain; the Windows signing key is protected with DPAPI when available. |

## Current Product Scope

### v2.7.0 — Controlled Bank Reconciliation

Each bank-feed mapping has an explicit reconciliation state:

| State | Meaning |
|---|---|
| `needs_review` | Human classification is required before close. |
| `matched` | The eligible contra classification has been approved. |
| `exception` | The item requires independent resolution. |
| `removed` | The provider removed the item; it is no longer in the review queue. |

A user with `bank.reconcile.match` can classify an eligible item to an active, in-scope contra account. A user with `bank.reconcile.exception.resolve` can resolve an exception only when they are not the person who flagged it. The service layer, not the UI, enforces these controls.

See [release notes for v2.7.0](RELEASE_NOTES_v2.7.0.md) for detailed behavior and constraints.

### Enterprise Control Foundation

| Domain | Current capability |
|---|---|
| Identity | Microsoft Entra OIDC/PKCE and MSAL-based SSO context, with MFA freshness checks for sensitive actions. |
| Authorization | Deny-by-default authorization service with company-scoped memberships and explicit permissions. |
| Period close | Request/approval separation, atomic execution, Close Readiness gates, and audit evidence. |
| Audit | Structured HMAC-SHA256 event chain with verification support and DPAPI-protected audit signing-key storage on Windows. |
| Connectivity | Plaid-bank-feed integration with atomic synchronization behavior and controlled review of new/revised mappings. |
| Reporting | PDF and Excel generation for financial reporting workflows. |
| Packaging | PyInstaller-based Windows build flow and signed-release CI/CD path. |

## Product Direction

The next product direction is **Statement Reconciliation Intelligence**, delivered only through controlled milestones. It is a roadmap, not a shipped capability.

| Planned milestone | Intended outcome | Release gate |
|---|---|---|
| **v2.8.0-a** | Statement import, deterministic matching, immutable decision history, idempotency, and optimistic concurrency control. | Data migration, idempotency, audit, restore, and finance UAT evidence. |
| **v2.8.0-b** | Explainable candidate suggestions, split matching, active-allocation protection, and policy-based approvals. | Allocation invariants, independent approval, SoD negative tests, and concurrency evidence. |
| **v2.8.0-c** | Certification balance, exception SLA, evidence export, and a second Close Readiness check. | Controller sign-off, failure injection, evidence verification, and rollback readiness. |

AI is intended to prepare candidates, explanations, and drafts. It is not intended to autonomously post financial changes. Permission, fresh MFA, policy, separation of duties, human approval, and audit evidence remain the decision boundary.

## Architecture

```text
FinAnalyzer
├── core/
│   ├── authorization.py          # Deny-by-default, company-scoped authorization
│   ├── audit.py                  # HMAC audit chain and signing-key protection
│   ├── bank_reconciliation.py    # Controlled reconciliation and exception workflow
│   ├── database.py               # SQLAlchemy persistence and migrations
│   ├── period_close.py            # Controlled close and readiness gates
│   ├── plaid_connector.py         # Bank-feed synchronization
│   └── models.py                  # Domain models and reconciliation state
├── ui/
│   ├── main_window.py             # Desktop shell and principal propagation
│   └── pages/bank_reconciliation.py
├── tests/
│   └── test_bank_reconciliation_v27.py
├── .github/workflows/
│   └── release-sign.yml           # Signed Windows release workflow
└── docs/
```

## Technology

| Component | Technology |
|---|---|
| Language | Python 3.12 |
| Desktop UI | PySide6 / Qt 6 |
| Persistence | SQLAlchemy 2.0 with SQLite/WAL in the current release |
| Identity | MSAL, OIDC/PKCE, Microsoft Entra integration |
| Security | bcrypt, cryptography/Fernet, Windows DPAPI where available |
| Audit integrity | HMAC-SHA256 chain and signing-key verification |
| Reporting | ReportLab, openpyxl, fpdf2 |
| Packaging | PyInstaller and Windows signing CI/CD |

## Installation

### From a release

Download the Windows executable from the [Releases](https://github.com/Ali-Marandi/FinAnalyzer/releases) page. The latest v2.7.0 release is available at [v2.7.0](https://github.com/Ali-Marandi/FinAnalyzer/releases/tag/v2.7.0).

### From source

```bash
git clone https://github.com/Ali-Marandi/FinAnalyzer.git
cd FinAnalyzer
python -m pip install -r requirements.txt
python main.py
```

### Run the test suite

```bash
python -m unittest discover -s tests -p "test_*.py"
```

## Commercial and Global Readiness

FinAnalyzer is pursuing a controller-led, evidence-first close-control position. The first commercial priority is to validate the workflow with design partners, rather than expand indiscriminately into ERP, payroll, payments, or tax functionality.

The strategy, commercial validation plan, and v2.8.0 control designs are documented in:

- [Global Product and Commercial Strategy](docs/FINANALYZER_GLOBAL_PRODUCT_AND_COMMERCIAL_STRATEGY_FA.md)
- [90-Day Commercial Validation Plan](docs/FINANALYZER_90_DAY_COMMERCIAL_VALIDATION_PLAN_FA.md)
- [v2.8.0 Commercial Intelligence Roadmap](docs/V2_8_COMMERCIAL_INTELLIGENCE_ROADMAP_FA.md)
- [v2.7.0 Bank Reconciliation Code Review](docs/V2_7_BANK_RECONCILIATION_CODE_REVIEW_FA.md)

## Security and Compliance Notice

FinAnalyzer provides technical controls intended to support controlled finance workflows. It does not by itself certify compliance with GAAP, IFRS, SOX, GDPR, tax rules, banking rules, or any jurisdiction-specific regulatory obligation. Deployment, policy configuration, retention, legal review, and operational controls remain the customer’s responsibility.

## License

See the repository license and release terms before deploying in production.

---

Developed by **Ali Marandi**.
