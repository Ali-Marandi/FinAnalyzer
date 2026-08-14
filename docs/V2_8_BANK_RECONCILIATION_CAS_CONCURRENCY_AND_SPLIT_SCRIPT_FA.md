# بازبینی BankReconciliationService، مدیریت CAS Conflict، آزمون‌های Concurrency و اسکریپت Split Matching v2.8.0

## وضعیت و تفکیک نسخه‌ها

`BankReconciliationService` فعلی یک سرویس واقعی v2.7.0 برای review و reclassification کنترل‌شده bank feed است. این سرویس optimistic locking، `ReconciliationCase` یا Split Matching ندارد. این مفاهیم برای v2.8.0-a/b **طراحی پیشنهادی** هستند و باید به‌صورت یک service جدید یا extension مستقل، همراه migration، test و UAT پیاده‌سازی شوند؛ نباید منطق v2.7.0 با افزودن mutationهای پیچیده به `_reconcile()` شل شود.[1] [2]

> **مرز معماری:** v2.7.0 فقط contra line یک entry استاندارد را تغییر می‌دهد. v2.8.0-b برای Split Matching، رابطه statement-to-ledger و decision history می‌سازد؛ نه اینکه entry جدید تولید کند یا مبلغ entryهای موجود را تغییر دهد.

## ۱. بازبینی کامل مسیرهای سرویس موجود v2.7.0

| متد | ورودی و مجوز | کنترل‌های اصلی | وضعیت و اثر داده |
|---|---|---|---|
| `list_work_items()` | `ledger.read` و principal معتبر | company scope، صف `needs_review`/`exception` و عدم نمایش raw payload | read-only؛ `ReconciliationWorkItem` کمینه می‌سازد |
| `summary()` | همان مجوز read | از صف کامل شمارش می‌کند | read-only؛ needs review/exception/matched/pending |
| `mark_exception()` | `bank.reconcile.match` | MFA context، mapping در company، دوره باز، non-pending، note بین ۳ تا ۵۰۰ کاراکتر | status=`exception`؛ actor/time/note ثبت؛ entry تغییر نمی‌کند |
| `match_transaction()` | `bank.reconcile.match` | status باید `needs_review` باشد | به `_reconcile()` می‌رود |
| `resolve_exception()` | `bank.reconcile.exception.resolve` | status باید `exception` باشد؛ resolver مستقل از flagger | به `_reconcile()` می‌رود |
| `_reconcile()` | permission parameterized | principal، MFA، scope، mutable period، active account، contra-only، SoD | status=`matched`؛ فقط `account_id` خط contra تغییر می‌کند |
| `_assert_open_and_mutable()` | داخلی | pending/removed، entry غیرposted و locked period را رد می‌کند | fail closed پیش از mutation |
| `_audit()` | داخلی | actor/company/session/request/source/target را ثبت می‌کند | رویداد در HMAC audit chain |

### ۱.۱. مسیر Match عادی

`match_transaction()` فقط status `needs_review` را می‌پذیرد و `_reconcile()` را با permission `bank.reconcile.match` صدا می‌زند. `_reconcile()` ابتدا note را validate، سپس `AuthorizationService.require()` را با contextی که MFA حداکثر ۱۵ دقیقه دارد اجرا می‌کند. mapping با join به `PlaidItem` و شرط `company_id` واکشی می‌شود، بنابراین شناسه provider transaction به‌تنهایی ابزار دسترسی بین‌شرکتی نیست.[1]

پس از بررسی دوره و status، account مقصد باید فعال و متعلق به همان company باشد. service حساب بانک محلی را از mapping پیدا می‌کند، انتخاب همان حساب بانک به‌عنوان contra را رد می‌کند و انتظار دارد دقیقاً یک line غیر بانکی در entry وجود داشته باشد. فقط `account_id` آن line تغییر می‌کند؛ مبلغ، تاریخ، line count و bank line تغییر نمی‌کنند. سپس status mapping به `matched` می‌رود و event `bank.reconciliation.matched` با account و resolution path در audit HMAC ثبت می‌شود.[1]

