# Idempotency، Active Allocation Conflict و معماری هوش مصنوعی/تطبیق بانکی v2.8.0

## وضعیت و محدوده

این سند یک blueprint پیاده‌سازی برای v2.8.0 است. جدول‌های idempotency، reservationهای تخصیص، `ReconciliationCase` و service CAS هنوز در کد فعلی v2.7.0 وجود ندارند. کنترل‌های مبنایی مانند HMAC audit، authorization، MFA، company scope و SoD exception در v2.7.0 وجود دارند و باید بدون تضعیف، توسط service جدید مصرف شوند.[1] [2]

> **اصل:** idempotency از تکرار «همان command» جلوگیری می‌کند؛ optimistic locking از overwrite «case تغییرکرده» جلوگیری می‌کند؛ reservation یکتا از مصرف هم‌زمان «همان statement/ledger entry در caseهای متفاوت» جلوگیری می‌کند. این سه کنترل مکمل‌اند، نه جایگزین یکدیگر.

## ۱. مدل داده و constraintهای یکتا

### ۱.۱. جدول idempotency

هر command تغییردهنده—submit، approve، reject، void یا close exception—باید یک `idempotency_key` تولیدشده در کلاینت داشته باشد. کلید باید UUID تصادفی باشد؛ hash بدنه درخواست یا timestamp به‌تنهایی کلید امن idempotency نیستند. سرور باید scope و fingerprint command را همراه key ذخیره کند تا استفاده مجدد همان key برای بدنه متفاوت، تشخیص داده شود.

```python
class IdempotencyStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED_RETRYABLE = "failed_retryable"

class ReconciliationIdempotencyKey(Base):
    __tablename__ = "reconciliation_idempotency_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    key: Mapped[str] = mapped_column(String(36), nullable=False)
    command_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    decision_id: Mapped[Optional[str]] = mapped_column(String(36))
    response_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "company_id", "actor_id", "operation", "key",
            name="uq_reconciliation_idempotency_actor_operation_key",
        ),
    )
```

scope باید `company_id`، `actor_id` و `operation` را دربرگیرد. این انتخاب اجازه نمی‌دهد idempotency key یک actor در شرکت A، نتیجه actor/operation دیگری در شرکت B را برگرداند. `command_fingerprint` از canonical JSON command ساخته می‌شود؛ شامل `case_id`، expected version، candidate fingerprint، policy version، allocationهای مرتب‌شده و note نرمال‌شده، اما بدون secret یا raw provider payload.

### ۱.۲. reservationهای فعال برای تخصیص

idempotency key مانع request تکراری یک actor می‌شود، اما دو case یا دو actor متفاوت همچنان ممکن است یک entry مشترک را تخصیص دهند. برای این وضعیت `ActiveAllocationReservation` لازم است. هر reservation active به statement line یا ledger entry خاص تعلق دارد و توسط database uniqueness enforce می‌شود.

```python
class ActiveAllocationReservation(Base):
    __tablename__ = "active_allocation_reservations"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    statement_line_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bank_statement_lines.id"))
    ledger_entry_id: Mapped[Optional[int]] = mapped_column(ForeignKey("journal_entries.id"))
    case_id: Mapped[str] = mapped_column(String(36), nullable=False)
    decision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

در databaseهایی که partial unique index دارند، constraintهای زیر توصیه می‌شود:

```sql
CREATE UNIQUE INDEX uq_active_statement_reservation
ON active_allocation_reservations(company_id, statement_line_id)
WHERE state = 'active' AND statement_line_id IS NOT NULL;

