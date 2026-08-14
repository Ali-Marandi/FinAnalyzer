# راهنمای اجرای پایلوت، Go/No-Go، UAT/CI و اسلایدهای امنیت v2.8.0-a

**تاریخ مرجع:** ۱۴ اوت ۲۰۲۶
**وضعیت:** این سند یک specification اجرایی برای پایلوت و نمونه کد آزمون است. قابلیت‌های v2.8.0-a تا زمان پیاده‌سازی، آزمون و UAT، قابلیت منتشرشده یا کنترل انطباقی تأییدشده نیستند.[1]

> **قاعده اصلی:** یک پایلوت موفق، demo زیبا یا تست سبز جداگانه نیست. پایلوت فقط وقتی وارد workflow محدود می‌شود که evidence فنی، evidence امنیتی و UAT مالی برای همان scope، به یک تصمیم Go/No-Go قابل بازبینی وصل شوند.

## ۱. مکانیزم اجرای پایلوت برای مصاحبه‌های اولویت‌دار

### ۱.۱. مدل تصمیم مرحله‌ای

| گیت | زمان تقریبی | شرط ورود | فعالیت مجاز | evidence خروج | تصمیم |
|---|---:|---|---|---|---|
| G0 — Discovery Fit | روز ۰ تا ۷ | مصاحبه‌شونده نزدیک به workflow و issue واقعی دارد | گفت‌وگو، concept card، artefact حذف‌هویت‌شده | Interview record، scorecard، stakeholder map | ادامه یا ثبت learning-only |
| G1 — Charter & Security Baseline | روز ۷ تا ۱۴ | champion و workflow منتخب وجود دارد | تکمیل Charter، Data Map، Role/SoD Matrix و Security Discovery | scope، data classification، ownerها، exit rule | ورود به fixture یا No-Go |
| G2 — Technical Fixture | روز ۱۴ تا ۲۸ | داده مصنوعی/ماسک‌شده و UAT matrix تأیید شده‌اند | import/match/CAS/negative path روی fixture | test reports، audit samples، integrity report | ورود به UAT یا نقص/بازگشت |
| G3 — Financial UAT | روز ۲۸ تا ۴۵ | گیت‌های فنی و امنیتی G2 پاس شده‌اند | controller سناریوهای match/conflict/no-mutation را تأیید می‌کند | UAT checklist، defect list، sign-off یا rejection | workflow محدود یا remediation |
| G4 — Limited Workflow | روز ۴۵ تا ۹۰ | UAT بدون blocker بحرانی و rollback owner مشخص است | یک workflow محدود، telemetry و review هفتگی | weekly evidence review، risk/change log | Convert / Extend / Pivot / Stop |

هر یک از ده مصاحبه، فقط در صورت score حداقل ۹ از ۱۲، نبود No-Go و وجود next action تاریخ‌دار می‌تواند از G0 به G1 برود. امتیاز نباید جای judgment ذی‌نفع مالی/امنیتی را بگیرد؛ فقط یک فیلتر قابل‌توضیح برای اولویت‌گذاری است.[2]

### ۱.۲. معیارهای Go/No-Go

| طبقه تصمیم | معیار | اقدام لازم |
|---|---|---|
| **Go به G1** | workflow تکرارشونده، champion، مسیر buyer، داده حداقلی ممکن و fit با Control Layer | Charter و Security Discovery را شروع کنید |
| **Go به G2** | Charter، Data Map، Role/SoD Matrix، UAT Fixture Matrix و escalation contacts کامل هستند | تنها fixture کنترل‌شده اجرا شود |
| **Go به G3** | import/provenance، deterministic match، idempotency، CAS، no-ledger-mutation و HMAC/SoD negative path پاس شده‌اند | Controller UAT را برنامه‌ریزی کنید |
| **Go به G4** | UAT مالی sign-off یا acceptance محدود، rollback owner و incident path وجود دارند؛ critical/high blocker باز نیست | workflow محدود با review هفتگی فعال شود |
| **Convert در روز ۹۰** | evidence ارزش، champion، buyer و procurement path واقعی هستند | قرارداد و roadmap مشترک تدوین شود |
| **No-Go فوری** | HMAC نامعتبر، bypass موفق SoD/MFA، mutation ناخواسته ledger، نقض company scope، داده بدون توافق یا rollback نامشخص | workflow را متوقف، incident/risk record را ثبت و fix+retest کنید |
| **Pivot / Stop** | pain، buyer، data readiness یا fit کنترل تکرارشونده تأیید نشود | feature build را pause کنید و segment/problem را بازنگری نمایید |