### ۱.۲. مسیر Exception و SoD

`mark_exception()` status را به `exception` تغییر می‌دهد، note، `reconciled_by_user_id` و timestamp را ثبت می‌کند، اما هیچ transaction line را تغییر نمی‌دهد. `resolve_exception()` permission حساس مستقل `bank.reconcile.exception.resolve` می‌خواهد. در `_reconcile()`، اگر actor فعلی همان user ثبت‌کننده exception باشد، سرویس event زیر را می‌سازد:

```python
self._audit(
    session, principal, "bank.reconciliation.sod_denied", company_id, mapping,
    outcome="denied", severity="warning",
    details={"reason": "exception_flagger_cannot_resolve"},
)
session.commit()  # evidence باید پیش از rollback پایدار شود
raise BankReconciliationError(
    "The user who flagged an exception cannot resolve it; an independent reviewer is required."
)
```

commit در این مورد استثنایی است و صرفاً برای حفظ evidence denial انجام می‌شود. برای mutationهای business، موفقیت باید اتمیک باشد: اگر هر کنترل پس از insertهای موقت شکست بخورد، همه تغییرات business باید rollback شوند.[1]

### ۱.۳. چرا CAS را به `_reconcile()` اضافه نمی‌کنیم؟

ساختار v2.7.0 برای یک entry با یک bank line و دقیقاً یک contra line طراحی شده است. Split Matching ممکن است یک statement line را به چند ledger entry ربط دهد و lifecycle مستقلی برای candidate، approval و certification داشته باشد. افزودن تعدادی if/version به `_reconcile()`، separation of concern را کاهش و احتمال گسترش mutationهای غیرمجاز را بالا می‌برد. پیشنهاد درست، service مستقل `StatementReconciliationDecisionService` است که به‌صورت composition از AuthorizationService و AuditLogger استفاده می‌کند؛ تنها اگر reclassification استاندارد لازم شد، می‌تواند مسیر محدود و موجود v2.7.0 را فراخوانی کند.[1] [2]

## ۲. مدیریت Conflict در service پیشنهادی CAS

### ۲.۱. errorهای domain پیشنهادی

```python
class StatementReconciliationError(RuntimeError):
    pass

class ConcurrentDecisionConflict(StatementReconciliationError):
    """The case head changed after the reviewer loaded it."""

class StaleCandidateConflict(StatementReconciliationError):
    """Candidate, statement, ledger snapshot, or policy changed."""

class ActiveAllocationConflict(StatementReconciliationError):
    """A statement line or ledger entry already belongs to an active case."""

class PolicyApprovalRequired(StatementReconciliationError):
    """The decision must be sent to an independent approver."""

class AllocationInvariantError(StatementReconciliationError):
    """Amounts, precision, currency, status, or allocation capacity are invalid."""
```

این errorها نباید پیام database یا شناسه شرکت دیگر را مستقیم به UI برگردانند. response desktop/API باید reason امن، case ID فعلی، version جاری و action پیشنهادی—مانند reload evidence یا submit for approval—را ارائه دهد.

### ۲.۲. pseudo-implementation سرویس تصمیم

