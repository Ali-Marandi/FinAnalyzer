# PostgreSQL Active Allocation Reservation، Deadlock، گیت CI/CD و اسکریپت Split Matching v2.8.0

## وضعیت و مرز پیاده‌سازی

این سند، طراحی پیشنهادی برای لایه persistence و آزمون‌های v2.8.0-a/b است. پروژه موجود در v2.7.0 از SQLite، `BankReconciliationService`، HMAC audit، MFA و SoD برای بانک-feed reconciliation استفاده می‌کند؛ جدول‌های `ReconciliationCase`، `ActiveAllocationReservation` و Split Matching هنوز در مخزن پیاده‌سازی نشده‌اند.[1] [2]

> **مرز مهم:** unique reservation، CAS و idempotency برای جلوگیری از conflict در جریان تصمیم به‌کار می‌روند. آن‌ها هیچ مجوزی برای ساخت journal entry، تغییر مبلغ/تاریخ ledger یا عبور از MFA، policy و SoD ایجاد نمی‌کنند.

## ۱. طراحی PostgreSQL برای Active Allocation Reservation

### ۱.۱. قرارداد کسب‌وکاری

در طرح پایه، هر `statement_line` و هر `ledger_entry` فقط می‌تواند در یک decision با حالت زنده—`pending` یا `active`—قرار بگیرد. این مدل عمداً **exclusive** است: اجرای هم‌زمان دو case روی یک entry را منع می‌کند و برای مرحله نخست Split Matching ایمن‌تر است. اگر محصول در آینده به «تخصیص جزئی یک entry بین چند case» نیاز داشته باشد، این constraint کافی نیست و باید ledger capacity، sum allocation، isolation و locking جداگانه طراحی شوند؛ حذف unique index راه‌حل قابل‌قبول نیست.

| منبع رزرو | حالت زنده | invariant پایگاه داده | تصمیم سرویس |
|---|---|---|---|
| `statement_line` | `pending` یا `active` | فقط یک reservation زنده در یک company | duplicate → `ActiveAllocationConflict` |
| `ledger_entry` | `pending` یا `active` | فقط یک reservation زنده در یک company | duplicate → `ActiveAllocationConflict` |
| reservation release/supersede | `released` یا `superseded` | history باقی می‌ماند؛ در index جزئی نیست | candidate تازه می‌تواند بررسی شود |

### ۱.۲. DDL پیشنهادی

از دو ستون nullable با constraint «دقیقاً یک resource» استفاده می‌شود. این کار foreign key واقعی به هر دو جدول را حفظ می‌کند و polymorphic key بدون referential integrity نمی‌سازد.

```sql
CREATE TYPE allocation_reservation_state AS ENUM (
    'pending',
    'active',
    'released',
    'superseded'
);

CREATE TABLE active_allocation_reservations (
    id                   uuid PRIMARY KEY,
    company_id           bigint NOT NULL REFERENCES companies(id),
    reconciliation_case_id uuid NOT NULL REFERENCES reconciliation_cases(id),
    decision_id          uuid NOT NULL REFERENCES reconciliation_decisions(id),
    statement_line_id    bigint NULL REFERENCES bank_statement_lines(id),
    ledger_entry_id      bigint NULL REFERENCES journal_entries(id),
    state                allocation_reservation_state NOT NULL DEFAULT 'pending',
    created_at           timestamptz NOT NULL DEFAULT now(),
    released_at          timestamptz NULL,
    release_reason       varchar(80) NULL,
    CONSTRAINT ck_reservation_exactly_one_resource CHECK (
        num_nonnulls(statement_line_id, ledger_entry_id) = 1
    ),
    CONSTRAINT ck_reservation_lifecycle CHECK (
        (state IN ('pending','active') AND released_at IS NULL)
        OR
        (state IN ('released','superseded') AND released_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX CONCURRENTLY uq_live_statement_line_reservation
    ON active_allocation_reservations (company_id, statement_line_id)
    WHERE state IN ('pending', 'active')
      AND statement_line_id IS NOT NULL;

CREATE UNIQUE INDEX CONCURRENTLY uq_live_ledger_entry_reservation
    ON active_allocation_reservations (company_id, ledger_entry_id)
    WHERE state IN ('pending', 'active')
      AND ledger_entry_id IS NOT NULL;

CREATE INDEX CONCURRENTLY ix_reservation_case_state
    ON active_allocation_reservations (reconciliation_case_id, state);
```

