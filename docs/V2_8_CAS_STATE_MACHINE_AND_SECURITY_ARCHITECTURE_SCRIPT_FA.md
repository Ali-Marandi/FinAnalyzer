# Compare-and-Swap، ماشین وضعیت و اسکریپت معماری/امنیت FinAnalyzer v2.8.0

## وضعیت و مرز این سند

این سند، specification پیشنهادی برای موج‌های v2.8.0 است. بخش‌هایی از کنترل‌های امنیتیِ مرجع—از جمله HMAC audit، DPAPI برای کلید audit، principal معتبر، MFA تازه، company scope، RBAC و SoD exception—در کد v2.7.0 وجود دارند. `ReconciliationCase`، `ReconciliationDecision`، Compare-and-Swap و ماشین وضعیت Split Matching، طراحی‌های لازم برای پیاده‌سازی بعدی v2.8.0 هستند و تا پیش از implementation، test، UAT و approval نباید قابلیت منتشرشده تلقی شوند.[1] [2]

> **اصل mutation:** generation و explanation فقط read-only هستند. تنها یک command معتبر که permission، MFA، policy، SoD، snapshot و optimistic version را پاس می‌کند، می‌تواند یک decision جدید و allocationهای آن را در transaction واحد ثبت کند.

## ۱. قرارداد داده و وضعیت پیشنهادی

### ۱.۱. جداسازی history از وضعیت جاری

`ReconciliationDecision` یک record append-only است. هیچ endpoint یا service عمومی نباید آن را update/delete کند. `ReconciliationCase` فقط head mutable جریان است و برای optimistic locking استفاده می‌شود. در نتیجه، تاریخچه تصمیم‌ها باقی می‌ماند اما state جاری به‌صورت کنترل‌شده جلو می‌رود.

| موجودیت | مسئولیت | mutable؟ | قاعده امنیتی |
|---|---|---:|---|
| `ReconciliationCase` | وضعیت جاری، version و پیوند current decision | بله، فقط با CAS | company scoped و تغییر تنها در service layer |
| `ReconciliationDecision` | رخداد submit/approve/reject/exception/supersede | خیر | append-only، actor/policy/evidence اجباری |
| `CandidateAllocation` | سهم immutable entryهای انتخاب‌شده | خیر | فقط همراه decision موفق درج می‌شود |
| `ActiveAllocationReservation` | مالکیت عملیاتی entry/statement در تصمیم active | بله، محدود | uniqueness و lifecycle مستقل از history |
| `ReconciliationCandidate` | پیشنهاد rules/AI و explanation | نسخه‌دار | فاقد mutation ledger |

### ۱.۲. وضعیت‌های `ReconciliationCase`

| وضعیت | معنا | transition مجاز | effect بر Close |
|---|---|---|---|
| `draft` | candidate تولید شده، اما برای تصمیم آماده نیست یا هنوز submit نشده است | `submitted`، `exception`، `cancelled` | معمولاً blocker policy |
| `submitted` | maker evidence را submit کرده است | `approved`، `pending_independent_approval`، `rejected`، `exception` | blocker تا تصمیم نهایی |
| `pending_independent_approval` | policy split/high-risk یا FX reviewer مستقل می‌خواهد | `approved`، `rejected`، `exception` | blocker |
| `approved` | decision معتبر و reservationها ثبت شده‌اند | `superseded`، `voided` | مطابق policy قابل certification |
| `rejected` | candidate رد شده و اثر مالی ندارد | `draft` با candidate تازه یا `exception` | blocker تا اقدام بعدی |
| `exception` | اختلاف، evidence ناکافی یا policy violation | `submitted` با evidence جدید، `closed_exception` | blocker در صورت policy-blocking |
| `superseded` | provider revision، policy change یا decision جدید، decision قبلی را جایگزین کرده است | terminal در history | case تازه/بازبینی‌شده را لازم می‌کند |
| `voided` | statement line حذف یا غیرقابل اتکا شده است | terminal در history | اثر مستقیم ledger ندارد؛ نیازمند review |
| `cancelled` | پیش از approval لغو شده است | terminal در history | بدون اثر مالی |

