# FinAnalyzer Enterprise v2.1.0

## Secure Banking and Automated Management Reporting

FinAnalyzer Enterprise v2.1.0 adds a secure Plaid banking workflow and automated PDF/Excel management reporting to the existing double-entry accounting platform. The release keeps the v2 accounting engine intact and introduces bank-feed provenance, encryption, and reporting automation as additive capabilities.

## Included Features

| Area | Delivered capability |
| --- | --- |
| Plaid Link | On-demand browser-based Plaid Link consent through a temporary localhost bridge. |
| Credential protection | Encryption at rest for locally stored access tokens; configuration secrets are supplied only by environment variables. |
| Transaction synchronization | Cursor-based synchronization for added, modified, and removed transactions with no partial cursor persistence on failure. |
| Accounting integration | Imported banking records create balanced journal entries and preserve a source-to-journal audit mapping. |
| Review controls | Unclassified feed events initially post to clearly labelled uncategorized income/expense accounts for accountant review. |
| Reporting | Ledger-backed management summary, balance sheet, income statement, trial balance, PDF export, and Excel export. |
| Automation | Local daily, weekly, or monthly schedules plus a Windows Task Scheduler runner; optional SMTP or Telegram delivery hooks. |
| Desktop UX | New **Bank Connections** navigation page and fully operational **Financial Reports** exports and monthly scheduling control. |

## Security and Compliance Boundary

This release stores access tokens encrypted locally and intentionally excludes credentials from reports and repository files. Production rollout requires the organization to complete its own security review, provider configuration, consent, privacy, retention, accounting-policy, and regional compliance requirements. No live banking account or production Plaid credential was used during validation.

## Validation

Three offline integration tests passed:

```text
✓ Mocked Plaid exchange, encrypted token storage, and balanced journal posting
✓ Ledger-derived PDF and Excel management-pack generation
✓ Due-schedule execution and local output generation
```

## Upgrade

```powershell
pip install -r requirements.txt
python -m unittest tests/test_plaid_v2.py tests/test_reporting_v2.py -v
python build_exe.py
```

Refer to [`docs/V1_1_BANKING_AND_REPORTING.md`](docs/V1_1_BANKING_AND_REPORTING.md) for configuration, security boundaries, Windows scheduling, and operational setup.