PostgreSQL partial unique indexes uniqueness را فقط برای rowهایی که predicate آن‌ها را پوشش می‌دهد enforce می‌کنند؛ به همین دلیل history released/superseded می‌تواند حفظ شود، اما active ownership تکراری ایجاد نشود.[3] چون partial index به‌صورت `UNIQUE CONSTRAINT` attach نمی‌شود، خود unique index همان enforcement constraint است. در migrationهای بزرگ، `CREATE INDEX CONCURRENTLY` نباید داخل transaction block اجرا شود؛ migration tool باید آن step را non-transactional اجرا کند و پیش از deployment در staging آزموده شود.

پرس‌وجوهای operational باید predicate سازگار داشته باشند تا planner بتواند partial index را به‌کار گیرد. برای نمونه:

```sql
SELECT id, reconciliation_case_id, decision_id
FROM active_allocation_reservations
WHERE company_id = :company_id
  AND ledger_entry_id = :ledger_entry_id
  AND state IN ('pending', 'active');
```

برای integrity، درست‌بودن predicate query شرط نیست—unique index همچنان enforce می‌شود—اما predicate مبهم یا parameterized نامتناسب می‌تواند استفاده بهینه از index را کاهش دهد.[3]

### ۱.۳. SQLAlchemy 2.0 migration/model

```python
from sqlalchemy import CheckConstraint, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

class ActiveAllocationReservation(Base):
    __tablename__ = "active_allocation_reservations"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    reconciliation_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("reconciliation_cases.id"), nullable=False
    )
    decision_id: Mapped[UUID] = mapped_column(
        ForeignKey("reconciliation_decisions.id"), nullable=False
    )
    statement_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_statement_lines.id"), nullable=True
    )
    ledger_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("journal_entries.id"), nullable=True
    )
    state: Mapped[str] = mapped_column(nullable=False, server_default="pending")

    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(statement_line_id, ledger_entry_id) = 1",
            name="ck_reservation_exactly_one_resource",
        ),
        CheckConstraint(
            "(state IN ('pending','active') AND released_at IS NULL) OR "
            "(state IN ('released','superseded') AND released_at IS NOT NULL)",
            name="ck_reservation_lifecycle",
        ),
        Index(
            "uq_live_statement_line_reservation",
            "company_id", "statement_line_id",
            unique=True,
            postgresql_where=text("state IN ('pending','active') AND statement_line_id IS NOT NULL"),
        ),
        Index(
            "uq_live_ledger_entry_reservation",
            "company_id", "ledger_entry_id",
            unique=True,
            postgresql_where=text("state IN ('pending','active') AND ledger_entry_id IS NOT NULL"),
        ),
    )
```

برای production، migrationهای schema باید با Alembic و revision بررسی‌شده اجرا شوند. `Index(..., postgresql_where=...)` تعریف metadata است؛ انتخاب گزینه `CONCURRENTLY` به migration عملیاتی جدا نیاز دارد، نه صرفاً model declaration.

## ۲. مدیریت deadlock و retry در PostgreSQL

### ۲.۱. پیشگیری: ترتیب قفل ثابت و transaction کوتاه

PostgreSQL deadlock را تشخیص می‌دهد و یکی از transactionها را abort می‌کند؛ اینکه کدام transaction قربانی شود قابل اتکا نیست. بهترین دفاع، گرفتن چند قفل در ترتیب ثابت و نگه‌نداشتن transaction هنگام I/O یا انتظار input کاربر است.[4]

ترتیب پیشنهادی برای `approve_split()` این است:

1. `ReconciliationCase` را با `FOR UPDATE` قفل کنید تا actionهای یک case serialize شوند.
2. `statement_line` و سپس `ledger_entry`های allocation را بر مبنای کلید canonical `(resource_kind, resource_id)` مرتب کنید.
3. هر resource را با query مستقل و `FOR UPDATE` در همان ترتیب قفل کنید؛ همه code pathها—approve، reject، supersede و release—باید دقیقاً همین ترتیب را رعایت کنند.
4. snapshot، policy و SoD را validate کنید؛ سپس decision، allocation و reservationها را به ترتیب sort‌شده درج کنید.
5. CAS head، audit success و idempotency completion را ثبت و commit کنید.