CREATE UNIQUE INDEX uq_active_ledger_reservation
ON active_allocation_reservations(company_id, ledger_entry_id)
WHERE state = 'active' AND ledger_entry_id IS NOT NULL;
```

اگر engine مقصد partial index نداشته باشد، جدول active-only جداگانه با `UNIQUE(company_id, statement_line_id)` و `UNIQUE(company_id, ledger_entry_id)`، همراه با انتقال history به event table، جایگزین امن‌تری است. هیچ‌گاه نباید uniqueness را فقط با یک `SELECT` پیش از `INSERT` پیاده‌سازی کرد؛ آن الگو در برابر race condition ناامن است.

## ۲. جریان پیاده‌سازی idempotency

### ۲.۱. canonical fingerprint

```python
def command_fingerprint(command: ApproveReconciliationCommand) -> str:
    canonical = {
        "case_id": str(command.case_id),
        "expected_case_version": command.expected_case_version,
        "candidate_fingerprint": command.candidate_fingerprint,
        "statement_line_version": command.statement_line_version,
        "ledger_snapshot_versions": sorted(command.ledger_snapshot_versions.items()),
        "policy_version": command.policy_version,
        "allocations": sorted(
            (str(item.ledger_entry_id), str(item.amount)) for item in command.allocations
        ),
        "note": (command.note or "").strip(),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
```

sort کردن allocationها مهم است؛ ترتیب نمایش در UI نباید fingerprint را تغییر دهد. در عین حال، تغییر واقعی amount، member، policy یا expected version باید fingerprint را تغییر دهد.

### ۲.۲. claim اتمیک key

`_claim_idempotency_key()` باید در transaction کوتاه انجام شود. ابتدا تلاش می‌کند یک row با status `in_progress` درج کند. اگر uniqueness violation رخ داد، row موجود خوانده می‌شود و server با fingerprint مقایسه می‌کند.

```python
def _claim_idempotency_key(self, session, *, company_id, actor_id, operation, key, fingerprint):
    record = ReconciliationIdempotencyKey(
        company_id=company_id,
        actor_id=actor_id,
        operation=operation,
        key=str(key),
        command_fingerprint=fingerprint,
        status=IdempotencyStatus.IN_PROGRESS.value,
        created_at=utc_now(),
    )
    try:
        with session.begin_nested():
            session.add(record)
            session.flush()
        return IdempotencyClaim(owner=True, record=record)
    except IntegrityError:
        existing = session.scalar(
            select(ReconciliationIdempotencyKey).where(
                ReconciliationIdempotencyKey.company_id == company_id,
                ReconciliationIdempotencyKey.actor_id == actor_id,
                ReconciliationIdempotencyKey.operation == operation,
                ReconciliationIdempotencyKey.key == str(key),
            )
        )
        if existing is None:
            raise
        if not hmac.compare_digest(existing.command_fingerprint, fingerprint):
            raise IdempotencyKeyReuseError("The same idempotency key was used for a different command.")
        if existing.status == IdempotencyStatus.COMPLETED.value:
            return IdempotencyClaim(owner=False, completed=existing)
        return IdempotencyClaim(owner=False, in_progress=existing)
```

در SQLAlchemy، `begin_nested()` کمک می‌کند uniqueness error حاصل از claim، کل transaction اصلی را abort نکند. پیاده‌سازی production باید behavior engine هدف را validate کند. پاسخ `in_progress` می‌تواند کوتاه‌مدت به‌صورت «در حال پردازش» برگردد یا تا سقف محدود برای completion poll شود. retry خودکار بدون deadline یا اجرای دوباره command ممنوع است.

### ۲.۳. completion و failure

اگر owner موفق شد، در همان transaction business که decision، allocation، reservation، CAS و audit را commit می‌کند، idempotency record نیز `completed` می‌شود و پاسخ success serialize می‌گردد. بنابراین پس از crash قبل از commit، نه تصمیم و نه status completed باقی نمی‌ماند. اگر validation/CAS/reservation conflict رخ دهد، transaction business rollback می‌شود؛ برای خطاهای retryable می‌توان row claim را در transaction جدا به `failed_retryable` تغییر داد یا با TTL پاک‌سازی کرد. برای خطاهای غیرretryable مانند key reuse، هیچ command دیگری با همان key پذیرفته نمی‌شود.

| وضعیت key | پاسخ retry همسان | پاسخ key با fingerprint متفاوت |
|---|---|---|
| `completed` | همان response ذخیره‌شده، بدون write | `IdempotencyKeyReuseError` |
| `in_progress` | در حال پردازش یا poll محدود | `IdempotencyKeyReuseError` |
| `failed_retryable` | طبق policy claim جدید پس از TTL/cleanup | `IdempotencyKeyReuseError` |
| absent | یک owner جدید می‌شود | — |

## ۳. نمونه service: idempotency + CAS + reservation

```python
def approve(self, company_id, command, principal):
    fingerprint = command_fingerprint(command)
    with self.database.get_session() as session:
        self._require_approval_context(session, company_id, principal)
        claim = self._claim_idempotency_key(
            session,
            company_id=company_id,
            actor_id=principal.user_id,
            operation="statement.reconcile.approve",
            key=command.idempotency_key,
            fingerprint=fingerprint,
        )
        if claim.completed:
            return ApprovalResult.from_json(claim.completed.response_json)
        if claim.in_progress:
            raise IdempotencyInProgress(claim.in_progress.id)

        case, statement, candidate, entries, policy = self._load_and_validate_snapshot(
            session, company_id, command
        )
        self._validate_allocations(statement, entries, command.allocations, policy)
        self._assert_sod_and_policy(case, command, principal, policy)

        decision = self._append_immutable_decision(session, case, command, principal, policy)
        self._reserve_statement_and_entries(
            session, company_id, statement, entries, command.allocations, case, decision
        )
        self._insert_immutable_allocations(session, decision, command.allocations)

        cas = session.execute(
            update(ReconciliationCase)
            .where(
                ReconciliationCase.id == case.id,
                ReconciliationCase.company_id == company_id,
                ReconciliationCase.version == command.expected_case_version,
                ReconciliationCase.state == "submitted",
            )
            .values(
                state="approved",
                version=command.expected_case_version + 1,
                current_decision_id=decision.id,
                updated_at=utc_now(),
            )
        )
        if cas.rowcount != 1:
            raise ConcurrentDecisionConflict(case.id, command.expected_case_version)

        result = ApprovalResult(decision_id=decision.id, case_version=command.expected_case_version + 1)
        claim.record.status = IdempotencyStatus.COMPLETED.value
        claim.record.decision_id = str(decision.id)
        claim.record.response_json = result.to_json()
        claim.record.completed_at = utc_now()
        self._audit_success(session, company_id, principal, case, decision, command)
        return result
```

تمام exceptionهای business—`ConcurrentDecisionConflict`، `ActiveAllocationConflict`، `StaleCandidateConflict`، `AllocationInvariantError` و `AuditIntegrityError`—باید از transaction خارج شوند تا decision، allocation، reservation و completion record rollback شوند. `IntegrityError` ناشی از constraint reservation باید پس از nested savepoint به `ActiveAllocationConflict` ترجمه شود. تنها persistence جداگانه برای denialهای ضروری SoD است که مطابق الگوی v2.7.0 evidence audit را قبل از raise commit می‌کند.[1]

## ۴. نمونه کامل تست هم‌زمانی ActiveAllocationConflict

نمونه زیر فرض می‌کند service پیشنهادی یک hook آزمایشی محدود به نام `before_reservation_hook` دارد. هدف hook، کنترل deterministic زمان‌بندی دو thread است؛ این hook نباید در build production فعال باشد. هر thread باید database session مستقل داشته باشد و database فایل مشترک باشد.

```python
import threading
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from core.statement_reconciliation import (
    ActiveAllocationConflict,
    ApprovalResult,
    StatementReconciliationDecisionService,
)
from core.models import (
    ActiveAllocationReservation,
    CandidateAllocation,
    ReconciliationCase,
    ReconciliationDecision,
)


class ActiveAllocationConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "concurrency.db"
        self.database = make_file_backed_test_database(str(db_path))
        self.database.init_database()
        self.service = make_statement_reconciliation_service(self.database)
        self.company_id, self.reviewer_a, self.reviewer_b = seed_company_and_reviewers(self.database)
        self.statement_a, self.statement_b, self.shared_entry = seed_two_cases_with_shared_entry(
            self.database, self.company_id
        )
        self.case_a = seed_case(self.database, self.company_id, self.statement_a, state="submitted", version=3)
        self.case_b = seed_case(self.database, self.company_id, self.statement_b, state="submitted", version=5)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_two_cases_cannot_reserve_the_same_ledger_entry(self):
        barrier = threading.Barrier(2)
        original_hook = self.service.before_reservation_hook
        self.service.before_reservation_hook = lambda: barrier.wait(timeout=5)
        try:
            command_a = build_approve_command(
                case_id=self.case_a,
                expected_case_version=3,
                statement_line_id=self.statement_a,
                allocations=[(self.shared_entry, "120.00")],
                idempotency_key=uuid4(),
            )
            command_b = build_approve_command(
                case_id=self.case_b,
                expected_case_version=5,
                statement_line_id=self.statement_b,
                allocations=[(self.shared_entry, "120.00")],
                idempotency_key=uuid4(),
            )

            def approve(command, principal):
                try:
                    return self.service.approve(self.company_id, command, principal)
                except Exception as exc:
                    return exc

            with ThreadPoolExecutor(max_workers=2) as pool:
                future_a = pool.submit(approve, command_a, self.reviewer_a)
                future_b = pool.submit(approve, command_b, self.reviewer_b)
                results = [future_a.result(timeout=10), future_b.result(timeout=10)]
        finally:
            self.service.before_reservation_hook = original_hook

        self.assertEqual(sum(isinstance(item, ApprovalResult) for item in results), 1)
        self.assertEqual(sum(isinstance(item, ActiveAllocationConflict) for item in results), 1)

        with self.database.get_session() as session:
            active = list(session.scalars(select(ActiveAllocationReservation).where(
                ActiveAllocationReservation.company_id == self.company_id,
                ActiveAllocationReservation.ledger_entry_id == self.shared_entry,
                ActiveAllocationReservation.state == "active",
            )))
            self.assertEqual(len(active), 1)

            decisions = list(session.scalars(select(ReconciliationDecision).where(
                ReconciliationDecision.case_id.in_([self.case_a, self.case_b]),
                ReconciliationDecision.action == "approved",
            )))
            self.assertEqual(len(decisions), 1)

            allocations = list(session.scalars(select(CandidateAllocation).where(
                CandidateAllocation.ledger_entry_id == self.shared_entry,
            )))
            self.assertEqual(len(allocations), 1)

            case_a = session.get(ReconciliationCase, self.case_a)
            case_b = session.get(ReconciliationCase, self.case_b)
            self.assertEqual({case_a.version, case_b.version}, {3, 6})
            self.assertTrue(self.service.audit_logger.verify_chain(session).valid)
```

### ۴.۱. سناریوهای تکمیلی برای همین test suite

| test | تنظیم | انتظار |
|---|---|---|
| `test_same_idempotency_key_returns_one_decision` | دو thread، همان actor/key/fingerprint | یک result قطعی؛ هیچ decision دوم ایجاد نشود |
| `test_idempotency_key_reuse_with_different_command_is_denied` | همان key با amount یا case متفاوت | `IdempotencyKeyReuseError` و بدون mutation |
| `test_conflict_rolls_back_idempotency_completion` | reservation conflict پس از claim | key completed نشود؛ decision/allocation/reservation دوم صفر |
| `test_stale_case_version_rolls_back_reservations` | case version تغییر کند پیش از CAS | `ConcurrentDecisionConflict` و active reservation جدید صفر |
| `test_concurrent_retry_observes_in_progress_or_completed` | همان key با delay در owner | پاسخ in-progress یا result cached؛ هرگز approve دوم نه |
| `test_denial_audit_is_preserved_without_business_write` | maker تلاش کند split high-risk خودش را approve کند | denial HMAC ثبت، ولی decision approved/reservation ایجاد نشود |

## ۵. محتوا و اسکریپت ارائه کامل معماری هوش مصنوعی و تطبیق بانکی v2.8.0

## Cover

**عنوان:** FinAnalyzer Enterprise v2.8.0

**زیرعنوان:** هوش تطبیق قابل‌توضیح، کنترل انسانی و Close مبتنی بر evidence

**متن سخنران:**

«در این ارائه، v2.8.0 را به‌عنوان یک تغییر معماری معرفی می‌کنیم: از review صرف bank feed به سمت تطبیق statement، تصمیم‌های قابل‌توضیح و evidence برای close. تأکید این نسخه بر اتوماسیون بدون کنترل نیست؛ برعکس، هدف این است که هوش مصنوعی پیشنهاد بدهد و کنترل‌های مالی سازمان تصمیم نهایی را اداره کنند.»

## Slide 1 — از Feed Review تا Statement Certification

**متن روی اسلاید:** Bank feed کنترل‌شده v2.7.0 → شکاف statement مستقل → certification و evidence v2.8.0.

**متن سخنران:**

«v2.7.0 ورود و review bank feed را کنترل‌پذیر کرد. بااین‌حال، close سازمانی به اثبات سازگاری statement خارجی با دفتر و مانده پایان دوره نیاز دارد. v2.8.0 این فاصله را با import کنترل‌شده CSV/OFX، relationهای تطبیق و certification قابل‌ممیزی هدف می‌گیرد. خروجی مورد انتظار، صرفاً status match نیست؛ evidence‌ای است که controller و حسابرس بتوانند آن را دنبال کنند.»

## Slide 2 — AI پیشنهاد می‌دهد؛ انسان تصمیم می‌گیرد

**متن روی اسلاید:** candidate explanation → permission + MFA + policy + approval → immutable decision.

**متن سخنران:**

«لایه هوشمند، candidate و explanation تولید می‌کند: چرا مبلغ، تاریخ، merchant یا reference احتمالاً با هم مرتبط‌اند. اما هیچ score یا confidence به‌تنهایی ledger را تغییر نمی‌دهد. permission، MFA تازه، policy و human approval مرز اصلی mutation هستند. این تفکیک باعث می‌شود از AI برای کاهش زمان review استفاده کنیم، بدون آن‌که مسئولیت و کنترل مالی را به یک مدل منتقل کنیم.»

## Slide 3 — معماری سه‌لایه تصمیم

**متن روی اسلاید:** Import & provenance | Candidate engine | Decision service & evidence.

**متن سخنران:**

«معماری v2.8.0 سه لایه دارد. در لایه نخست، statement با schema validation، hash و provenance وارد می‌شود. در لایه دوم، rules یا مدل، candidateهای deterministic و توضیح‌پذیر تولید می‌کنند، بدون mutation مالی. در لایه سوم، Decision Service، principal، MFA، policy، SoD، allocation و concurrency را کنترل می‌کند و سپس decision immutable، audit HMAC و evidence export را ثبت می‌کند. این جداسازی اجازه می‌دهد مدل بهبود یابد، بدون آن‌که مرز کنترل مالی باز شود.»

## Slide 4 — HMAC و Handoff امن Evidence

**متن روی اسلاید:** redact → canonical payload → HMAC-SHA256/DPAPI → verify/export.

**متن سخنران:**

«هر decision، approval یا denial باید evidence باشد. AuditLogger رخداد را پاکسازی می‌کند تا token یا secret باقی نماند، payload canonical با sequence و previous hash می‌سازد و آن را با HMAC-SHA256 امضا می‌کند. کلید audit در Windows با DPAPI محافظت می‌شود. verification، sequence، پیوند hashها و checkpoint را کنترل می‌کند. برای ادعای immutability سازمانی، evidence export به SIEM یا WORM نیز در مسیر v2.8.0-c قرار می‌گیرد.»

## Slide 5 — Split Matching: رابطه کنترل‌شده

**متن روی اسلاید:** یک statement line → allocationهای immutable → چند ledger entry موجود؛ بدون سند جدید.

**متن سخنران:**

«Split Matching پاسخ به settlementهای تجمیعی است. یک statement line ممکن است چند entry posted دفتر را پوشش دهد. سیستم سهم هر entry را به‌صورت allocation ثبت می‌کند، اما سند تازه ایجاد نمی‌کند و مبلغ یا تاریخ entryهای موجود را تغییر نمی‌دهد. هر allocation باید مثبت، دقیق، هم‌ارز statement و متعلق به entry مجاز همان شرکت باشد. هر اختلاف بدون policy، exception است؛ نه چیزی که با یک split اجباری پنهان شود.»

## Slide 6 — Idempotency، CAS و Reservation

**متن روی اسلاید:** idempotency key | expected case version | active reservation | immutable decision.

**متن سخنران:**

«برای اطمینان از این‌که اتوماسیون در شرایط retry و concurrency امن است، سه کنترل مکمل داریم. idempotency key مانع می‌شود همان request دوباره decision بسازد. Compare-and-Swap تضمین می‌کند reviewer تصمیمی را که از زمان مشاهده تغییر کرده overwrite نکند. و active reservation مانع می‌شود یک ledger entry یا statement line هم‌زمان به case دیگری تخصیص یابد. اگر هرکدام شکست بخورد، transaction rollback می‌شود و UI باید evidence را refresh کند؛ نه اینکه command را مخفیانه تکرار کند.»

## Slide 7 — SoD و Policy متناسب با ریسک

**متن روی اسلاید:** maker ≠ checker؛ split/FX/high-risk → independent approval؛ denial → HMAC evidence.

**متن سخنران:**

«همه matches ریسک یکسان ندارند. policy می‌تواند split، FX، tolerance غیرصفر، مبلغ بالا یا vendor پرریسک را به independent approval هدایت کند. maker نباید checker تصمیم خودش باشد و controller/certifier نیز نباید تنها approver همان تصمیم باشد. این enforcement در service layer با actor ID، permission، MFA و policy version انجام می‌شود. در صورت نقض، business mutation انجام نمی‌شود؛ اما denial به evidence HMAC تبدیل می‌شود تا قابل بررسی باقی بماند.»

## Slide 8 — کیفیت، UAT و Release Waveها

**متن روی اسلاید:** a: data foundation | b: explainable split | c: certification & close readiness.

**متن سخنران:**

«rollout مرحله‌ای است. موج a، import، deterministic match، immutable history و optimistic lock را تثبیت می‌کند. موج b، explanation، Split Matching، reservation و approval matrix را با UAT مالی اضافه می‌کند. موج c، certification، exception SLA، evidence export و Close Readiness را کامل می‌کند. هر موج فقط با evidence، migration/restore، HMAC verification، تست‌های negative و sign-off مناسب جلو می‌رود. معیار موفقیت confidence مدل نیست؛ درستی مالی، قابلیت توضیح و کنترل مستقل نیز ضروری‌اند.»

## Slide 9 — تصمیم پیشنهادی

**متن روی اسلاید:** Policy workshop → controlled data/UAT → evidence-based rollout.

**متن سخنران:**

«تصمیم پیشنهادی، شروع policy workshop میان Finance، Security و Product و اجرای v2.8.0-a با داده کنترل‌شده است. پس از آن، v2.8.0-b باید Split Matching را با invariantهای سخت و UAT مالی اثبات کند. تنها زمانی که evidence کامل، rollback قابل تمرین و approval مستقل برقرار است، قابلیت‌های certification و rollout production فعال می‌شوند. این مسیر، رشد اتوماسیون را با قابلیت دفاع مالی و امنیتی هم‌راستا نگه می‌دارد.»

## منابع

[1]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/audit.py "AuditLogger و AuditSigningKeyStore"

[2]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/bank_reconciliation.py "BankReconciliationService و کنترل‌های SoD v2.7.0"

[3]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/docs/V2_8_BANK_RECONCILIATION_CAS_CONCURRENCY_AND_SPLIT_SCRIPT_FA.md "CAS، Concurrency و Split Matching پیشنهادی"

[4]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/docs/V2_8_HMAC_AUDIT_RELEASE_GATES_FA.md "گیت‌های کیفیت و HMAC Audit v2.8.0"
