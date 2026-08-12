# FinAnalyzer Enterprise — Banking and Automated Reporting

## Scope

This enhancement adds **consented Plaid banking connectivity** and **automated PDF/Excel reporting** to FinAnalyzer Enterprise’s v2 double-entry accounting architecture. The banking workflow creates a Link token, exchanges the one-time public token locally, encrypts the resulting access token at rest, and uses a stored cursor for incremental transaction synchronization.[1] [2]

> **Security boundary:** No Plaid client secret, access token, SMTP password, Telegram bot token, local encryption key, or generated financial report may be committed to Git. The repository’s `.gitignore` explicitly excludes these local artifacts.

## Components

| Component | Location | Purpose |
| --- | --- | --- |
| Plaid data models | `core/models.py` | Stores an encrypted Item token, linked account metadata, and idempotent source-to-journal mappings. |
| Secret store | `core/security.py` | Reads a deployment-managed Fernet key or creates a user-scoped local key for encrypted access-token storage. |
| Plaid connector | `core/plaid_connector.py` | Creates Link tokens, exchanges public tokens, pages through Transactions Sync, and maps bank activity into balanced journal entries. |
| Desktop bridge | `core/plaid_link_desktop.py` | Runs a short-lived `127.0.0.1` bridge that opens the user’s browser for Plaid Link consent. |
| Banking UI | `ui/pages/banking.py` | Provides connection status, browser-based linking, and manual synchronization. |
| Management reports | `core/automated_reporting.py` | Builds reports from the double-entry ledger; exports PDF and Excel, preserves schedules locally, and supports optional delivery hooks. |
| Report UI | `ui/pages/reports.py` | Provides statement preview, on-demand export, and creation of a monthly local schedule. |
| Scheduler runner | `scripts/run_scheduled_reports.py` | Evaluates due schedules for Windows Task Scheduler and prints a JSON execution result. |

## Configure Plaid Safely

Create a Plaid developer application, begin in **Sandbox**, and obtain the client ID and secret privately from the provider dashboard. Copy `.env.example` to `.env`, or set the values in the Windows user environment. FinAnalyzer does not contain hard-coded provider credentials.

```powershell
Copy-Item .env.example .env
$env:PLAID_CLIENT_ID = "your_private_client_id"
$env:PLAID_SECRET = "your_private_secret"
$env:PLAID_ENV = "sandbox"
$env:PLAID_COUNTRY_CODES = "US"
```

Start the desktop application and select **Bank Connections**. After selecting **Connect bank with Plaid**, the application opens the consent experience in the default browser. The browser returns only the one-time `public_token` to a temporary local endpoint; FinAnalyzer exchanges it locally and stores only an encrypted access token. Plaid recommends that access tokens be held securely and not exposed in client-side code.[1]

The first synchronization requests transaction changes without a cursor; later runs provide the locally stored cursor. The service saves a new cursor only after every response page is processed successfully, so a failed run does not silently skip data. It handles added, modified, and removed transaction records as part of Plaid’s synchronization model.[2]

### Accounting Treatment of Imported Activity

Bank entries are imported as **balanced journal entries**. Because a bank feed alone does not establish a definitive accounting or tax classification, expense outflows initially post to **Uncategorized bank feed expense** and inflows post to **Uncategorized bank feed income**. The accountant should review, recategorize, and apply any organization-specific controls before relying on reports for statutory, tax, or audit purposes.

| Imported bank event | Initial debit | Initial credit | Required review |
| --- | --- | --- | --- |
| Positive Plaid amount / user outflow | Uncategorized bank feed expense | Linked bank account | Assign the proper expense, asset, liability, or other ledger account. |
| Negative Plaid amount / user inflow | Linked bank account | Uncategorized bank feed income | Confirm whether the item is revenue, financing, transfer, refund, or another event. |
| Modified provider transaction | Revised entry; prior entry is voided | Revised entry; prior entry is voided | Verify the amended transaction and preserve the audit trail. |
| Removed provider transaction | Prior entry marked voided | Prior entry marked voided | Confirm the provider’s removal reason before reporting. |

## Generate PDF and Excel Reports

The **Financial Reports** page is sourced from the enterprise chart of accounts and journal entries rather than demonstration values. It can preview a balance sheet, income statement, trial balance, or management summary. The **Export PDF** and **Export Excel** actions create files under `reports/`.

The management pack includes ledger-backed totals for assets, liabilities, equity, revenue, expenses, net income, and journal-entry count. The Excel workbook contains a trial-balance sheet with formulas; the PDF includes the same management summary. Access tokens and delivery credentials are never exported.

## Automate Reports

Selecting **Schedule Monthly Pack** records a local schedule for PDF and Excel generation at 08:00 UTC on the first day of each month. The schedule service supports daily, weekly, and monthly cadence. A schedule itself stores no provider or mail credentials.

| Delivery model | Benefits | Operational considerations |
| --- | --- | --- |
| **Local on-demand export** | Lowest exposure; no external delivery credential is needed. | A user manually opens or distributes each generated file. |
| **Windows scheduled local export** | Repeatable and automated while reports remain on the device. | Requires Task Scheduler monitoring and a Windows user with access to the project folder. |
| **SMTP or Telegram scheduled delivery** | Distributes reports automatically to approved stakeholders. | Requires documented recipient authorization, secret management, retention controls, and incident handling. |

For the initial commercial rollout, use **Windows scheduled local export**. Enable external delivery only after the business has approved recipient lists, retention, and credential management.

### Configure Windows Task Scheduler

Create a Windows task that runs daily at the required time. The FinAnalyzer runner will determine whether each weekly or monthly schedule is due.

```text
Program/script: C:\FinAnalyzer\.venv\Scripts\python.exe
Add arguments: scripts\run_scheduled_reports.py
Start in: C:\FinAnalyzer
```

The runner uses `data/report_schedules.json` and writes files under `reports/`. SMTP delivery requires `FINANALYZER_SMTP_HOST`, `FINANALYZER_SMTP_PORT`, `FINANALYZER_SMTP_USERNAME`, `FINANALYZER_SMTP_PASSWORD`, and `FINANALYZER_EMAIL_FROM` in the environment of the Windows user that runs the task. Telegram delivery requires `FINANALYZER_TELEGRAM_BOT_TOKEN` and an approved `telegram_chat_id` in the schedule configuration.

## Build the Windows Executable

Install dependencies and run the packaged build script on Windows.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m unittest tests/test_plaid_v2.py tests/test_reporting_v2.py -v
python build_exe.py
```

The `dist/` folder will contain `FinAnalyzer_Enterprise_v2.exe` on Windows. The build script explicitly includes the Plaid connector, browser bridge, security layer, reporting scheduler, and Plaid SDK modules.

## Validation Boundary

The automated tests exercise local encryption, mocked Plaid token exchange and transaction synchronization, balanced journal posting, PDF/Excel generation, and due schedule execution. They do **not** connect to a live financial institution, use any real banking credential, or provide financial, tax, or compliance advice.

## References

[1]: https://plaid.com/docs/link/ "Plaid Link documentation"
[2]: https://plaid.com/docs/transactions/add-to-app/ "Plaid Transactions Sync integration guide"