```python
RESOURCE_ORDER = {"statement": 0, "ledger": 1}

def lock_resources_in_canonical_order(session, statement_line_id: int, ledger_ids: list[int]) -> None:
    resources = [("statement", statement_line_id)] + [("ledger", value) for value in ledger_ids]
    for kind, resource_id in sorted(resources, key=lambda item: (RESOURCE_ORDER[item[0]], item[1])):
        if kind == "statement":
            session.execute(
                select(BankStatementLine.id)
                .where(BankStatementLine.id == resource_id)
                .with_for_update()
            ).scalar_one()
        else:
            session.execute(
                select(JournalEntry.id)
                .where(JournalEntry.id == resource_id)
                .with_for_update()
            ).scalar_one()
```

`FOR UPDATE` برای writer/lockerهای متعارض روی همان row مانع ایجاد می‌کند و در پایان transaction آزاد می‌شود.[4] برای این workload، `READ COMMITTED` همراه با unique reservation و CAS معمولاً مدل قابل‌فهم‌تری است. اگر `SERIALIZABLE` انتخاب شود، کل transaction باید در برابر `40001` retry شود؛ serialization failure ممکن است حتی بدون deadlock منطقی رخ دهد.[5]

### ۲.۲. retry policy محدود و امن

| SQLSTATE / خطا | معنا | retry؟ | رفتار دامنه |
|---|---|---|---|
| `40P01` | PostgreSQL deadlock detected | بله، کل transaction و فقط bounded | retry با همان idempotency key و jitter |
| `40001` | serialization failure | بله، کل transaction | re-read همه snapshotها؛ همان key |
| `55P03` | lock not available / timeout | حداکثر طبق policy | conflict موقت؛ به client بگویید دوباره evidence را بارگذاری کند |
| `23505` روی reservation | unique violation | خیر، مگر علت transient اثبات‌شده | `ActiveAllocationConflict`؛ case/entry دیگر owner دارد |
| `23505` روی idempotency | key همزمان | خیر برای business command | result completed/in-progress را بازخوانی کنید |
| SoD / MFA / allocation invariant | validation/authz failure | هرگز | denial/exception بدون retry |

مستند PostgreSQL توصیه می‌کند transaction کامل—شامل همه decision logic و SQL—در برابر `40001` و در برخی موارد `40P01` retry شود؛ retry یک statement کافی نیست.[5] retry باید **در outer boundary** انجام شود، نه درون یک `Session` که پس از exception در وضعیت failed قرار گرفته است. هر attempt باید session/transaction تازه، backoff تصادفی محدود و deadline کل request داشته باشد.

```python
RETRYABLE_SQLSTATE = {"40P01", "40001"}
MAX_ATTEMPTS = 3


def approve_with_retry(service, company_id, command, principal):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return service.approve_once(company_id, command, principal)
        except DBAPIError as exc:
            sqlstate = getattr(getattr(exc, "orig", None), "pgcode", None)
            if sqlstate not in RETRYABLE_SQLSTATE or attempt == MAX_ATTEMPTS:
                raise
            sleep(backoff_with_full_jitter(attempt, cap_seconds=0.35))
    raise AssertionError("unreachable")
```

هر `approve_once()` باید claim idempotency، validations، locks، inserts، CAS، audit و completion را در یک transaction نگه دارد. اگر deadlock یا serialization failure رخ دهد، transaction rollback می‌شود و idempotency record `completed` نباید باقی بماند؛ attempt بعدی همان key را دوباره claim می‌کند. اگر attempt اول واقعاً commit شده اما network response گم شده باشد، retry همان key باید result completed ذخیره‌شده را بازگرداند، نه decision دوم بسازد.

### ۲.۳. observability و عملیات

deadlock را فقط retry نکنید؛ count، SQLSTATE، operation، company scope، attempt و latency را بدون payload حساس در metrics/audit ثبت کنید. برای incident response از `pg_locks` و lock monitoring استفاده شود. `lock_timeout` و `statement_timeout` باید در محیط production با SRE/DBA تنظیم و در CI با failure injection آزموده شوند. Advisory lock راه اصلی integrity نیست؛ زیرا PostgreSQL اجرای آن را enforce نمی‌کند. اگر advisory lock برای کاهش contention استفاده می‌شود، باید transaction-level باشد و unique reservation/CAS همچنان source of truth باقی بمانند.[4]