## ۲. نمونه کد آزمون خودکار برای ردیف‌های UAT مالی

### ۲.۱. مرز اجرای کد

کد زیر، **نمونه پیشنهادی** برای توسعه آزمون‌های جاری v2.7.0 است. سه کنترل اول بر سرویس موجود قابل اجرا هستند: SoD exception، locked period و audit-chain verification. سناریوهای v2.8.0-a مانند CSV import، deterministic statement matching، idempotency و CAS باید تنها بعد از پیاده‌سازی سرویس/مدل مربوطه به suite اصلی افزوده شوند. از mockی که invariants را دور می‌زند برای اثبات گیت مالی استفاده نکنید.[3] [4]

```python
# tests/test_design_partner_uat_controls.py
# نمونه؛ از fixture و helperهای test_bank_reconciliation_v27.py استفاده می‌کند.

from __future__ import annotations

from sqlalchemy import select

from core.audit import AuditLog
from core.bank_reconciliation import BankReconciliationError
from core.models import BankReconciliationStatus, JournalEntry
from tests.test_bank_reconciliation_v27 import BankReconciliationV27Tests


class DesignPartnerUatControlTests(BankReconciliationV27Tests):
    """UAT control rows that remain executable against the v2.7.0 service."""

    def _entry_snapshot(self) -> tuple[tuple[int, int, str, str], ...]:
        with self.database.get_session() as session:
            mapping = self._mapping(session)
            entry = session.get(JournalEntry, mapping.journal_entry_id)
            return tuple(sorted(
                (line.id, line.account_id, str(line.debit), str(line.credit))
                for line in entry.transactions
            ))

    def test_uat_sod_denial_preserves_exception_and_ledger(self) -> None:
        before = self._entry_snapshot()
        self.service.mark_exception(
            self.company_id,
            "reconciliation-tx-001",
            "UAT exception: invoice evidence missing",
            self.manager,
        )

        with self.assertRaises(BankReconciliationError):
            self.service.resolve_exception(
                self.company_id,
                "reconciliation-tx-001",
                self.expense_account_id,
                self.manager,  # same actor as exception flagger
                "UAT attempted self-resolution",
            )

        self.assertEqual(self._entry_snapshot(), before)
        with self.database.get_session() as session:
            mapping = self._mapping(session)
            denied = session.scalar(select(AuditLog).where(
                AuditLog.action == "bank.reconciliation.sod_denied"
            ))
            self.assertEqual(mapping.reconciliation_status, BankReconciliationStatus.EXCEPTION)
            self.assertIsNotNone(denied)
            self.assertEqual(denied.outcome, "denied")
            self.assertTrue(self.audit_logger.verify_chain(session).valid)

    def test_uat_independent_resolver_can_complete_same_exception(self) -> None:
        self.service.mark_exception(
            self.company_id,
            "reconciliation-tx-001",
            "UAT exception: document review required",
            self.manager,
        )
        self.service.resolve_exception(
            self.company_id,
            "reconciliation-tx-001",
            self.expense_account_id,
            self.controller,  # independent actor
            "Controller reviewed the UAT evidence",
        )

        with self.database.get_session() as session:
            mapping = self._mapping(session)
            self.assertEqual(mapping.reconciliation_status, BankReconciliationStatus.MATCHED)
            self.assertEqual(mapping.reconciled_by_user_id, self.controller_id)
            self.assertTrue(self.audit_logger.verify_chain(session).valid)
```

برای ردیف locked period، تست موجود `test_locked_period_cannot_be_reclassified` باید در UAT suite نگه داشته شود. این تست نشان می‌دهد error نباید status را از `needs_review` خارج کند و chain audit باید معتبر بماند. برای MFA freshness و company scope، پس از بازبینی exception classهای authorization، negative tests را با principal دارای `mfa_at` قدیمی و mapping شرکت دوم اضافه کنید؛ نام دقیق exception باید از implementation واقعی گرفته شود، نه از فرض این سند.[3]

### ۲.۲. نمونه آزمون‌های پیشنهادی پس از پیاده‌سازی v2.8.0-a