هر transition یک `ReconciliationDecision` تازه می‌سازد. برای نمونه، تغییر از `approved` به `superseded` هرگز update وضعیت در decision پیشین نیست؛ یک decision جدید با `supersedes_decision_id`، reason، actor و evidence دارد، سپس `ReconciliationCase.current_decision_id` با CAS به آن اشاره می‌کند.

## ۲. command contract و پیش‌شرط‌ها

```python
@dataclass(frozen=True)
class ApproveReconciliationCommand:
    case_id: UUID
    expected_case_version: int
    candidate_id: UUID
    candidate_fingerprint: str
    statement_line_version: int
    ledger_snapshot_versions: Mapping[int, int]
    policy_version: str
    allocations: tuple[AllocationInput, ...]
    idempotency_key: UUID
    note: str
```

server نباید صرفاً به `case_id` یا داده‌های نمایش‌داده‌شده در UI اعتماد کند. `expected_case_version` از overwrite جلوگیری می‌کند؛ fingerprint از پذیرش candidate دیگر جلوگیری می‌کند؛ snapshot versionها تغییر statement/ledger پس از مشاهده را آشکار می‌کنند؛ policy version مانع اعمال policy قدیمی می‌شود و idempotency key retry شبکه را از تصمیم دوم جدا می‌کند.

| پیش‌شرط | بررسی service layer | نتیجه نقض |
|---|---|---|
| هویت | `AuthenticatedPrincipal` معتبر | `IdentityValidationError`، بدون mutation |
| مجوز و MFA | permission لازم و MFA تازه | authorization denial؛ audit طبق policy |
| scope | case، statement، entry و account همگی در company مجاز | not-found/denied بدون افشای cross-company data |
| version | `expected_case_version` با head فعلی برابر | `ConcurrentDecisionConflict` و reload لازم |
| snapshot | fingerprint و versionهای source معتبر | `StaleCandidateConflict` و بازتولید evidence |
| policy | policy version فعلی و ruleهای risk برقرار | `PolicyChangedConflict` یا مسیر approval جدید |
| allocation | amount/currency/precision/reservation/status معتبر | validation error یا exception |
| SoD | maker/approver/certifier مستقل در policyهای لازم | denial و HMAC evidence |

## ۳. شبه‌کد کامل Compare-and-Swap

### ۳.۱. پذیرش یک decision کم‌ریسک

در این pseudocode، همه تغییرات business در یک database transaction انجام می‌شوند. اگر به هر دلیل exception ایجاد شود، هیچ case head، decision، allocation یا reservation جدیدی باقی نمی‌ماند. Audit event نیز داخل همان transaction درج می‌شود تا نتیجه موفق و evidence آن اتمیک باشند.