## ۳. نمونه آزمون‌های خودکار CI/CD برای SoD و exception

### ۳.۱. آنچه هم‌اکنون تست می‌شود

`tests/test_bank_reconciliation_v27.py` در حال حاضر صف `needs_review`، contra-only match، self-resolution exception، locked period و Close Readiness blocker را پوشش می‌دهد. در سناریوی SoD موجود، همان manager exception را flag می‌کند، resolve خود او باید خطا دهد، controller مستقل resolve می‌کند، event `bank.reconciliation.sod_denied` باید ثبت باشد و HMAC chain معتبر بماند.[2]

### ۳.۲. ماژول regression پیشنهادی برای v2.7.0

کد زیر fixture فعلی `BankReconciliationV27Tests` را گسترش می‌دهد و سه postcondition حیاتی را صریح می‌کند: denial، وضعیت exception را تغییر نمی‌دهد؛ evidence denial باقی می‌ماند؛ و MFA منقضی هیچ mutation ایجاد نمی‌کند.

```python
# tests/test_bank_reconciliation_security_ci.py
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from core.audit import AuditLogger, AuditSigningKeyStore
from core.bank_reconciliation import BankReconciliationError
from core.models import AuditLog, BankReconciliationStatus, PlaidTransactionMapping
from tests.test_bank_reconciliation_v27 import BankReconciliationV27Tests


class BankReconciliationSecurityCiTests(BankReconciliationV27Tests):
    def _mapping_after(self, session):
        return session.scalar(
            select(PlaidTransactionMapping).where(
                PlaidTransactionMapping.provider_transaction_id == "reconciliation-tx-001"
            )
        )

    def test_self_resolution_is_denied_without_state_or_ledger_mutation(self):
        self.service.mark_exception(
            self.company_id,
            "reconciliation-tx-001",
            "Invoice evidence is incomplete",
            self.manager,
        )
        with self.database.get_session() as session:
            before = self._mapping_after(session)
            before_status = before.reconciliation_status
            before_actor = before.reconciled_by_user_id
            before_entry_id = before.journal_entry_id

        with self.assertRaises(BankReconciliationError):
            self.service.resolve_exception(
                self.company_id,
                "reconciliation-tx-001",
                self.expense_account_id,
                self.manager,
                "Self-resolution must not be accepted",
            )

        with self.database.get_session() as session:
            after = self._mapping_after(session)
            self.assertEqual(after.reconciliation_status, BankReconciliationStatus.EXCEPTION)
            self.assertEqual(after.reconciled_by_user_id, before_actor)
            self.assertEqual(after.journal_entry_id, before_entry_id)
            denied = session.scalar(
                select(AuditLog).where(AuditLog.action == "bank.reconciliation.sod_denied")
            )
            self.assertIsNotNone(denied)
            self.assertEqual(denied.outcome, "denied")
            self.assertTrue(self.audit_logger.verify_chain(session).valid)

    def test_stale_mfa_cannot_mark_exception_and_keeps_needs_review(self):
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=16)
        stale_principal = self.manager.__class__(
            user_id=self.manager.user_id,
            session_id="stale-mfa-session",
            provider_code=self.manager.provider_code,
            issuer=self.manager.issuer,
            subject=self.manager.subject,
            authenticated_at=stale_time,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            mfa_at=stale_time,
        )
        with self.assertRaises(BankReconciliationError):
            self.service.mark_exception(
                self.company_id,
                "reconciliation-tx-001",
                "MFA freshness must be enforced",
                stale_principal,
            )
        with self.database.get_session() as session:
            mapping = self._mapping_after(session)
            self.assertEqual(mapping.reconciliation_status, BankReconciliationStatus.NEEDS_REVIEW)
            self.assertTrue(self.audit_logger.verify_chain(session).valid)

    def test_independent_controller_can_resolve_after_denial(self):
        self.service.mark_exception(
            self.company_id, "reconciliation-tx-001", "Needs independent review", self.manager
        )
        with self.assertRaises(BankReconciliationError):
            self.service.resolve_exception(
                self.company_id, "reconciliation-tx-001", self.expense_account_id,
                self.manager, "Must fail",
            )
        self.service.resolve_exception(
            self.company_id, "reconciliation-tx-001", self.expense_account_id,
            self.controller, "Controller verified the evidence",
        )
        with self.database.get_session() as session:
            mapping = self._mapping_after(session)
            self.assertEqual(mapping.reconciliation_status, BankReconciliationStatus.MATCHED)
            self.assertEqual(mapping.reconciled_by_user_id, self.controller_id)
            self.assertTrue(self.audit_logger.verify_chain(session).valid)
```