```python
# tests/test_statement_reconciliation_v28a.py
# این API نام‌ها specification هستند و تا زمان پیاده‌سازی نباید به CI اصلی افزوده شوند.

class StatementReconciliationV28ATests(unittest.TestCase):
    def test_replaying_same_idempotency_key_creates_one_decision(self):
        first = self.service.submit_deterministic_match(
            command=self.command(idempotency_key="8e3f..."),
        )
        replay = self.service.submit_deterministic_match(
            command=self.command(idempotency_key="8e3f..."),
        )
        self.assertEqual(replay.decision_id, first.decision_id)
        self.assertEqual(self.repository.active_decision_count(), 1)

    def test_two_reviewers_cannot_overwrite_same_case_version(self):
        winner = self.service.approve(
            command=self.command(expected_case_version=7), actor=self.reviewer_a,
        )
        with self.assertRaises(ConcurrentDecisionConflict):
            self.service.approve(
                command=self.command(expected_case_version=7), actor=self.reviewer_b,
            )
        self.assertEqual(self.repository.current_case_version(), 8)
        self.assertEqual(self.repository.current_decision_id(), winner.decision_id)
```

هر دو نمونه باید علاوه بر assertion business state، این invariantها را بررسی کنند: یک HMAC event یا زنجیره معتبر، absence of duplicate decision/allocation، policy version ثبت‌شده، و عدم mutation ناخواسته ledger. این‌ها specification آزمون v2.8.0-a هستند؛ نه ادعا درباره APIهای موجود.[1]

## ۳. یکپارچه‌سازی با GitHub Actions

workflow فعلی signed release، پیش از build و signing، `python -m unittest discover -s tests -v` را اجرا می‌کند. گیت Design Partner باید ابتدا روی Pull Request اجرا شود تا defect قبل از tag release دیده شود؛ signed release همچنان آخرین خط دفاع است.[5]

```yaml
# .github/workflows/control-uat.yml
name: Control UAT Gate

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  bank-reconciliation-controls:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - name: Check out source
        uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09

      - name: Set up Python 3.12
        uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: requirements-windows-build.txt

      - name: Install test dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -r requirements-windows-build.txt

      - name: Run existing bank-reconciliation regression gate
        run: |
          python -m unittest discover -s tests -p "test_bank_reconciliation_v27.py" -v

      # فعال‌سازی پس از پیاده‌سازی واقعی v2.8.0-a:
      # - name: Run v2.8.0-a statement control gate
      #   run: python -m unittest discover -s tests -p "test_statement_reconciliation_v28a.py" -v
```

تا زمان نصب/پیکربندی dependencyهای لازم در Linux CI، اگر regression class به‌دلیل `PLAID_SDK_AVAILABLE` skip شود، job نباید به اشتباه evidence کامل تلقی شود. گزارش CI باید صریحاً تعداد `skipped` را بررسی کند و test environment باید به‌گونه‌ای آماده شود که کنترل‌های مورد نیاز واقعاً اجرا، نه صرفاً skip، شوند. اگر تنها Windows build environment قابلیت اجرای dependency معین را دارد، همین job باید روی Windows یا matrix معتبر اجرا شود؛ gate نباید به‌خاطر راحتی runner از پوشش واقعی صرف‌نظر کند.[3] [5]

## ۴. متن کامل اسلایدهای چک‌لیست امنیت و تست‌های منفی v2.8.0-a

### اسلاید A — امنیت پایلوت با Data Minimization شروع می‌شود

**متن روی اسلاید**

| پیش از discovery | در fixture | پیش از workflow محدود |
|---|---|---|
| Charter، Data Map، owner و consent | synthetic/masked data، test actor، MFA و company scope | UAT sign-off، rollback owner، incident path |
| بدون raw bank file یا secret | بدون UI bypass یا hidden retry | بدون critical/high blocker باز |

**اسکریپت سخنران**

«امنیت Design Partner از ابزار یا questionnaire شروع نمی‌شود؛ از این شروع می‌شود که چه داده‌ای اصلاً لازم نداریم. در discovery، داده production، token و credential وارد نمی‌شوند. در fixture، test actor، company scope و MFA به‌صورت کنترل‌شده بررسی می‌شوند. و پیش از workflow محدود، باید UAT مالی، rollback owner و مسیر incident روشن باشند. اگر یکی از این لایه‌ها ناقص باشد، سرعت بیشتر ارزش ندارد؛ پایلوت متوقف می‌شود.»

### اسلاید B — مسیر منفی، Evidence کنترل است

**متن روی اسلاید**

```text
Flagger → Resolve own exception → DENY
                         │
                         ├─ Ledger: بدون mutation
                         ├─ Status: exception باقی می‌ماند
                         └─ Audit: sod_denied + HMAC-valid

Independent reviewer → Resolve → policy-bound success
```

**اسکریپت سخنران**

