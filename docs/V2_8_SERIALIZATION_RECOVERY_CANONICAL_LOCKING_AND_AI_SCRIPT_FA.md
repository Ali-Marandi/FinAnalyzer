# بازیابی Serialization Failure، Canonical Ordering و اسکریپت معماری هوش مصنوعی FinAnalyzer v2.8.0

## وضعیت و مرز پیاده‌سازی

این سند، design specification برای v2.8.0 است. `BankReconciliationService`، HMAC audit، MFA، company scope و کنترل SoD exception در v2.7.0 وجود دارند؛ `StatementReconciliationDecisionService`، `ReconciliationCase`، Split Matching و PostgreSQL concurrency control باید پیش از rollout با migration، integration test و UAT مالی پیاده‌سازی شوند.[1] [2]

> **اصل recovery:** هر retry باید همان هدف business و همان `idempotency_key` را حفظ کند، اما transaction، session، snapshot، policy و authorization context را از ابتدا دوباره بخواند. retry یک statement یا ادامه‌دادن session شکست‌خورده مجاز نیست.

## ۱. Serialization Failure با SQLSTATE `40001`

در PostgreSQL، `Repeatable Read` و `Serializable` می‌توانند `40001` تولید کنند. در `Serializable`، هر transaction موفق همان اثر یک ترتیب سریالی را دارد؛ transactionهایی که به این تضمین آسیب می‌زنند rollback می‌شوند. PostgreSQL صراحتاً توصیه می‌کند **کل transaction**، شامل تصمیم‌گیری و تمام SQLها، retry شود.[3] [4]

### ۱.۱. چرخه صحیح recovery

| گام | عمل لازم | چرا لازم است |
|---|---|---|
| ۱ | command و `idempotency_key` را immutable نگه دارید | retry از command تازه یا تصمیم مضاعف جلوگیری می‌کند |
| ۲ | attempt تازه با Session/transaction تازه بسازید | session قبلی پس از خطای database قابل ادامه نیست |
| ۳ | principal، MFA، permission و company scope را دوباره اعتبارسنجی کنید | authorization و وضعیت session ممکن است تغییر کرده باشد |
| ۴ | case، statement، entryها، policy و candidate را دوباره load کنید | snapshot قدیمی نباید بعد از restart معتبر تلقی شود |
| ۵ | allocation/SoD/risk را دوباره محاسبه کنید | policy یا resource ownership ممکن است تغییر کرده باشد |
| ۶ | lockها، reservation، decision، CAS، audit و idempotency completion را در یک transaction اجرا کنید | atomicity باقی می‌ماند |
| ۷ | فقط `40001` و `40P01` را bounded retry کنید | validation و conflict تجاری نباید loop بسازند |
| ۸ | پس از عبور از deadline یا attempts، نتیجه conflict قابل‌فهم برگردانید | از contention storm و latency نامحدود جلوگیری می‌شود |

### ۱.۲. دسته‌بندی خطا و تصمیم retry

| خطا | SQLSTATE | retry | پاسخ سرویس |
|---|---:|---|---|
| Serialization failure | `40001` | بله، full transaction با snapshot جدید | تاخیر کوتاه و bounded؛ سپس `ConcurrentDecisionConflict` |
| Deadlock detected | `40P01` | بله، full transaction با snapshot جدید | retry با jitter؛ بررسی canonical ordering در metrics |
| Lock timeout/not available | `55P03` | سیاست محدود، نه نامحدود | `ContentionRetryLater`؛ refresh evidence |
| Reservation unique violation | `23505` | خیر | `ActiveAllocationConflict`؛ resource مالک active دارد |
| Idempotency unique violation | `23505` | خیر برای command | result completed/in-progress همان key خوانده می‌شود |
| Policy/MFA/SoD/invariant | — | هرگز | denial یا exception بدون mutation |
| Audit key/signing failure | — | خیر تا رفع علت | fail closed؛ هیچ decision approved ثبت نمی‌شود |