```python
class ReconciliationDecisionService:
    def approve(
        self,
        company_id: int,
        command: ApproveReconciliationCommand,
        principal: AuthenticatedPrincipal,
    ) -> ApprovalResult:
        # 0. اعتبار retry پیش از انجام کار جدید
        existing = self._find_idempotent_result(
            company_id, command.idempotency_key, principal.user_id
        )
        if existing:
            return existing

        with self.database.get_session() as session:
            # 1. هویت، MFA و permission
            context = principal.authorization_context(
                company_id,
                reason="statement_reconciliation_approve",
                mfa_max_age=timedelta(minutes=15),
            )
            self.authorization.require(
                session, context, "statement.reconcile.approve"
            )

            # 2. واکشی مجدد server-side؛ هیچ data نمایش‌داده‌شده UI معتبر تلقی نمی‌شود
            case = self._case_for_company(session, company_id, command.case_id)
            statement = self._statement_line_for_case(session, case)
            candidate = self._candidate_for_case(session, case, command.candidate_id)
            policy = self.policy_store.get_active(session, company_id)
            entries = self._ledger_entries_for_allocations(
                session, company_id, command.allocations
            )

            # 3. checks بدون write
            self._assert_case_version(case, command.expected_case_version)
            self._assert_candidate_fingerprint(candidate, command.candidate_fingerprint)
            self._assert_snapshots(statement, entries, command)
            self._assert_policy_version(policy, command.policy_version)
            self._assert_case_state(case, allowed={"submitted"})
            self._assert_reconcilable(statement, entries)
            self._validate_allocations(statement, entries, command.allocations, policy)

            risk = self._risk_engine.classify(statement, command.allocations, policy)
            if risk.requires_independent_approval:
                raise ApprovalRequired(
                    case_id=case.id,
                    current_version=case.version,
                    required_role="statement.reconcile.independent_approve",
                )
            self._assert_maker_is_allowed_to_approve(case, principal, policy)

            # 4. decision immutable هنوز به head متصل نشده است
            new_version = case.version + 1
            decision = ReconciliationDecision(
                id=uuid4(),
                case_id=case.id,
                decision_version=new_version,
                action="approved",
                actor_id=principal.user_id,
                policy_version=policy.version,
                candidate_fingerprint=candidate.fingerprint,
                evidence_hash=self._evidence_hash(statement, entries, command.allocations, policy),
                supersedes_decision_id=case.current_decision_id,
                occurred_at=utc_now(),
            )
            session.add(decision)
            session.flush()

            # 5. reservationهای active؛ unique constraint، رقابت میان caseهای متفاوت را متوقف می‌کند
            self._reserve_statement_line(session, company_id, statement.id, case.id, decision.id)
            for allocation in command.allocations:
                self._reserve_ledger_entry(
                    session, company_id, allocation.ledger_entry_id, case.id, decision.id
                )
                session.add(CandidateAllocation(
                    decision_id=decision.id,
                    ledger_entry_id=allocation.ledger_entry_id,
                    amount=allocation.amount,
                    currency=statement.currency,
                ))
            session.flush()

            # 6. Compare-and-Swap تنها نقطه mutable transition
            updated = session.execute(
                update(ReconciliationCase)
                .where(
                    ReconciliationCase.id == case.id,
                    ReconciliationCase.company_id == company_id,
                    ReconciliationCase.version == command.expected_case_version,
                    ReconciliationCase.state == "submitted",
                )
                .values(
                    state="approved",
                    version=new_version,
                    current_decision_id=decision.id,
                    updated_at=utc_now(),
                )
            )
            if updated.rowcount != 1:
                # خروج از context باعث rollback decision، allocations و reservations می‌شود.
                raise ConcurrentDecisionConflict(
                    case_id=case.id,
                    expected_version=command.expected_case_version,
                )

            # 7. evidence موفقیت؛ داخل همان transaction
            self.audit_logger.record(
                session,
                action="statement.reconciliation.approved",
                category="banking",
                outcome="success",
                severity="notice",
                actor_id=principal.user_id,
                company_id=company_id,
                session_id=principal.session_id,
                request_id=str(command.idempotency_key),
                source="statement_reconciliation",
                target_type="reconciliation_case",
                target_id=str(case.id),
                details={
                    "decision_id": str(decision.id),
                    "decision_version": new_version,
                    "policy_version": policy.version,
                    "allocation_count": len(command.allocations),
                    "risk_tier": risk.tier,
                },
            )
            self._save_idempotency_result(
                session, company_id, command.idempotency_key, principal.user_id, decision.id
            )
            return ApprovalResult(decision_id=decision.id, case_version=new_version)
```

نکته کلیدی: `session.flush()` موفق بودن business operation را ثابت نمی‌کند. ممکن است decision و reservation به‌طور موقت insert شوند، اما اگر CAS یا audit failure رخ دهد، خروج exception از context باید همه آن‌ها را rollback کند. در پیاده‌سازی production، integrity error ناشی از uniqueness reservation باید به خطای domain تبدیل شود تا UI آن را conflict، نه خطای مبهم server، نشان دهد.

### ۳.۲. مسیر high-risk و approval مستقل

maker نباید در همان command یک split/high-risk را `approved` کند. او یک decision `submitted` ثبت می‌کند و head را با CAS به `pending_independent_approval` منتقل می‌کند. سپس approver مستقل، command جدا با version جدید می‌فرستد.