```python
class StatementReconciliationDecisionService:
    def approve(self, company_id, command, principal):
        # A: Retry امن؛ نتیجه موجود را برمی‌گرداند و write جدید انجام نمی‌دهد.
        existing = self._idempotency_lookup(company_id, command.idempotency_key)
        if existing:
            return existing

        with self.database.get_session() as session:
            # B: هویت، مجوز و MFA تازه
            context = principal.authorization_context(
                company_id,
                "statement_reconciliation_approve",
                mfa_max_age=timedelta(minutes=15),
            )
            self.authorization.require(session, context, "statement.reconcile.approve")

            # C: تمام objectها server-side و در همان company بازخوانی می‌شوند.
            case = self._case_for_company(session, company_id, command.case_id)
            statement = self._statement_for_case(session, case)
            candidate = self._candidate_for_case(session, case, command.candidate_id)
            entries = self._entries_for_allocations(session, company_id, command.allocations)
            policy = self.policy_store.get_active(session, company_id)

            # D: هیچ write پیش از validation انجام نمی‌شود.
            self._assert_expected_version(case, command.expected_case_version)
            self._assert_snapshot(candidate, statement, entries, command)
            self._assert_active_policy(policy, command.policy_version)
            self._validate_allocations(statement, entries, command.allocations, policy)
            risk = self._risk_classification(statement, command.allocations, policy)
            if risk.requires_independent_approval:
                raise PolicyApprovalRequired(case.id, case.version)
            self._assert_sod(case, principal, policy)

            # E: رخداد immutable و reservationهای active فقط در transaction محلی.
            next_version = case.version + 1
            decision = self._append_decision(
                session, case=case, version=next_version, action="approved",
                principal=principal, policy=policy, command=command,
            )
            self._insert_active_reservations(session, company_id, case, statement, command.allocations, decision)
            self._insert_allocations(session, decision, command.allocations)

            # F: CAS: شرط version + state باید دقیقاً یک row را به‌روزرسانی کند.
            result = session.execute(
                update(ReconciliationCase)
                .where(
                    ReconciliationCase.id == case.id,
                    ReconciliationCase.company_id == company_id,
                    ReconciliationCase.version == command.expected_case_version,
                    ReconciliationCase.state == "submitted",
                )
                .values(
                    state="approved",
                    version=next_version,
                    current_decision_id=decision.id,
                    updated_at=utc_now(),
                )
            )
            if result.rowcount != 1:
                raise ConcurrentDecisionConflict(case.id, command.expected_case_version)

            # G: success audit و idempotency result در همان commit.
            self._record_approval_audit(session, principal, company_id, case, decision, command)
            self._store_idempotency_result(session, company_id, command.idempotency_key, decision)
            return ApprovalResult(decision.id, next_version)
```

هر unique constraint error که از `ActiveAllocationReservation` می‌آید باید در مرز service به `ActiveAllocationConflict` تبدیل شود. هر `ConcurrentDecisionConflict`، `StaleCandidateConflict`، `AllocationInvariantError` یا `AuditIntegrityError` باید از context transaction خارج شود تا decision، allocation، reservation و idempotency row جدید rollback شوند. در مقابل، SoD denialهایی که نیاز evidence مستقل دارند، باید transaction audit جدا و محدود خود را commit کنند؛ همان الگوی موجود v2.7.0.[1]

### ۲.۳. conflict-to-UX contract

| conflict | دلیل قابل فهم | UI مجاز | UI غیرمجاز |
|---|---|---|---|
| version conflict | «تصمیم از زمان مشاهده شما تغییر کرده است.» | refresh و مشاهده latest decision | retry خودکار همان command |
| stale candidate | «statement/ledger/policy تغییر کرده است.» | بازتولید candidate و review دوباره | استفاده از score/fingerprint قدیمی |
| reservation conflict | «entry قبلاً در تطبیق فعال دیگری استفاده شده است.» | نمایش conflict scoped و flag exception | تخصیص دوم یا overwrite reservation |
| independent approval | «policy بررسی مستقل می‌خواهد.» | submit به checker مستقل | approval توسط maker |
| allocation error | «مبلغ/ارز/دقت یا status معتبر نیست.» | اصلاح ورودی یا exception | round/split مخفی برای عبور از validation |

## ۳. سناریوهای آزمون invariantهای allocation

### ۳.۱. fixture پایه