retry بی‌قید و شرط روی `23505` خطرناک است: این code ممکن است constraint دائمی مانند active reservation را نشان دهد، نه یک race گذرا. PostgreSQL نیز برای unique violation نسبت به `40001` احتیاط بیشتری توصیه می‌کند.[4]

### ۱.۳. کد کامل outer retry boundary

```python
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, TypeVar

from sqlalchemy.exc import DBAPIError

T = TypeVar("T")
RETRYABLE_SQLSTATES = {"40001", "40P01"}


class RetryBudgetExhausted(RuntimeError):
    """Transient database contention did not settle within the command deadline."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.025
    cap_delay_seconds: float = 0.250
    total_deadline_seconds: float = 1.250


def postgres_sqlstate(error: BaseException) -> str | None:
    original = getattr(error, "orig", None)
    return getattr(original, "pgcode", None) or getattr(original, "sqlstate", None)


def full_jitter_delay(policy: RetryPolicy, attempt: int) -> float:
    ceiling = min(policy.cap_delay_seconds, policy.base_delay_seconds * (2 ** (attempt - 1)))
    return random.uniform(0.0, ceiling)


def run_with_postgres_retry(
    operation: Callable[[int], T],
    *,
    policy: RetryPolicy,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> T:
    started = monotonic()
    last_error: DBAPIError | None = None

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return operation(attempt)
        except DBAPIError as exc:
            sqlstate = postgres_sqlstate(exc)
            last_error = exc
            elapsed = monotonic() - started
            if sqlstate not in RETRYABLE_SQLSTATES:
                raise
            if attempt == policy.max_attempts or elapsed >= policy.total_deadline_seconds:
                raise RetryBudgetExhausted(
                    f"PostgreSQL contention persisted after {attempt} attempt(s); sqlstate={sqlstate}."
                ) from exc
            delay = full_jitter_delay(policy, attempt)
            remaining = policy.total_deadline_seconds - elapsed
            if delay > remaining:
                raise RetryBudgetExhausted(
                    f"PostgreSQL contention exceeded deadline; sqlstate={sqlstate}."
                ) from exc
            sleeper(delay)

    raise RetryBudgetExhausted("Retry loop ended unexpectedly.") from last_error
```

`operation()` باید هر بار یک Session و transaction تازه ایجاد کند. retry wrapper هرگز خودش transaction نیمه‌تمام را دوباره استفاده نمی‌کند. `idempotency_key` و fingerprint command بیرون wrapper ثابت می‌مانند؛ در مقابل، resource ownership، current version، candidate fingerprint و policy version داخل هر attempt از database دوباره load می‌شوند.

### ۱.۴. مقیاس بالا: کاهش contention، بدون شل‌کردن کنترل

برای workload پرحجم، راه‌حل نخست افزایش retry نیست. transaction باید کوتاه، مبتنی بر کلیدهای indexable و عاری از call شبکه، مدل AI، فایل I/O یا انتظار انسان باشد. candidate generation باید قبل از transaction تصمیم یا در worker read-only انجام شود؛ در transaction فقط validate، lock، reserve، CAS، audit و outbox record ثبت می‌شوند. publish به SIEM/evidence store باید از outbox پس از commit انجام شود، نه در transaction مالی.

| اهرم مقیاس | اجرای ایمن | هشدار |
|---|---|---|
| Connection pool محدود | تعداد اتصال فعال Serializable را متناسب با DB محدود کنید | افزایش بی‌رویه connection، abort و memory pressure را بدتر می‌کند |
| Transaction کوتاه | فقط key-based read/lock/write در transaction | external API، OCR/AI و input کاربر در transaction ممنوع |
| Index قابل‌استفاده | index برای company/resource/state و query predicate متناظر | sequential scan در Serializable می‌تواند predicate lock گسترده‌تر بسازد |
| Sharding عملیاتی | queue/caseها را بر اساس company/account shard کنید | cross-company mutation یا bypass company scope ممنوع |
| Outbox | audit/export پس از commit توسط worker idempotent | success مالی نباید به availability سرویس خارجی وابسته شود |
| Load shedding | deadline و backpressure برای hot account | retry نامحدود باعث thundering herd می‌شود |
| Metrics | SQLSTATE، retry count، lock wait، hot resource، latency | raw statement payload یا secret در metric ثبت نشود |