در implementation فعلی، exception text دقیق `BankReconciliationError` ممکن است از authorization layer یا service بیاید؛ CI باید type error و postconditionهای امنیتی را assert کند، نه exact wording پیام. نام import پایه نیز باید با package layout واقعی test runner هماهنگ شود؛ اگر `tests` package نیست، fixture مشترک به یک helper module منتقل شود.

### ۳.۳. نمونه workflow CI/CD پیشنهادی

workflow release امضاشده فعلی پیش از ساخت EXE، dependency validation و `python -m unittest discover -s tests -v` را اجرا می‌کند.[6] گیت مستقل زیر برای pull request و main نمونه‌ای از جداسازی fast regression و PostgreSQL integration است. بخش PostgreSQL باید تنها پس از پیاده‌سازی models/service v2.8.0 فعال شود.

```yaml
# .github/workflows/reconciliation-controls.yml
name: Reconciliation Control Gates

on:
  pull_request:
    paths:
      - 'core/**'
      - 'tests/**'
      - '.github/workflows/reconciliation-controls.yml'
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  v27-sod-regression:
    runs-on: ubuntu-24.04
    timeout-minutes: 12
    steps:
      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
        with:
          python-version: '3.12'
          cache: pip
      - name: Install test dependencies
        run: python -m pip install -r requirements-windows-build.txt
      - name: Run bank reconciliation SoD and exception gates
        run: |
          python -m unittest \
            tests.test_bank_reconciliation_v27 \
            tests.test_bank_reconciliation_security_ci -v

  v28-postgres-concurrency:
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: finanalyzer_test
          POSTGRES_PASSWORD: local-ci-only-password
          POSTGRES_DB: finanalyzer_test
        ports: ['5432:5432']
        options: >-
          --health-cmd "pg_isready -U finanalyzer_test -d finanalyzer_test"
          --health-interval 5s --health-timeout 5s --health-retries 12
    env:
      TEST_DATABASE_URL: postgresql+psycopg://finanalyzer_test:local-ci-only-password@localhost:5432/finanalyzer_test
      FINANALYZER_TESTING: '1'
    steps:
      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
        with:
          python-version: '3.12'
          cache: pip
      - name: Install PostgreSQL integration dependencies
        run: |
          python -m pip install -r requirements-windows-build.txt
          python -m pip install 'psycopg[binary]>=3.2,<4'
      - name: Apply test schema and verify partial unique indexes
        run: |
          python scripts/migrate_test_database.py
          python scripts/verify_reconciliation_schema.py
      - name: Run SoD, idempotency, allocation and deadlock gates
        run: |
          python -m unittest \
            tests.test_bank_reconciliation_security_ci \
            tests.test_statement_reconciliation_postgres -v
```

workflow نمونه، پین SHA برای actionها را از الگوی release-sign فعلی حفظ می‌کند. credential PostgreSQL فقط service container CI است و نباید با secret production مشترک باشد. job PostgreSQL تا زمان نصب driver و ایجاد migration واقعی نباید به build release فعلی افزوده شود؛ ابتدا روی PR/staging فعال و سپس به release gate منتقل شود.[6]

### ۳.۴. تست integration PostgreSQL برای constraint و deadlock