برای جلوگیری از fixtureهای مبهم، هر test باید یک company، یک bank statement line، حداقل سه ledger entry posted در دوره باز، policy version مشخص، دو principal مستقل و audit key ایزوله داشته باشد. amountها باید با `Decimal` تعریف شوند. به‌طور نمونه: statement=`Decimal("120.00")`، entry A=`70.00`، B=`30.00`، C=`20.00` و currency=`USD`.

| test | setup | assertion اصلی |
|---|---|---|
| `test_exact_split_is_approved_atomically` | 70 + 30 + 20 = 120 | decision approved، سه allocation immutable، case version +1 و audit chain معتبر |
| `test_under_allocation_is_rejected` | 70 + 30 + 19 = 119 | `AllocationInvariantError`؛ version/reservation/decision جدید نداریم |
| `test_over_allocation_is_rejected` | 70 + 30 + 21 = 121 | rollback کامل؛ entryها آزاد می‌مانند |
| `test_zero_negative_and_duplicate_member_are_rejected` | allocation 0/−1 یا A دوبار | error قبل از reservation؛ ledger دست‌نخورده |
| `test_minor_unit_quantization_is_enforced` | amount با precision فراتر از currency policy | reject؛ پنهان‌سازی rounding ممنوع |
| `test_currency_and_sign_mismatch_become_exception` | EUR در برابر USD یا direction مخالف | بدون approved decision؛ policy exception/approval path |
| `test_entry_status_and_locked_period_are_rejected` | entry draft/voided یا period locked | fail closed؛ هیچ allocation ساخته نمی‌شود |
| `test_tolerance_requires_versioned_policy_and_evidence` | اختلافی که فقط در policy مجاز است | approval تنها با policy version و evidence درست |
| `test_idempotency_returns_same_result` | همان idempotency key دوبار | یک decision، یک مجموعه allocation و یک success audit |
| `test_provider_revision_supersedes_history` | revision پس از approval | decision قبلی update نمی‌شود؛ decision superseding و state review/exception ایجاد می‌شود |

هر test شکست باید postconditionهای کامل داشته باشد: تعداد `ReconciliationDecision`های جدید صفر است، allocation جدید صفر است، reservation active جدید صفر است، `ReconciliationCase.version` عوض نشده و `AuditLogger.verify_chain()` معتبر می‌ماند. برای denialهای SoD، انتظار متفاوت است: business write نباید بماند، اما event denial باید پایدار و chain معتبر باشد.

## ۴. آزمون‌های Concurrency و CAS

### ۴.۱. دو reviewer روی یک case

این مهم‌ترین سناریوی CAS است. دو thread یا process، case را با version مشترک—مثلاً ۷—می‌خوانند. سپس با `threading.Barrier` هر دو command پس از read به‌طور هم‌زمان به approve می‌رسند. انتظار: فقط یکی `approved` با version ۸ برگردد؛ دیگری `ConcurrentDecisionConflict` بگیرد. در پایان فقط یک decision approved، یک current decision head و یک مجموعه reservation فعال وجود دارد.

```python
barrier = threading.Barrier(2)
results = []

def reviewer(command, principal):
    service.test_hook_before_cas = lambda: barrier.wait(timeout=5)
    try:
        results.append(service.approve(company_id, command, principal))
    except Exception as exc:
        results.append(exc)

thread_a = Thread(target=reviewer, args=(command_v7_a, reviewer_a))
thread_b = Thread(target=reviewer, args=(command_v7_b, reviewer_b))
thread_a.start(); thread_b.start(); thread_a.join(); thread_b.join()

assert sum(isinstance(x, ApprovalResult) for x in results) == 1
assert sum(isinstance(x, ConcurrentDecisionConflict) for x in results) == 1
```

`test_hook_before_cas` باید فقط یک seam تستی باشد و در production فعال نشود. هر thread باید session مستقل و اتصال واقعی خود را داشته باشد. objectهای cached در یک SQLAlchemy session، concurrency database را شبیه‌سازی نمی‌کنند.