مستند PostgreSQL برای عملکرد Serializable توصیه می‌کند transactionها تا حد ممکن کوتاه باشند، connectionهای فعال کنترل شوند، session idle-in-transaction رها نشود و برای جلوگیری از predicate lock گسترده، index scan در نظر گرفته شود.[3]

## ۲. Canonical Ordering برای پیشگیری از Deadlock

PostgreSQL deadlock را تشخیص می‌دهد و یکی از transactionها را abort می‌کند، اما قربانی قابل پیش‌بینی نیست. دفاع اصلی، گرفتن همه قفل‌های چندمنبعی در یک ترتیب ثابت است.[5] در این design، ترتیب resourceها از نوع و شناسه canonical به‌دست می‌آید:

```text
ReconciliationCase → BankStatementLine → JournalEntry (ascending ID) → ActiveReservation rows
```

همه code pathها—approve، reject، supersede، void و release—باید همین order را به‌کار ببرند. اگر یک path entryها را `[90, 10]` و دیگری `[10, 90]` قفل کند، امکان cycle و `40P01` بازمی‌گردد.

### ۲.۱. کد کامل lock target و canonical sort

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable, Sequence
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from core.models import BankStatementLine, JournalEntry, ReconciliationCase


class LockKind(IntEnum):
    CASE = 0
    STATEMENT_LINE = 1
    LEDGER_ENTRY = 2


@dataclass(frozen=True, order=True)
class LockTarget:
    kind: LockKind
    numeric_id: int


def canonical_lock_targets(
    *,
    case_id: int,
    statement_line_id: int,
    ledger_entry_ids: Iterable[int],
) -> tuple[LockTarget, ...]:
    """Return unique lock targets in the only approved acquisition order."""
    targets = {
        LockTarget(LockKind.CASE, case_id),
        LockTarget(LockKind.STATEMENT_LINE, statement_line_id),
        *(LockTarget(LockKind.LEDGER_ENTRY, int(entry_id)) for entry_id in ledger_entry_ids),
    }
    return tuple(sorted(targets))