```python
# tests/test_statement_reconciliation_postgres.py
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.statement_reconciliation import ActiveAllocationConflict, ApprovalResult
from core.models import ActiveAllocationReservation, ReconciliationDecision
from tests.reconciliation_postgres_fixture import StatementReconciliationPostgresFixture


class StatementReconciliationPostgresTests(StatementReconciliationPostgresFixture):
    def test_two_cases_contending_for_one_entry_yield_one_owner(self):
        barrier = threading.Barrier(2)
        self.service.before_reservation_hook = lambda: barrier.wait(timeout=8)
        command_a = self.make_split_command(
            case_id=self.case_a_id, entry_ids=[self.shared_entry_id], idempotency_key=uuid4()
        )
        command_b = self.make_split_command(
            case_id=self.case_b_id, entry_ids=[self.shared_entry_id], idempotency_key=uuid4()
        )

        def run(command, principal):
            try:
                return self.service.approve_with_retry(self.company_id, command, principal)
            except Exception as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [
                pool.submit(run, command_a, self.reviewer_a).result(timeout=15),
                pool.submit(run, command_b, self.reviewer_b).result(timeout=15),
            ]

        self.assertEqual(sum(isinstance(item, ApprovalResult) for item in results), 1)
        self.assertEqual(sum(isinstance(item, ActiveAllocationConflict) for item in results), 1)
        with self.database.get_session() as session:
            reservations = list(session.scalars(select(ActiveAllocationReservation).where(
                ActiveAllocationReservation.company_id == self.company_id,
                ActiveAllocationReservation.ledger_entry_id == self.shared_entry_id,
                ActiveAllocationReservation.state.in_(['pending', 'active']),
            )))
            self.assertEqual(len(reservations), 1)
            approved = list(session.scalars(select(ReconciliationDecision).where(
                ReconciliationDecision.action == 'approved'
            )))
            self.assertEqual(len(approved), 1)
            self.assertTrue(self.audit_logger.verify_chain(session).valid)
```

در test واقعی، `future.result()`ها باید پس از submit هر دو future فراخوانی شوند تا ناخواسته serial نشوند:

```python
with ThreadPoolExecutor(max_workers=2) as pool:
    future_a = pool.submit(run, command_a, self.reviewer_a)
    future_b = pool.submit(run, command_b, self.reviewer_b)
    results = [future_a.result(timeout=15), future_b.result(timeout=15)]
```

همچنین failure injection برای `40P01` باید در محیط integration کنترل‌شده با دو transaction که resourceهای مشترک را **عمداً به ترتیب معکوس** قفل می‌کنند اجرا شود. بعد از retry bounded، assertionهای پسین ثابت‌اند: حداکثر یک owner active برای هر resource، decision تکراری صفر، audit chain معتبر و هیچ reservation نیمه‌کاره.

## ۴. متن کامل اسلایدها و اسکریپت سخنران: Split Matching و Concurrency

### اسلاید ۵ — Split Matching رابطه می‌سازد

**متن روی اسلاید**

| ورودی | تصمیم تخصیص | خروجی کنترل‌شده |
|---|---|---|
| `BankStatementLine` با amount، currency، date و source hash | یک یا چند `CandidateAllocation` به entryهای posted و هم‌شرکت | `ReconciliationDecision` immutable، evidence hash و reservation فعال |

- `Σ allocation = statement amount`
- بدون journal entry جدید
- بدون تغییر مبلغ، تاریخ یا lineهای ledger موجود
- اختلاف خارج policy → exception

**اسکریپت سخنران**

«Split Matching برای settlementهای تجمیعی طراحی می‌شود؛ یک ردیف statement ممکن است چند entry موجود دفتر را پوشش دهد. ما رابطه و سهم هر entry را به‌صورت allocation ثبت می‌کنیم، نه این‌که برای جورشدن مبلغ، سند تازه بسازیم یا entryهای قبلی را بازنویسی کنیم. statement line منبع evidence است و entryها باید posted، هم‌شرکت و مجاز باشند. جمع allocationها باید دقیقاً با مبلغ statement برابر باشد. اگر اختلاف خارج policy باشد، نتیجه exception است؛ این طراحی عمداً اجازه نمی‌دهد کاربر با یک match ظاهراً متوازن، یک اختلاف واقعی را پنهان کند.»

### اسلاید ۶ — Allocation با invariant محافظت می‌شود

**متن روی اسلاید**

| گیت | قانون | نتیجه نقض |
|---|---|---|
| Amount | Decimal، مثبت، غیرصفر و جمع دقیق | rollback و validation error |
| Currency | ارز، sign و minor unit سازگار | exception یا approval بالاتر |
| Eligibility | entry posted، دوره باز و بدون ownership فعال دیگر | `ActiveAllocationConflict` |
| Policy | tolerance نسخه‌دار با reason/evidence | عدم پذیرش اختلاف پنهان |
| Governance | split/FX/high-risk → approver مستقل | denial یا pending approval |