### ۴.۲. دو case متفاوت روی یک ledger entry

دو case می‌توانند version متفاوت داشته باشند اما به یک ledger entry مشترک تخصیص دهند. CAS head هر case به‌تنهایی کافی نیست؛ unique constraint روی `ActiveAllocationReservation(company_id, ledger_entry_id, active)` باید یکی را متوقف کند. انتظار: یکی approved و دیگری `ActiveAllocationConflict`؛ command شکست‌خورده نباید decision یا allocation نیمه‌کاره داشته باشد.

### ۴.۳. stale candidate پس از provider/policy change

reviewer candidate را باز می‌کند. پیش از approve، provider statement را اصلاح می‌کند یا policy version عوض می‌شود. command باید fingerprint/snapshot/policy mismatch را ببیند و `StaleCandidateConflict` برگرداند. هیچ راهی برای تبدیل خودکار command قدیمی به decision تازه مجاز نیست؛ reviewer باید explanation جدید را ببیند.

### ۴.۴. retry هم‌زمان همان request

برای همان `idempotency_key`، دو command هم‌زمان می‌رسند. طراحی توصیه‌شده این است که uniqueness برای idempotency key و یک state `in_progress/completed` وجود داشته باشد. یک request owner می‌شود؛ درخواست دوم یا منتظر result قطعی می‌ماند یا پاسخ «در حال پردازش» می‌گیرد، اما هیچ‌کدام decision دوم نمی‌سازند. این سناریو باید هم در موفقیت و هم در rollback آزمایش شود.

### ۴.۵. ملاحظات SQLite و production-like DB

testهای domain می‌توانند با SQLite file-backed اجرا شوند، اما تست جدی concurrency باید sessionهای مستقل، database فایل مشترک و تنظیمات transaction مشابه production داشته باشد. SQLite ممکن است به‌جای conflict منطقی، خطای lock database بدهد؛ service باید آن را با retry bounded یا domain error قابل‌فهم مدیریت کند و production gate باید همین سناریو را روی database engine هدف نیز اجرا کند. هیچ تست memory-only تک‌connection برای ادعای صحت concurrent CAS کافی نیست.

## ۵. متن اسلایدها و اسکریپت کامل Split Matching

### اسلاید ۶ — Split Matching: رابطه، نه سند جدید

**متن روی اسلاید:**

| ورودی | تصمیم تخصیص | خروجی کنترل‌شده |
|---|---|---|
| یک `BankStatementLine` با amount، currency، date و source hash | یک یا چند `CandidateAllocation` برای entryهای posted و هم‌شرکت | `ReconciliationDecision` immutable، reservation active و evidence hash |

**نکات نمایشی:**

- یک line statement تجمیعی → چند ledger entry موجود.
- `Σ allocation = statement amount`.
- بدون entry جدید، بدون تغییر مبلغ یا تاریخ، بدون mutation خودکار ledger.

**اسکریپت سخنران:**

«Split Matching برای زمانی طراحی می‌شود که یک settlement بانکی تجمیعی، چند entry موجود دفتر را پوشش می‌دهد. از نظر فنی، ما یک statement line تغییرناپذیر با hash منشأ داریم و یک یا چند allocation به entryهای موجود و posted می‌سازیم. نکته مهم این است که این قابلیت سند جدید تولید نمی‌کند و مبلغ یا تاریخ entryهای قبلی را تغییر نمی‌دهد. پذیرش فقط رابطه‌ای کنترل‌شده با decision immutable ثبت می‌کند. جمع سهم‌ها باید دقیقاً برابر statement باشد و هر سهم باید به entry معتبر همان شرکت تعلق داشته باشد. اگر این شرایط برقرار نباشد، نتیجه exception است، نه یک match اجباری برای بستن اختلاف.»

### اسلاید ۷ — Policy اختلاف را پنهان نمی‌کند

**متن روی اسلاید:**