«ما کنترل را با happy path ثابت نمی‌کنیم. سناریوی مهم این است که همان فردی که exception را ثبت کرده، بخواهد آن را حل کند. انتظار محصول این است که سرویس، نه فقط UI، درخواست را رد کند؛ دفتر تغییر نکند؛ status در exception بماند؛ و denial در audit chain ثبت شود. سپس reviewer مستقل می‌تواند همان item را طبق permission، MFA و policy تکمیل کند. این تفاوت میان یک فرم approval و یک کنترل قابل دفاع است.»

### اسلاید C — پنج تست منفی پیش از UAT مالی

**متن روی اسلاید**

1. MFA قدیمی یا permission ناکافی → deny، بدون mutation
2. actor از company دیگر → deny، بدون data exposure
3. exception توسط flagger حل می‌شود → SoD denial و HMAC evidence
4. دوره قفل، pending یا removed → state/ledger بدون تغییر
5. retry یا conflict هم‌زمان → یک نتیجه یا conflict قابل‌فهم، نه overwrite

**اسکریپت سخنران**

«این پنج تست منفی، کوتاه‌ترین اثبات ما از این هستند که کنترل در جای درست اجرا می‌شود. هیچ‌کدام نباید صرفاً به دکمه disabled در UI متکی باشند. ما به result service، state پایگاه‌داده، ledger snapshot و audit evidence نگاه می‌کنیم. برای v2.8.0-a، retry باید idempotent باشد و concurrency باید conflict شفاف بدهد؛ این دو قابلیت تا پیاده‌سازی کامل، گیت پیشنهادی‌اند، نه claim محصول جاری.»

### اسلاید D — UAT مالی یک Sign-off کلی نیست

**متن روی اسلاید**

| ردیف UAT | expectation | evidence | مالک |
|---|---|---|---|
| Import / Provenance | نتیجه قابل‌پیش‌بینی و hash | manifest + rejected reason | QA + analyst |
| Exact Match | فقط reference+amount+currency | expected-vs-actual | Controller + QA |
| No Mutation | دفتر خارج از مسیر مجاز تغییر نمی‌کند | before/after report | Controller |
| SoD / HMAC | denial حفظ و chain معتبر | verify_chain + event | Security + QA |
| CAS / Retry | duplicate یا overwrite وجود ندارد | conflict / idempotency log | Engineering + QA |

**اسکریپت سخنران**

«UAT مالی یعنی controller یک صفحه را تأیید کند؟ نه. هر ردیف باید input، actor، expected state، expected ledger state، audit evidence و signatory داشته باشد. Import و provenance، match قطعی، no mutation، SoD/HMAC و سپس CAS/retry، هر یک evidence جدا نیاز دارند. اگر یک ردیف بحرانی Blocked یا Not Run است، Go نداریم؛ حتی اگر demo ظاهراً خوب کار کند.»

### اسلاید E — Go فقط وقتی صادر می‌شود که Evidence کامل باشد

**متن روی اسلاید**

```text
Technical Gate + Security Gate + Financial UAT + Rollback Readiness
                                │
                                ▼
                         Limited Workflow Go
```

**اسکریپت سخنران**

«تصمیم Go از یک مالک یا یک معیار نمی‌آید. گیت فنی نشان می‌دهد behavior درست است؛ گیت امنیت نشان می‌دهد داده، identity و audit قابل کنترل‌اند؛ UAT مالی نشان می‌دهد controller به outcome اعتماد دارد؛ و rollback readiness نشان می‌دهد در failure چه کسی و چگونه workflow را متوقف می‌کند. نبود هر یک از این چهار جزء، به معنای No-Go یا remediation است. Design Partner باید این شفافیت را نشانه بلوغ محصول ببیند، نه کندی تیم.»

## منابع

[1]: /home/ubuntu/FinAnalyzer_User/docs/V2_8_HMAC_AUDIT_RELEASE_GATES_FA.md "HMAC Audit، SoD و گیت‌های کیفیت v2.8.0"

[2]: /home/ubuntu/FinAnalyzer_User/docs/FINANALYZER_V28A_DESIGN_PARTNER_GATES_AND_INTERVIEW_PLAYBOOK_FA.md "گیت‌های v2.8.0-a و برنامه مصاحبه Design Partner"

[3]: /home/ubuntu/FinAnalyzer_User/tests/test_bank_reconciliation_v27.py "آزمون‌های regression Bank Reconciliation v2.7.0"

[4]: /home/ubuntu/FinAnalyzer_User/core/bank_reconciliation.py "BankReconciliationService v2.7.0"

[5]: /home/ubuntu/FinAnalyzer_User/.github/workflows/release-sign.yml "Signed Windows Release workflow"
