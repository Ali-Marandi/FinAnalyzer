# 🏢 FinAnalyzer Enterprise v2.0.0

<p align="center">
  <strong>Professional Financial Analytics, Accounting & ERP Desktop Suite</strong><br>
  <em>Enterprise-grade financial management competing with QuickBooks, Xero, Fathom & Sage</em>
</p>

---

## 🚀 Overview

**FinAnalyzer Enterprise** is a commercial-grade desktop financial analysis application built with Python and PySide6 (Qt6). It provides comprehensive double-entry bookkeeping, AI-powered forecasting, professional financial reporting, and enterprise security — all in a beautiful modern interface.

### Key Differentiators
- **True Double-Entry Accounting Engine** with GAAP/IFRS compliance
- **AI/ML Financial Forecasting** using scikit-learn (Polynomial Regression, IsolationForest)
- **50+ Financial KPIs** calculated in real-time
- **Multi-Entity Support** for corporate groups and holding companies
- **AES-256 Encrypted Database** with audit trail compliance
- **Professional Reports** (Balance Sheet, P&L, Cash Flow, Trial Balance)
- **Beautiful Dark/Light UI** with Fluent Design principles

---

## 📸 Features

### 💎 Executive Dashboard
- Real-time KPI summary cards with trend indicators
- Interactive revenue & expense charts (Matplotlib embedded)
- Recent transactions audit table
- Period selector (Month, Quarter, Year, Custom)

### 💳 Transaction Management
- Sortable/filterable transaction table with pagination
- Add/Edit/Delete with full validation
- Bulk import from CSV, Excel, OFX, QIF bank formats
- Category & account filtering
- Export to CSV, Excel (with formulas), PDF

### 📚 Chart of Accounts
- Hierarchical tree view (Assets → Liabilities → Equity → Revenue → Expenses)
- Account type indicators with color coding
- Balance display per account
- Add/Edit account dialogs with validation

### 📑 Professional Financial Reports
- **Balance Sheet** — Assets = Liabilities + Equity
- **Income Statement (P&L)** — Revenue, COGS, Operating Expenses, Net Income
- **Cash Flow Statement** — Operating, Investing, Financing activities
- **Trial Balance** — Debit/Credit verification
- Export to PDF (publication-grade) and Excel (with SUM formulas)

### 🤖 AI Forecasting & Analytics
- Cash flow forecasting (3, 6, 12 months horizon)
- Polynomial regression with confidence intervals
- Anomaly detection (IsolationForest) for fraud/unusual transactions
- What-if scenario simulator with interactive sliders
- Budget vs Actual variance analysis

### ⚙️ Enterprise Settings
- Company profile management (multi-entity)
- User management with RBAC (Admin, Accountant, Viewer)
- Dark/Light theme switching
- Encrypted database backup & restore
- License key management
- Two-factor authentication (2FA) support

---

## 🏗️ Architecture

```
FinAnalyzer_v2/
├── main.py                          # Application entry point
├── requirements.txt                 # Python dependencies
├── core/                            # Business logic layer
│   ├── models.py                    # SQLAlchemy ORM (12 enterprise models)
│   ├── database.py                  # Database manager (SQLite, pooling, WAL)
│   ├── accounting_engine.py         # Double-entry bookkeeping engine
│   ├── analytics.py                 # AI/ML forecasting & KPIs
│   ├── import_export.py             # Multi-format data I/O
│   ├── security.py                  # Auth, encryption, RBAC, licensing
│   └── notifications.py            # Email, in-app alerts, scheduling
├── ui/                              # Presentation layer (PySide6)
│   ├── theme.py                     # Dark/Light theme engine (QSS)
│   ├── main_window.py              # Main application window
│   ├── pages/                       # Application pages
│   │   ├── dashboard.py            # Executive dashboard
│   │   ├── transactions.py         # Transaction management
│   │   ├── accounts.py             # Chart of accounts
│   │   ├── reports.py              # Financial reports
│   │   ├── forecasting.py          # AI forecasting
│   │   └── settings.py            # System settings
│   ├── widgets/                     # Reusable UI components
│   │   ├── card_widget.py          # Summary cards
│   │   └── chart_widget.py         # Matplotlib chart wrapper
│   └── dialogs/                     # Modal dialogs
│       └── transaction_dialog.py   # Transaction entry form
└── dist/                            # Built executables
    └── FinAnalyzer_Enterprise_v2   # Standalone binary
```

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| GUI Framework | PySide6 (Qt6) |
| Database | SQLAlchemy 2.0 + SQLite (WAL mode) |
| Charts | Matplotlib (embedded in Qt) |
| AI/ML | scikit-learn (LinearRegression, IsolationForest) |
| Data Processing | Pandas, NumPy |
| Security | bcrypt, cryptography (Fernet/AES-256) |
| Reports | ReportLab (PDF), openpyxl (Excel) |
| Packaging | PyInstaller |
| Bank Formats | ofxparse, qifparse |

---

## 📦 Installation

### From Release (Recommended)
1. Download `FinAnalyzer_Enterprise_v2` from the [Releases](../../releases) page
2. Run the executable directly (no installation required)

### From Source
```bash
git clone https://github.com/Ali-Marandi/FinAnalyzer.git
cd FinAnalyzer
pip install -r requirements.txt
python main.py
```

### Build EXE (Windows)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name=FinAnalyzer_Enterprise_v2 --add-data="core;core" --add-data="ui;ui" main.py
```

---

## 🔐 Security Features

- **bcrypt Password Hashing** — Industry-standard password protection
- **Fernet Symmetric Encryption (AES-256)** — All sensitive data encrypted at rest
- **Role-Based Access Control (RBAC)** — Admin, Accountant, Viewer roles
- **HMAC-SHA256 License Keys** — Cryptographically signed enterprise licenses
- **Comprehensive Audit Trail** — Every action logged for compliance
- **SQLite WAL Mode** — ACID-compliant transactions with high concurrency

---

## 📊 Financial KPIs (50+)

The analytics engine calculates institutional-grade financial metrics including:

| Category | Metrics |
|----------|---------|
| Liquidity | Current Ratio, Quick Ratio, Cash Ratio, Working Capital |
| Leverage | Debt-to-Equity, Debt-to-Assets, Equity Multiplier, Interest Coverage |
| Profitability | Net Profit Margin, ROA, ROE, Operating Margin, Gross Margin |
| Operational | Asset Turnover, Capital Intensity, Revenue Growth Rate |
| Forecasting | Cash Flow Projections, Trend Analysis, Anomaly Scores |

---

## 🏢 Enterprise Capabilities

- **Multi-Entity Support** — Manage multiple companies/branches in one database
- **Hierarchical Chart of Accounts** — Parent-child account relationships
- **Fiscal Year Management** — Period locking, year-end closing entries
- **Multi-Currency** — Real-time exchange rate conversion
- **Invoice Management** — AR/AP tracking with status workflow
- **Asset Depreciation** — Straight-line and declining balance methods
- **Bank Reconciliation** — OFX/QIF import with auto-matching

---

## 📄 License

Enterprise Commercial License. © 2026 FinAnalyzer Corp. All rights reserved.

---

## 👨‍💻 Author

Developed by **Ali Marandi** — Enterprise Financial Software Engineer

---

*Built with ❤️ for finance professionals who demand the best.*