| گیت | قاعده | شکست چه می‌شود؟ |
|---|---|---|
| Amount و precision | Decimal، allocation مثبت، nonzero و quantized | validation error و rollback |
| Currency و direction | ارز و sign سازگار؛ FX فقط workflow policy | exception یا approval بالاتر |
| Tolerance | فقط policy versionدار و evidenceدار | عدم پذیرش اختلاف پنهان |
| Idempotency و concurrency | key تکراری و CAS/reservation فعال | result قبلی یا conflict؛ نه overwrite |
| Risk و SoD | split/high-risk نیازمند approver مستقل | denial یا pending approval |

**اسکریپت سخنران:**

«در Split Matching، صرف رسیدن به جمع مبلغ کافی نیست. هر allocation باید با Decimal محاسبه شود، مثبت و غیرصفر باشد و از دقت ارزی مجاز فراتر نرود. ارز و جهت جریان نیز باید سازگار باشند. tolerance از یک policy versionدار خوانده می‌شود و همراه evidence تصمیم ذخیره می‌گردد؛ بنابراین تفاوت مبلغ با یک عدد مخفی در UI یا کد توجیه نمی‌شود. همچنین retry شبکه با idempotency key و رقابت reviewerها با Compare-and-Swap و reservation کنترل می‌شود. اگر split یا عامل ریسک بالاتر باشد، policy approval مستقل می‌خواهد. خروجی این گیت‌ها یا تصمیم قابل دفاع است یا exception قابل پیگیری؛ هیچ مسیر سومی برای پنهان‌کردن اختلاف نداریم.»

### اسلاید ۹ — v2.8.0-b: هوش توضیح‌پذیر و approval matrix

**متن روی اسلاید:**

| Candidate Explanation | Split Invariant | Approval Matrix |
|---|---|---|
| دلیل قابل‌نمایش برای تاریخ، مبلغ، merchant و account | amount/currency/reservation/status در transaction واحد | maker ≠ checker؛ high-risk به independent approval |

**نکات نمایشی:**

- explanation، rule/model version و fingerprint candidate به reviewer نمایش داده می‌شود.
- conflict باعث reload evidence است، نه retry پنهان.
- decisionها immutable و audit chain قابل verification باقی می‌ماند.

**اسکریپت سخنران:**

«v2.8.0-b فقط اضافه‌کردن یک امتیاز هوشمند نیست؛ اضافه‌کردن governance به پیشنهادهای هوشمند است. reviewer باید بداند candidate چرا پیشنهاد شده و چه rule یا نسخه مدلی در آن دخیل بوده است. پیش از approval، سرویس amount، currency، status، reservation و snapshot را دوباره بررسی می‌کند. اگر reviewer دیگری در این فاصله تصمیم را تغییر داده باشد، Compare-and-Swap conflict می‌دهد و کاربر evidence جدید را می‌بیند؛ سیستم command قدیمی را پنهانی تکرار نمی‌کند. برای split، FX، tolerance غیرصفر، مبلغ بالا یا vendor پرریسک، maker نمی‌تواند checker خودش باشد. این استقلال همراه با HMAC audit chain، تصمیم را نه فقط سریع‌تر، بلکه قابل‌توضیح و قابل دفاع می‌کند.»

## منابع

[1]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/bank_reconciliation.py "پیاده‌سازی BankReconciliationService v2.7.0"

[2]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/tests/test_bank_reconciliation_v27.py "آزمون‌های regression تطبیق بانکی v2.7.0"

[3]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/docs/V2_8_CAS_STATE_MACHINE_AND_SECURITY_ARCHITECTURE_SCRIPT_FA.md "Compare-and-Swap و معماری/امنیت پیشنهادی v2.8.0"

[4]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/docs/V2_8_OPTIMISTIC_LOCKING_ALLOCATION_TESTS_AND_RELEASE_SCRIPT_FA.md "آزمون allocation و اسکریپت انتشار v2.8.0"