```python
def submit_for_independent_approval(...):
    # identity, scope, MFA, candidate/policy/allocation validation مانند approve
    assert risk.requires_independent_approval
    assert case.created_by_user_id == principal.user_id or principal.has("statement.reconcile.submit")

    decision = append_decision(action="submitted", actor=principal, ...)
    cas_transition(
        case_id=case.id,
        expected_version=command.expected_case_version,
        from_states={"draft", "submitted"},
        to_state="pending_independent_approval",
        current_decision_id=decision.id,
    )
    audit("statement.reconciliation.submitted", outcome="success")


def independently_approve(...):
    # full re-read و validation دوباره
    assert case.state == "pending_independent_approval"
    if case.created_by_user_id == principal.user_id or case.submitted_by_user_id == principal.user_id:
        record_sod_denial_and_commit_before_raise(...)
        raise SeparationOfDutiesError("Independent approval is required.")
    # reserve + append approved decision + CAS + audit، در transaction واحد
```

برای denialهایی که باید حتی در صورت رد business operation باقی بمانند، الگوی v2.7.0 حفظ می‌شود: رویداد denial HMAC ثبت، transaction آن evidence به‌طور مستقل commit و سپس exception raise می‌شود. این الگو فقط برای evidence denial به‌کار می‌رود؛ هرگز نباید برای حفظ یک mutation نیمه‌تمام business استفاده شود.

### ۳.۳. handler خطا و پاسخ API/Desktop

| وضعیت فنی | پاسخ سرویس | رفتار UI مجاز | وضعیت داده |
|---|---|---|---|
| idempotency hit | همان decision/result پیشین | نمایش success قبلی | هیچ write جدیدی ندارد |
| `ConcurrentDecisionConflict` | نسخه و current state جدید برگردد | refresh evidence و review مجدد | rollback کامل command دوم |
| `StaleCandidateConflict` | علت تغییر statement/ledger/policy برگردد | بازتولید candidate؛ عدم submit پنهان | rollback کامل |
| reservation unique conflict | entry/statement already active را اعلام کند | نمایش conflict بدون افشای داده خارج scope | rollback کامل |
| validation failure | field-level reason امن | اصلاح allocation یا flag exception | rollback کامل |
| policy requires independent approval | state pending یا requirement مناسب | submit برای checker، نه bypass | فقط transition مجاز ثبت می‌شود |
| SoD denial | denied + audit event | عملیات متوقف؛ reviewer مستقل لازم | بدون allocation/decision موفق |
| audit/key failure | fail closed | توقف تصمیم و اعلام خطای امن | rollback کامل |

## ۴. شبه‌کد transition عمومی و invalidation

```python
def cas_transition(session, *, case_id, company_id, expected_version,
                   from_states, to_state, current_decision_id):
    result = session.execute(
        update(ReconciliationCase)
        .where(
            ReconciliationCase.id == case_id,
            ReconciliationCase.company_id == company_id,
            ReconciliationCase.version == expected_version,
            ReconciliationCase.state.in_(from_states),
        )
        .values(
            state=to_state,
            version=expected_version + 1,
            current_decision_id=current_decision_id,
            updated_at=utc_now(),
        )
    )
    if result.rowcount != 1:
        raise ConcurrentDecisionConflict(case_id, expected_version)
```

provider revision و statement removal نباید decision approved قبلی را rewrite کنند. handler باید decision `superseded` یا `voided` جدید بسازد، reservationهای active را طبق policy release/expire کند و head را با CAS به `draft` یا `exception` منتقل کند. اگر case head از snapshot handler تغییر کرده باشد، handler باید retry bounded با re-read یا conflict workflow داشته باشد؛ هرگز نباید `UPDATE` بدون version condition انجام دهد.

## ۵. متن اسلایدها و اسکریپت کامل سخنران: معماری و امنیت v2.8.0

### اسلاید ۳ — AI پیشنهاد می‌دهد؛ انسان تصمیم می‌گیرد

**متن روی اسلاید:**

| Candidate Intelligence | Control Gate | Financial Decision |
|---|---|---|
| امتیازدهی reference، مبلغ، تاریخ و merchant | Permission، MFA تازه، policy version و human approval | decision immutable، evidence hash و mutation service-controlled |