```

### ۲.۲. کد کامل acquisition در service layer

```python
class StatementReconciliationDecisionService:
    def _lock_target(self, session: Session, company_id: int, target: LockTarget) -> None:
        if target.kind is LockKind.CASE:
            row = session.execute(
                select(ReconciliationCase.id)
                .where(
                    ReconciliationCase.id == target.numeric_id,
                    ReconciliationCase.company_id == company_id,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                raise ReconciliationNotFound("Case was not found in the current company scope.")
            return

        if target.kind is LockKind.STATEMENT_LINE:
            row = session.execute(
                select(BankStatementLine.id)
                .where(
                    BankStatementLine.id == target.numeric_id,
                    BankStatementLine.company_id == company_id,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                raise ReconciliationNotFound("Statement line was not found in the current company scope.")
            return

        if target.kind is LockKind.LEDGER_ENTRY:
            row = session.execute(
                select(JournalEntry.id)
                .where(
                    JournalEntry.id == target.numeric_id,
                    JournalEntry.company_id == company_id,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                raise ReconciliationNotFound("Ledger entry was not found in the current company scope.")
            return

        raise AssertionError(f"Unhandled lock target: {target.kind}")

    def _lock_approval_resources(
        self,
        session: Session,
        *,
        company_id: int,
        case_id: int,
        statement_line_id: int,
        ledger_entry_ids: Sequence[int],
    ) -> tuple[LockTarget, ...]:
        ordered = canonical_lock_targets(
            case_id=case_id,
            statement_line_id=statement_line_id,
            ledger_entry_ids=ledger_entry_ids,
        )
        for target in ordered:
            self._lock_target(session, company_id, target)
        return ordered
```

`FOR UPDATE` باید پس از minimal identity/scope check ولی پیش از validationهای وابسته به resource اجرا شود. به این ترتیب، هر attempt وضعیت پایدار resourceها را زیر قفل می‌بیند. اگر read-only candidate service به snapshot آزاد نیاز دارد، آن کار قبل از transaction approval انجام می‌شود؛ approval همیشه data را دوباره load می‌کند.

### ۲.۳. کد کامل approval transaction با lock، reservation، CAS و audit

```python
class StatementReconciliationDecisionService:
    def approve_once(self, company_id, command, principal, *, attempt: int):
        # هر فراخوانی توسط run_with_postgres_retry در Session جدید اجرا می‌شود.
        with self.database.get_session() as session:
            with session.begin():
                context = principal.authorization_context(
                    company_id,
                    "statement_reconciliation_approve",
                    mfa_max_age=timedelta(minutes=15),
                )
                self.authorization.require(session, context, "statement.reconcile.approve")

                # idempotency claim از داخل همین transaction گرفته می‌شود.
                claim = self._claim_or_read_completed_result(
                    session,
                    company_id=company_id,
                    actor_id=principal.user_id,
                    command=command,
                )
                if claim.completed_result is not None:
                    return claim.completed_result
                if claim.in_progress_by_other_actor:
                    raise IdempotencyInProgress(claim.record_id)

                # ابتدا فقط identityهای command گرفته می‌شوند؛ پس از lock، details دوباره load می‌شوند.
                self._assert_command_shape(command)
                self._lock_approval_resources(
                    session,
                    company_id=company_id,
                    case_id=command.case_id,
                    statement_line_id=command.statement_line_id,
                    ledger_entry_ids=[item.ledger_entry_id for item in command.allocations],
                )

                case = self._load_case_for_update(session, company_id, command.case_id)
                statement = self._load_statement_for_update(session, company_id, command.statement_line_id)
                entries = self._load_entries_for_update(
                    session, company_id, [item.ledger_entry_id for item in command.allocations]
                )
                candidate = self._load_candidate(session, company_id, command.candidate_id)
                policy = self.policy_store.get_active(session, company_id)

                self._assert_case_version(case, command.expected_case_version)
                self._assert_candidate_and_snapshots(candidate, statement, entries, command)
                self._assert_policy_version(policy, command.policy_version)
                self._assert_case_state(case, allowed={"submitted"})
                self._validate_allocations(statement, entries, command.allocations, policy)
                self._assert_sod_and_risk_route(case, command, principal, policy)

                decision = self._append_immutable_decision(
                    session, case, command, principal, policy, action="approved"
                )
                self._insert_reservations_in_canonical_order(
                    session, company_id, statement, entries, command.allocations, case, decision
                )
                self._insert_allocations(session, decision, command.allocations)

                rowcount = self._compare_and_swap_case_head(
                    session,
                    company_id=company_id,
                    case_id=case.id,
                    expected_version=command.expected_case_version,
                    next_state="approved",
                    decision_id=decision.id,
                )
                if rowcount != 1:
                    raise ConcurrentDecisionConflict(case.id, command.expected_case_version)

                result = ApprovalResult(decision_id=decision.id, case_version=case.version + 1)
                self._complete_idempotency_claim(session, claim, result)
                self._audit_approval_success(
                    session, principal, company_id, case, decision, command, attempt
                )
                return result
```

unique reservation conflict از `IntegrityError` باید در `_insert_reservations_in_canonical_order()` با savepoint گرفته و به `ActiveAllocationConflict` تبدیل شود. این exception از `approve_once()` خارج می‌شود تا transaction کامل rollback شود. `40001` و `40P01` نیز به outer retry boundary می‌رسند. `SoD` denial متفاوت است: همانند v2.7.0، evidence denial در transaction audit محدود و مستقل commit، سپس business action رد می‌شود.[1]

### ۲.۴. جلوگیری از قفل‌گیری پنهان

| ضدالگو | چرا خطرناک است | جایگزین |
|---|---|---|
| قفل‌کردن entryها به ترتیب UI | دو reviewer ممکن است order مخالف بفرستند | `canonical_lock_targets()` با sort نوع/شناسه |
| `SELECT` سپس `INSERT` بدون unique index | race بین check و write | partial unique index + translate `23505` |
| external API زیر `FOR UPDATE` | مدت lock و deadlock را زیاد می‌کند | API/AI قبل یا پس از transaction با outbox |
| session reuse پس از `40001` | state خطادار/قدیمی ممکن است باقی بماند | Session و transaction کاملاً تازه |
| retry همه خطاها | denial و unique conflict دائمی را loop می‌کند | allowlist `40001` و `40P01` |
| advisory lock به‌تنهایی | DB usage آن را enforce نمی‌کند | reservation/CAS source of truth؛ advisory فقط مکمل اختیاری |

## ۳. متن و اسکریپت کامل اسلایدهای معماری هوش مصنوعی و اتوماسیون مالی

## Cover — FinAnalyzer Enterprise v2.8.0

**متن روی اسلاید:**

FinAnalyzer Enterprise v2.8.0

معماری هوش مصنوعی و تطبیق بانکی کنترل‌شده

*از statement تا تصمیم قابل‌توضیح، evidence زنجیره‌ای و Close قابل دفاع*

**اسکریپت سخنران:**

«این ارائه، v2.8.0 را به‌عنوان مسیر تکامل FinAnalyzer از review ساده bank feed به سمت اتوماسیون مالی کنترل‌شده معرفی می‌کند. هدف ما این نیست که هوش مصنوعی جایگزین مسئولیت مالی شود. هدف، کوتاه‌کردن زمان review، افزایش قابلیت توضیح و تولید evidence قابل دفاع برای Close است. به همین دلیل، معماری بر human approval، policy، MFA، تفکیک وظایف و audit زنجیره‌ای بنا می‌شود.»

## اسلاید ۱ — هوش مالی در مرز کنترل قرار می‌گیرد

**متن روی اسلاید:**

| v2.7.0 | شکاف Close سازمانی | v2.8.0 |
|---|---|---|
| Feed Review کنترل‌شده | Statement مستقل و اثبات مانده | Statement Intelligence + Certification |

**اسکریپت سخنران:**

«v2.7.0 تراکنش‌های bank feed را وارد صف review کرد، تطبیق را contra-only نگه داشت و موارد بررسی‌نشده را blocker Close قرار داد. اما Close سازمانی فقط دانستن status feed نیست؛ باید بتوان statement خارجی، ledger و مانده پایان دوره را به هم مرتبط و مستند کرد. v2.8.0 این شکاف را با import کنترل‌شده، relationهای تطبیق، decision history و certification مبتنی بر evidence هدف می‌گیرد. خروجی مورد انتظار فقط match rate نیست؛ یک مسیر قابل توضیح برای controller و حسابرس است.»

## اسلاید ۲ — سه لایه، یک مرز مالی

**متن روی اسلاید:**

| Import & Provenance | Candidate Engine | Decision Service & Evidence |
|---|---|---|
| schema، hash و scope | rule/model، score و explanation | permission، MFA، SoD، policy، CAS و audit |

**اسکریپت سخنران:**

«برای حفظ کنترل، معماری به سه لایه تقسیم می‌شود. لایه نخست statement را با schema validation، hash و provenance وارد می‌کند. لایه دوم rules یا مدل را برای candidate و explanation به‌کار می‌گیرد؛ این لایه هیچ mutation مالی انجام نمی‌دهد. لایه سوم، service تصمیم است: principal، MFA، permission، policy، SoD، allocation و concurrency را بررسی می‌کند و سپس decision immutable و audit evidence ثبت می‌کند. این جداسازی اجازه می‌دهد مدل هوشمند بهتر شود، بدون اینکه مسیر تغییر دفتر باز شود.»

## اسلاید ۳ — AI پیشنهاد می‌دهد؛ انسان تصمیم می‌گیرد

**متن روی اسلاید:**

Candidate explanation → permission + MFA تازه + policy → human approval → immutable decision

**اسکریپت سخنران:**

«مدل می‌تواند براساس reference، مبلغ، تاریخ یا merchant پیشنهاد بدهد و دلیل پیشنهاد را نمایش دهد. اما confidence مدل یک permission نیست. تصمیم مالی فقط زمانی ساخته می‌شود که identity معتبر باشد، MFA تازه باشد، permission و policy اجازه بدهند و reviewer انسانی تصمیم را تأیید کند. نتیجه یک decision immutable است که actor، policy version، candidate fingerprint و evidence hash دارد. بنابراین AI برای افزایش بهره‌وری استفاده می‌شود، نه برای انتقال مسئولیت مالی به یک مدل.»

## اسلاید ۴ — هر تصمیم، evidence زنجیره‌ای است

**متن روی اسلاید:**

Redact → Canonical Payload → HMAC-SHA256 / DPAPI → Verify → Export

**اسکریپت سخنران:**

«هر success، denial و exception باید به evidence تبدیل شود. AuditLogger ابتدا secrets را redaction می‌کند. سپس payload canonical شامل sequence، timestamp، previous hash و key ID ساخته و با HMAC-SHA256 امضا می‌شود. در Windows، کلید audit با DPAPI محافظت می‌شود. verification، ترتیب، previous hash، HMAC و checkpoint را بررسی می‌کند. برای immutability سازمانی، v2.8.0-c مسیر export به evidence store مستقل یا SIEM را در نظر می‌گیرد؛ زیرا audit محلی tamper-evident است، اما anchor خارجی برای ادعای نگهداشت سازمانی لازم است.»

## اسلاید ۵ — Split Matching رابطه می‌سازد

**متن روی اسلاید:**

| Statement line | Allocation decision | Ledger entryهای موجود |
|---|---|---|
| مبلغ، ارز، تاریخ و hash منشأ | `Σ allocation = statement amount` | posted، هم‌شرکت و قابل‌تخصیص |

- بدون journal entry جدید
- بدون تغییر مبلغ/تاریخ/lineهای entry موجود
- اختلاف خارج policy → exception

**اسکریپت سخنران:**

«یک settlement تجمیعی ممکن است چند entry موجود دفتر را پوشش دهد. Split Matching رابطه و سهم هر entry را به‌صورت allocation ثبت می‌کند؛ سند جدید نمی‌سازد و amount یا date entry موجود را بازنویسی نمی‌کند. مجموع سهم‌ها باید برابر statement باشد، entryها باید posted و هم‌شرکت باشند و اختلاف بدون policy به exception می‌رود. این محدودیت‌ها عمداً مانع از آن می‌شوند که تطبیق به ابزاری برای پنهان‌کردن اختلاف یا تولید mutation حسابداری کنترل‌نشده تبدیل شود.»

## اسلاید ۶ — Allocation با invariant محافظت می‌شود

**متن روی اسلاید:**

| Amount | Currency | Eligibility | Policy | Governance |
|---|---|---|---|---|
| Decimal و جمع دقیق | sign و minor unit | period/status/reservation | tolerance نسخه‌دار | SoD و approval متناسب با ریسک |

**اسکریپت سخنران:**

«جمع دقیق شرط لازم است، نه کافی. amount با Decimal محاسبه می‌شود و سهم صفر، منفی یا خارج از precision ارز پذیرفته نیست. direction و currency باید سازگار باشند. entry باید posted، در دوره باز و بدون owner active دیگر باشد. tolerance فقط از policy versionدار می‌آید و evidence دارد. split، FX، مبلغ بالا یا vendor پرریسک مسیر independent approval را فعال می‌کند. شکست هرکدام از این invariantها به rollback یا exception قابل پیگیری منتهی می‌شود، نه یک match اجباری.»

## اسلاید ۷ — Retry و Concurrency کنترل می‌شوند

**متن روی اسلاید:**

| Idempotency | Compare-and-Swap | Active Reservation |
|---|---|---|
| retry همان command → همان result | version قدیمی → reload evidence | resource فعال دیگر → rollback/conflict |

**اسکریپت سخنران:**

«در عملیات مالی، retry شبکه و هم‌زمانی طبیعی هستند، اما نباید decision تکراری یا overwrite پنهان ایجاد کنند. idempotency key همان command را به همان result متصل می‌کند. Compare-and-Swap بررسی می‌کند case از زمان مشاهده reviewer تغییر نکرده باشد. Active Reservation نیز جلوی تخصیص هم‌زمان statement یا entry به case دیگر را می‌گیرد. برای PostgreSQL، deadlock و serialization failure فقط در outer boundary و با transaction کاملاً جدید retry می‌شوند؛ ولی unique conflict یا SoD violation retry نمی‌شوند. این تمایز، availability را با integrity هم‌راستا می‌کند.»

## اسلاید ۸ — SoD در service layer اجرا می‌شود

**متن روی اسلاید:**

| Role/Actor | ممنوعیت | Evidence |
|---|---|---|
| Exception flagger | حل‌کردن exception خودش | `sod_denied` در HMAC audit |
| Maker | approval پرریسک خود | independent checker لازم |
| Controller/Certifier | bypass policy | sign-off مستقل و policy-bound |

**اسکریپت سخنران:**

«SoD یک ویژگی UI نیست. در v2.7.0، service بررسی می‌کند user ثبت‌کننده exception نمی‌تواند همان exception را resolve کند؛ اگر تلاش کند، denial قبل از raise در HMAC audit ثبت می‌شود. در v2.8.0، همین منطق برای maker، checker و certifier توسعه می‌یابد. actor ID، company scope، permission، MFA و policy version در service layer کنترل می‌شوند. در نتیجه حتی اگر کلاینت دستکاری شود یا کاربر permissionهای متعددی داشته باشد، مسیر ممنوع در domain service متوقف و evidence آن حفظ می‌شود.»

## اسلاید ۹ — Rollout کنترل را مقدم می‌داند

**متن روی اسلاید:**

| موج a | موج b | موج c |
|---|---|---|
| import، deterministic match، immutable history، CAS | explanation، Split Matching، reservation، approval matrix | certification، exception SLA، evidence export، Close re-check |

**اسکریپت سخنران:**

«این roadmap، AI را یک‌جا به production نمی‌برد. موج a، correctness داده و history تصمیم را تثبیت می‌کند. موج b فقط پس از گذر از invariantهای allocation، concurrency، SoD negative test و UAT مالی، explanation و Split Matching را اضافه می‌کند. موج c، certification، exception SLA، evidence export و Close re-check را تکمیل می‌کند. گیت‌های خروج، evidence، rollback و sign-off دارند؛ confidence مدل هرگز به‌تنهایی معیار Go نیست.»

## اسلاید ۱۰ — تصمیم: کنترل، سپس مقیاس

**متن روی اسلاید:**

Policy workshop → controlled data/UAT → evidence-based rollout

**اسکریپت سخنران:**

«گام بعدی، policy workshop مشترک میان Finance، Security و Product است. سپس موج a با داده کنترل‌شده و معیارهای پذیرش روشن اجرا می‌شود. پس از آن، موج b باید همزمان درستی allocation، independence actorها و تاب‌آوری concurrency را اثبات کند. تنها وقتی UAT مالی، audit integrity، rollback قابل تمرین و evidence قابل راستی‌آزمایی کامل شد، موج c و rollout گسترده منطقی است. این مسیر اجازه می‌دهد اتوماسیون رشد کند، اما هر تصمیم همچنان قابل دفاع، قابل بازبینی و تحت کنترل سازمان باقی بماند.»

## منابع

[1]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/bank_reconciliation.py "BankReconciliationService v2.7.0"

[2]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/audit.py "AuditLogger و AuditSigningKeyStore"

[3]: https://www.postgresql.org/docs/current/transaction-iso.html "PostgreSQL Transaction Isolation"

[4]: https://www.postgresql.org/docs/current/mvcc-serialization-failure-handling.html "PostgreSQL Serialization Failure Handling"

[5]: https://www.postgresql.org/docs/current/explicit-locking.html "PostgreSQL Explicit Locking and Deadlocks"