**اسکریپت سخنران**

«رسیدن جمع مبلغ به statement شرط لازم است، نه کافی. هر سهم با Decimal محاسبه می‌شود، باید مثبت و در minor unit ارز باشد و هیچ entry نمی‌تواند خارج از status یا دوره مجاز وارد تصمیم شود. tolerance یک عدد پنهان در UI نیست؛ باید از policy version فعال بیاید و در evidence ثبت شود. اگر entry هم‌زمان مالک فعال در case دیگر داشته باشد، unique reservation تصمیم دوم را متوقف می‌کند. و در مورد split، FX، tolerance غیرصفر یا ریسک بالاتر، policy مسیر approval مستقل را فعال می‌کند. بنابراین گیت‌ها اختلاف را به exception قابل پیگیری تبدیل می‌کنند، نه به mutation بدون کنترل.»

### اسلاید ۷ — Idempotency، CAS و Reservation

**متن روی اسلاید**

| کنترل | مسئله‌ای که حل می‌کند | رفتار در تعارض |
|---|---|---|
| Idempotency key | retry همان command | بازگشت همان result؛ no duplicate decision |
| Compare-and-Swap | case پس از مشاهده تغییر کرده است | reload evidence؛ no hidden overwrite |
| Active reservation | entry/statement در case دیگر فعال است | conflict domain و rollback کامل |

**اسکریپت سخنران**

«سه کنترل مکمل داریم. idempotency تضمین می‌کند اگر شبکه response را گم کرد و client همان درخواست را فرستاد، system همان decision را بازگرداند، نه اینکه تصمیم دوم بسازد. Compare-and-Swap تضمین می‌کند reviewer روی case تغییرکرده overwrite انجام ندهد. Active Reservation تضمین می‌کند همان entry یا statement line هم‌زمان به case دیگری تخصیص نیابد. این کنترل‌ها در یک transaction کنار decision، allocation، audit و policy اجرا می‌شوند. اگر conflict رخ دهد، UI evidence جدید را بارگذاری می‌کند؛ retry پنهان یا merge خودکار مجاز نیست.»

### اسلاید ۹ — Rollout کنترل را مقدم می‌داند

**متن روی اسلاید**

| موج | قابلیت‌ها | گیت خروج |
|---|---|---|
| v2.8.0-a | import، matching قطعی، history immutable، optimistic lock | idempotency، migration/restore، HMAC verification و UAT controller |
| v2.8.0-b | explanation، Split Matching، partial unique reservation و approval matrix | allocation/concurrency/SoD negative tests و approval Finance/Compliance |
| v2.8.0-c | certification، exception SLA، evidence export و re-check close | failure injection، restore و controller sign-off مستقل |

**اسکریپت سخنران**

«این roadmap، AI را یک‌باره به production نمی‌برد. ابتدا موج a، پایه داده و history تصمیم را تثبیت می‌کند. سپس موج b، Split Matching و explanation را فقط وقتی وارد می‌کند که invariantهای allocation، constraintهای uniqueness و منفی‌تست‌های SoD در PostgreSQL و UAT مالی عبور کرده باشند. موج c، certification و Close Readiness را کامل می‌کند. در هر مرحله، گیت خروج شامل evidence، rollback و sign-off است. confidence مدل هیچ‌گاه معیار Go به‌تنهایی نیست؛ تصمیم مالی باید از منظر Finance، Security و Compliance قابل دفاع باشد.»

## منابع

[1]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/bank_reconciliation.py "BankReconciliationService و کنترل‌های موجود v2.7.0"

[2]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/tests/test_bank_reconciliation_v27.py "آزمون‌های regression SoD و exception v2.7.0"

[3]: https://www.postgresql.org/docs/current/indexes-partial.html "PostgreSQL: Partial Indexes"

[4]: https://www.postgresql.org/docs/current/explicit-locking.html "PostgreSQL: Explicit Locking and Deadlocks"

[5]: https://www.postgresql.org/docs/current/mvcc-serialization-failure-handling.html "PostgreSQL: Serialization Failure Handling"

[6]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/.github/workflows/release-sign.yml "Signed Windows Release workflow"