**اسکریپت سخنران:**

«در معماری v2.8.0، هوش مصنوعی یک لایه پیشنهاددهنده است، نه یک actor مالی. candidate generation می‌تواند از reference، مبلغ، تاریخ یا merchant برای پیشنهاد رابطه میان statement و ledger استفاده کند و دلیل پیشنهاد را نشان دهد. اما حتی confidence بالا هم مجوز تغییر دفتر نیست. تصمیم فقط زمانی شکل می‌گیرد که principal معتبر باشد، MFA تازه باشد، policy فعال تصمیم را مجاز بداند و reviewer انسانی تأیید کند. سپس چیزی که ثبت می‌شود یک decision تغییرناپذیر با actor، policy version و evidence hash است. بنابراین AI زمان review را کاهش می‌دهد، اما مرز مسئولیت، مجوز و تغییر مالی را جابه‌جا نمی‌کند.»

### اسلاید ۴ — هر تصمیم به زنجیره HMAC متصل است

**متن روی اسلاید:**

| ۱. پاکسازی رخداد | ۲. canonical payload | ۳. امضای HMAC-SHA256 | ۴. verification |
|---|---|---|---|
| redact secretها | sequence، timestamp UTC، previous hash و key ID | کلید audit محافظت‌شده با DPAPI در Windows | sequence، hash پیوندها و checkpoint بررسی می‌شوند |

**اسکریپت سخنران:**

«امنیت این معماری به مشاهده تصمیم نهایی محدود نیست؛ ما باید بتوانیم رخدادهای مسیر تصمیم را هم راستی‌آزمایی کنیم. AuditLogger ابتدا details را از token، secret، password و داده‌های حساس پاکسازی می‌کند. سپس payloadی canonical با timestamp UTC، sequence و previous hash می‌سازد و با HMAC-SHA256 امضا می‌کند. در Windows، کلید audit به‌صورت DPAPI-protected نگهداری می‌شود. در verification، هم sequence، هم پیوند previous hash، هم HMAC هر event و هم checkpoint نهایی بررسی می‌شوند. نتیجه این است که ویرایش، حذف یا جابه‌جایی رخداد در audit محلی قابل تشخیص است؛ با این مرز روشن که برای immutability سازمانی باید evidence به SIEM یا WORM خارجی نیز صادر شود.»

### اسلاید ۵ — SoD در service layer اجرا می‌شود

**متن روی اسلاید:**

| کنترل | enforcement |
|---|---|
| RBAC | permission اختصاصی برای match، resolve و approval |
| MFA تازه | authorization context با حداکثر سن MFA پانزده دقیقه |
| Company scope | mapping، statement و account در محدوده همان شرکت |
| استقلال actor | flagger/maker/certifier نمی‌توانند در مسیر ممنوع خودشان تصمیم نهایی بگیرند |
| Denial evidence | audit HMAC پیش از raise/rollback commit می‌شود |

**اسکریپت سخنران:**

«تفکیک وظایف در این محصول یک rule ظاهری UI نیست. در v2.7.0، resolver نمی‌تواند همان user ثبت‌کننده exception باشد؛ این موضوع روی mapping و actor واقعی session بررسی می‌شود، نه روی دکمه صفحه. اگر نقض رخ دهد، سرویس قبل از raise، رویداد `bank.reconciliation.sod_denied` را در HMAC audit ثبت و commit می‌کند تا evidence denial با rollback گم نشود. در v2.8.0، همین فلسفه توسعه می‌یابد: candidate generator، maker، independent approver و controller/certifier در policyهای پرریسک از هم جدا می‌شوند. permission، MFA، company scope و actor ID همه در service layer اجرا می‌شوند و UI صرفاً مصرف‌کننده نتیجه است.»

### اسلاید ۶ — Split Matching: رابطه، نه سند جدید

**متن روی اسلاید:**

| Statement line | Allocation decision | Ledger entryهای موجود |
|---|---|---|
| ردیف تغییرناپذیر با hash منشأ | مجموع سهم‌ها برابر مبلغ statement؛ decision immutable | entryها posted، هم‌شرکت و بدون reservation فعال دیگر |

**اسکریپت سخنران:**

«Split Matching برای settlementهای تجمیعی است؛ جایی که یک ردیف statement چند entry موجود را پوشش می‌دهد. نکته مهم این است که این قابلیت ابزار ساخت سند جدید یا تغییر مبلغ entryهای قدیمی نیست. سیستم فقط رابطه و allocation هر entry را ثبت می‌کند. پیش از پذیرش، سرویس جمع مبلغ، دقت ارزی، جهت جریان، یکتایی member، status entry و reservation فعال را بررسی می‌کند. اگر اختلاف با policy پوشش داده نشده باشد، مورد exception است؛ نه اینکه با یک split ظاهراً متوازن پنهان شود. تصمیم نهایی نیز در history immutable ثبت می‌شود تا بتوان دقیقاً گفت چه کسی، با چه policy و چه evidenceای آن را پذیرفته است.»

### اسلاید ۷ — Policy اختلاف را پنهان نمی‌کند

**متن روی اسلاید:**

| Amount | Currency | Tolerance | Idempotency/Concurrency | Risk approval |
|---|---|---|---|---|
| جمع دقیق allocation | sign و minor unit معتبر | نسخه‌دار و evidenceدار | retry امن و CAS | split/FX/high-value → approval مستقل |

**اسکریپت سخنران:**

«یک allocation خوب فقط جمع‌زدن چند مبلغ نیست. هر سهم باید مثبت، غیرصفر و در minor unit ارز باشد و هیچ entry نباید بیش از ظرفیت خود مصرف شود. currency و جهت جریان باید با statement سازگار باشند و tolerance نمی‌تواند یک عدد پنهان در کد یا UI باشد؛ باید از policy version فعال بیاید و همراه evidence تصمیم ذخیره شود. اگر دو reviewer هم‌زمان عمل کنند، optimistic locking اجازه overwrite نمی‌دهد و اگر همان request به‌علت retry شبکه تکرار شود، idempotency key تصمیم دوم نمی‌سازد. در موارد ریسک بالا مانند split، FX یا tolerance غیرصفر، policy approval مستقل می‌خواهد. بنابراین اختلافی که توجیه کنترل‌شده ندارد، exception است، نه match.»

### اسلاید ۸ — v2.8.0-a: پایه قابل‌اعتماد

**متن روی اسلاید:**

| Import | Deterministic match | Immutable history | Optimistic lock |
|---|---|---|---|
| schema، hash و provenance | reference + amount + currency دقیق | actor، evidence hash و policy version | expected version، CAS و conflict UX |

**اسکریپت سخنران:**

«موج a، ستون فقرات فنی این roadmap است. ابتدا import کنترل‌شده، matching قطعی و history تصمیم را می‌سازیم. optimistic locking در اینجا به معنی compare-and-swap روی `ReconciliationCase.version` است: reviewer یک version را مشاهده می‌کند و command خود را با همان version می‌فرستد. server همه evidence را دوباره می‌خواند، decision و allocationهای immutable را در transaction آماده می‌کند و فقط اگر update شرطی head یک row را تغییر دهد، commit می‌کند. اگر rowcount صفر باشد، یعنی شخص یا process دیگری case را تغییر داده است؛ command دوم rollback می‌شود و UI evidence جدید را بارگذاری می‌کند. این راهی است برای جلوگیری از overwrite خاموش، نه برای ایجاد قفل بلندمدت database.»

## منابع

[1]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/audit.py "AuditLogger و AuditSigningKeyStore در FinAnalyzer"

[2]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/bank_reconciliation.py "BankReconciliationService و SoD موجود v2.7.0"

[3]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/docs/V2_8_OPTIMISTIC_LOCKING_ALLOCATION_TESTS_AND_RELEASE_SCRIPT_FA.md "طراحی optimistic locking و آزمون allocation v2.8.0"

[4]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/docs/V2_8_HMAC_AUDIT_RELEASE_GATES_FA.md "HMAC audit و گیت‌های کیفیت انتشار v2.8.0"
