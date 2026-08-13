# Optimistic Locking، Decisionهای تغییرناپذیر، آزمون Allocation و اسکریپت گیت‌های انتشار v2.8.0

## وضعیت این سند

این سند، طراحی فنی **پیشنهادی** برای v2.8.0-a و v2.8.0-b را تکمیل می‌کند. در نسخه جاری FinAnalyzer، کنترل‌های v2.7.0 مانند company scope، MFA تازه، RBAC deny-by-default، SoD exception و HMAC audit پیاده‌سازی شده‌اند؛ اما `ReconciliationDecision`، optimistic locking و Split Matching، هنوز برای موج‌های v2.8.0 پیشنهاد طراحی و معیار پیاده‌سازی‌اند. بنابراین هیچ بخش از این سند نباید پیش از کدنویسی، آزمون، UAT مالی و تصویب policy به‌عنوان رفتار عملیاتی منتشرشده توصیف شود.[1] [2]

> **اصل طراحی:** هیچ retry، هم‌زمانی UI یا confidence مدل نباید بتواند یک تصمیم مالی را overwrite یا یک allocation فعالِ تکراری ایجاد کند.

## ۱. مدل پیشنهادی optimistic locking در v2.8.0-a

### ۱.۱. مسئله‌ای که حل می‌شود

دو reviewer می‌توانند هم‌زمان یک candidate را باز کنند. اگر هر دو UI از snapshot یکسان استفاده کنند و backend فقط آخرین write را بپذیرد، reviewer دوم ممکن است تصمیم اول، policy version، evidence یا allocationهای آن را بی‌صدا overwrite کند. optimistic locking به‌جای قفل طولانی‌مدت database، هر request را با **نسخه‌ای که reviewer واقعاً دیده است** مقایسه می‌کند. تنها تصمیمی که با version فعلی aggregate سازگار است، مجاز به commit است.

### ۱.۲. مرز immutable و mutable

برای حفظ auditability، خود `ReconciliationDecision` نباید پس از ثبت update شود. در مقابل، یک aggregate کوچک و mutable به‌نام پیشنهادی `ReconciliationCase` یا `DecisionHead` می‌تواند فقط وضعیت جاری و version را نگه دارد. این تفکیک از تبدیل history تصمیم‌ها به یک رکورد قابل بازنویسی جلوگیری می‌کند.

| موجودیت پیشنهادی | ماهیت | فیلدهای کلیدی | قاعده |
|---|---|---|---|
| `BankStatementLine` | تغییرناپذیر پس از import | amount، currency، booking date، source hash | منبع evidence است؛ با UI ویرایش نمی‌شود |
| `ReconciliationCandidate` | تغییرناپذیر یا versioned | fingerprint، rule/model version، explanation، snapshot versions | تولید candidate هرگز ledger را mutate نمی‌کند |
| `ReconciliationCase` | mutable بسیار محدود | `id`، `company_id`، `state`، `version`، `current_decision_id` | تنها نقطه compare-and-swap برای وضعیت جاری |
| `ReconciliationDecision` | append-only | UUID، case ID، action، `decision_version`، actor، policy version، evidence hash، prior decision ID | update/delete برنامه‌ای ممنوع؛ هر تغییر، decision تازه است |
| `CandidateAllocation` | append-only و وابسته به decision | decision ID، ledger entry ID، amount، currency | سهم هر entry را مستند می‌کند |
| `ActiveAllocationReservation` | mutable عملیاتی | statement line، ledger entry، state/version | از تخصیص هم‌زمان یک entry در decision فعال دیگر جلوگیری می‌کند |

`ReconciliationDecision` باید decisionهای `submitted`، `approved`، `rejected`، `voided` یا `superseded` را به‌صورت رخداد مستقل ذخیره کند. اگر تصمیم approved به‌علت provider revision یا adjustment بعدی بی‌اعتبار شد، تاریخچه قبلی تغییر نمی‌کند؛ یک decision جدید با `supersedes_decision_id` و reason/evidence ثبت می‌شود. این همان معنای واقعی «تصمیم تغییرناپذیر» است: **اصلاح از طریق الحاق رخداد جدید، نه ویرایش تاریخچه**.

### ۱.۳. قرارداد نسخه و compare-and-swap

هر response که UI برای candidate بازمی‌کند باید دست‌کم این داده‌ها را به کلاینت بدهد:

| فیلد | کاربرد |
|---|---|
| `case_id` | aggregate هدف تصمیم |
| `case_version` | نسخه‌ای که reviewer مشاهده کرده است |
| `candidate_fingerprint` | جلوگیری از پذیرش candidate متفاوت با آنچه دیده شده |
| `statement_line_version` و `ledger_snapshot_versions` | تشخیص تغییر داده‌های زیرین پس از تولید candidate |
| `policy_version` | اطمینان از تصمیم‌گیری با policy فعلی یا اعلام نیاز به review مجدد |
| `idempotency_key` | جلوگیری از دوباره‌کاری همان request در retry شبکه |

هنگام submit/approve، server transaction را آغاز، snapshotها و policy را دوباره ارزیابی و سپس یک compare-and-swap شرطی اجرا می‌کند. الگوی اصلی به‌صورت زیر است؛ شناسه decision از نوع UUID پیش از statement تولید می‌شود تا به case head پیوند بخورد.

```python
expected = command.case_version
new_version = expected + 1
new_decision = ReconciliationDecision(
    id=uuid4(),
    case_id=command.case_id,
    decision_version=new_version,
    action="approved",
    actor_id=principal.user_id,
    policy_version=policy.version,
    evidence_hash=evidence_hash,
    supersedes_decision_id=current_decision_id,
)
session.add(new_decision)
session.flush()

result = session.execute(
    update(ReconciliationCase)
    .where(
        ReconciliationCase.id == command.case_id,
        ReconciliationCase.version == expected,
        ReconciliationCase.state.in_(["submitted", "pending_review"]),
    )
    .values(
        version=new_version,
        state="approved",
        current_decision_id=new_decision.id,
        updated_at=utc_now(),
    )
)
if result.rowcount != 1:
    raise ConcurrentDecisionConflict("Decision changed; reload the latest evidence.")
```

در همان transaction، server باید allocation reservationها را با uniqueness constraint ایجاد، `CandidateAllocation`های immutable را درج و audit event را ثبت کند. اگر `rowcount` صفر باشد، insertهای decision/allocation به‌علت rollback پایدار نمی‌مانند. پاسخ conflict باید آخرین version و علت reload را برگرداند؛ نباید submission reviewer دوم را به‌طور خاموش به تصمیم جدید تبدیل کند.

### ۱.۴. قفل allocation، جدا از history

`ReconciliationDecision` نباید تنها خط دفاعی در برابر یک ledger entry مشترک باشد؛ چون دو case متفاوت ممکن است هم‌زمان به همان entry برسند. برای هر allocation فعال، یک reservation عملیاتی با constraint یکتا توصیه می‌شود:

```text
UNIQUE(company_id, ledger_entry_id) WHERE reservation_state = 'active'
UNIQUE(company_id, statement_line_id) WHERE reservation_state = 'active'
```

اگر database مقصد partial unique index را پشتیبانی نکند، می‌توان جدول `ActiveAllocationReservation` با یک ردیف active برای هر کلید و uniqueness کامل داشت و هنگام release، وضعیت را به history event منتقل کرد. هر `INSERT` متعارض باید به conflict یا exception قابل‌فهم تبدیل شود و کل transaction را rollback کند. reservation نباید جای history تصمیم را بگیرد؛ فقط current ownership عملیاتی را enforce می‌کند.

### ۱.۵. ترتیب پیشنهادی پذیرش

1. principal، company scope، permission و MFA تازه بررسی شوند.
2. statement line، case، candidate، policy و ledger snapshotها دوباره خوانده شوند.
3. fingerprint، policy version، status، amount/currency/date و تمام invariantهای allocation اعتبارسنجی شوند.
4. بررسی SoD انجام شود؛ برای split/high-value/FX یا tolerance غیرصفر، maker و approver مستقل باشند.
5. reservationهای active به‌صورت اتمیک ایجاد شوند.
6. decision immutable و allocationها درج شوند.
7. `ReconciliationCase` با compare-and-swap update شود.
8. HMAC audit event ثبت و transaction commit شود.

ترتیب ۵ تا ۷ باید در یک transaction باشد. در پیاده‌سازی SQLAlchemy، exception حاصل از unique constraint یا `rowcount == 0` باید به خطای domain مانند `ConcurrentDecisionConflict` یا `ActiveAllocationConflict` ترجمه شود. UI در این حالت باید دکمه تأیید را غیرفعال و کاربر را به refresh evidence هدایت کند، نه اینکه retry پنهان انجام دهد.

## ۲. آزمون و اعتبارسنجی invariantهای allocation در v2.8.0-b

### ۲.۱. قواعدی که باید در service layer enforce شوند

تمام محاسبات مالی با `Decimal` و quantization بر مبنای minor unit ارز انجام می‌شوند؛ `float` برای جمع و مقایسه amount مجاز نیست. tolerance نیز باید از policy version فعال بیاید، نه از مقدار hard-coded در UI یا service.

| invariant | تعریف دقیق | نتیجه نقض |
|---|---|---|
| هم‌ارزی مبلغ | `sum(allocation.amount) == abs(statement_line.amount)`، مگر policy tolerance صریح و evidenceدار | rejection یا exception |
| مثبت و غیرصفر بودن | هر allocation باید `> 0` باشد | validation error |
| دقت ارزی | allocation در minor unit ارز quantize شود | validation error؛ گردکردن پنهان ممنوع |
| عدم over-allocation | allocation یک entry از ظرفیت/مبلغ مجاز آن تجاوز نکند | rejection |
| یکتایی member | یک ledger entry در مجموعه یک decision بیش از یک‌بار حضور نداشته باشد | validation error |
| مالکیت فعال | entry یا statement line در reservation active case دیگر نباشد | concurrency conflict |
| سازگاری ارز و جهت | currency و sign جریان سازگار باشند؛ FX فقط در workflow policy مجاز باشد | exception یا approval بالاتر |
| status قابل تطبیق | entry posted و در دوره/وضعیت مجاز باشد | rejection |
| پنجره تاریخ | booking date در policy window باشد یا override تأییدشده وجود داشته باشد | exception/approval بالاتر |
| policy و SoD | split/high-risk از independent approval عبور کند | denial و audit event |

### ۲.۲. لایه‌های آزمون

| لایه آزمون | هدف | نمونه سناریو |
|---|---|---|
| Unit | هر invariant به‌صورت ایزوله و deterministic | جمع allocation، minor unit، negative/zero و duplicate entry |
| Service integration | transaction، reservation، case version، authorization و audit با SQLite/SQLAlchemy | approve موفق، conflict، rollback و HMAC verification |
| Concurrency | رقابت واقعی دو session/command با `expected_version` یکسان | تنها یک CAS موفق؛ دیگری conflict بدون allocation اضافی |
| Property/boundary | permutation و مرزهای amount/tolerance بدون وابستگی به UI | ترتیب entryها نتیجه را عوض نکند؛ مرز tolerance دقیقاً بررسی شود |
| Negative security | bypass permission، MFA، company scope و SoD | رد شدن command و ثبت denial مناسب |
| Financial UAT | fixture کنترل‌شده با sign-off controller | split settlement، fee policy و exception aging |

### ۲.۳. مجموعه آزمون پیشنهادشده

| شناسه آزمون | setup | انتظار دقیق |
|---|---|---|
| `test_split_accepts_exact_allocations` | statement 120؛ entryهای 70 و 50 | decision approved، دو allocation immutable، جمع 120 |
| `test_split_rejects_under_allocation` | statement 120؛ allocationهای 70 و 49 | بدون decision/reservation فعال؛ اختلاف به exception یا validation error |
| `test_split_rejects_over_allocation` | statement 120؛ allocationهای 70 و 51 | rollback کامل؛ هیچ allocation ذخیره نشود |
| `test_split_rejects_zero_negative_and_duplicate_members` | allocation صفر/منفی یا همان entry دوبار | validation error، ledger دست‌نخورده |
| `test_split_uses_decimal_minor_units` | ارز با دقت مشخص و مقدار خارج از minor unit | reject؛ عدم استفاده از float و عدم گردکردن پنهان |
| `test_split_rejects_currency_or_sign_mismatch` | ارز ناهمسان یا debit/credit مخالف | exception یا policy denial؛ FX خودکار رخ ندهد |
| `test_split_rejects_active_member_reservation` | entry قبلاً در case active دیگر reserve شده است | `ActiveAllocationConflict` و rollback تصمیم جدید |
| `test_split_is_idempotent_for_retry` | همان `idempotency_key` دوبار ارسال شود | همان decision برگردد؛ allocation/audit دوم تولید نشود |
| `test_split_conflict_on_stale_case_version` | دو command با `case_version=7` | یکی version=8؛ دیگری `ConcurrentDecisionConflict` |
| `test_split_rechecks_candidate_snapshot` | پس از نمایش candidate، entry یا policy version تغییر کند | پذیرش رد؛ reviewer باید evidence را reload کند |
| `test_high_risk_split_requires_independent_approval` | split یا policy high-risk با maker=approver | SoD denial، بدون mutation، audit verification معتبر |
| `test_approval_failure_rolls_back_all_writes` | fault injection پس از reservation یا پیش از audit commit | نه decision، نه allocation و نه reservation باقی نماند |
| `test_provider_revision_supersedes_not_overwrites` | provider revision پس از approved decision | decision قبلی immutable، case به review نیاز دارد و decision جدید علت را ثبت می‌کند |
| `test_audit_chain_verifies_after_success_and_denial` | یک approve و یک denial SoD | `verify_chain().valid is True` و رخدادها actor/target صحیح دارند |

### ۲.۴. الگوی assertion برای آزمون atomicity

هر تست شکست باید بیش از یک پیام خطا را بررسی کند. پس از exception، test باید در session تازه ثابت کند که `ReconciliationDecision`، `CandidateAllocation` و `ActiveAllocationReservation` فعال جدیدی وجود ندارد و `ReconciliationCase.version` تغییر نکرده است. همچنین در failureهایی که evidence denial لازم دارند، باید صراحتاً بررسی شود که فقط audit event طراحی‌شده persist شده و زنجیره HMAC همچنان معتبر است.

```python
with pytest.raises(ConcurrentDecisionConflict):
    service.approve(command_from_second_reviewer)

with database.get_session() as session:
    case = session.get(ReconciliationCase, case_id)
    assert case.version == 8
    assert active_reservation_count(session, statement_line_id) == 1
    assert allocation_count_for_case(session, case_id) == 2
    assert audit_logger.verify_chain(session).valid is True
```

برای testهای concurrency واقعی، دو session مستقل باید snapshot version یکسان بگیرند. استفاده از یک object cached در همان session، رقابت واقعی database را شبیه‌سازی نمی‌کند. در SQLite، تنظیمات مناسب transaction و در CI یک database engine هماهنگ با production نیز باید برای اعتبارسنجی رفتار CAS و uniqueness در نظر گرفته شود.

## ۳. اسکریپت کامل سخنران: اسلایدهای موج انتشار و گیت‌های کیفیت v2.8.0

### اسلاید ۸ — v2.8.0-a: پایه قابل‌اعتماد

«در موج اول، عمداً از پیچیدگی هوش مصنوعی شروع نمی‌کنیم. ابتدا داده statement باید کنترل‌شده وارد شود: schema validation، hash و provenance به ما می‌گویند چه فایلی، چه زمانی و توسط چه کسی وارد شده است. سپس فقط matching قطعی بر پایه reference ID، مبلغ و ارز دقیق را اجرا می‌کنیم. هر تصمیم در history تغییرناپذیر ثبت می‌شود و optimistic locking مانع می‌شود دو reviewer تصمیم هم را overwrite کنند. معیار خروج این موج صرفاً نمایش یک UI جدید نیست؛ import و retry باید idempotent باشند، migration و restore باید تمرین شوند، زنجیره HMAC باید معتبر بماند و controller باید سناریوهای match قطعی و conflict را در UAT تأیید کند.»

### اسلاید ۹ — v2.8.0-b: هوش توضیح‌پذیر

«پس از تثبیت پایه داده و history، در v2.8.0-b سراغ هوش توضیح‌پذیر می‌رویم. سیستم می‌تواند با ویژگی‌هایی مثل تاریخ، مبلغ، merchant و account، candidate پیشنهاد کند؛ اما reviewer باید دلیل پیشنهاد و نسخه rule یا مدل را ببیند. Split Matching نیز برای settlementهای تجمیعی اضافه می‌شود، با این تفاوت مهم که رابطه statement با چند entry را ثبت می‌کند و سند جدید نمی‌سازد. در این موج، split، FX، tolerance غیرصفر، مبلغ بالا یا vendor پرریسک به approval مستقل می‌روند. خروج از موج دوم، با confidence مدل تعیین نمی‌شود؛ تمام invariantهای allocation، منع self-approval و کامل‌بودن explanationها باید در UAT مالی و Compliance تأیید شوند.»

### اسلاید ۱۰ — v2.8.0-c: Close قابل دفاع

«موج سوم، تصمیم‌های تطبیق را به قابلیت دفاع از close تبدیل می‌کند. Statement certification باید نشان دهد opening balance به اضافه movements با closing balance برابر است. Exception دیگر یک برچسب بدون مالک نیست؛ علت، owner، due date و escalation دارد و موارد policy-blocking تا حل یا approval معتبر، مانع Close Readiness هستند. evidence export نیز manifest هش‌شده‌ای از policy version، decisionها، actorها و verification result فراهم می‌کند. در این مرحله، re-check close ضروری است؛ چون ممکن است بین درخواست close و اجرا، sync یا تصمیم جدیدی ثبت شده باشد. گیت خروج شامل certification UAT، failure injection، restore قابل اثبات و sign-off مستقل controller است.»

### اسلاید ۱۱ — کیفیت با Evidence سنجیده می‌شود

«کیفیت release در این برنامه با یک شاخص منفرد سنجیده نمی‌شود. ابتدا design و policy باید مشخص باشند: scope، data classification، approval matrix و threat model. سپس migration و restore آزمون می‌شوند. در مسیر امنیت، dependency و secret gate و build integrity بررسی می‌شوند. در مسیر ممیزی، سناریوهای success، denial و failure باید زنجیره HMAC معتبر و redaction صحیح ایجاد کنند. و در نهایت، Finance باید invariantهای amount و balance را روی fixture کنترل‌شده تأیید کند. بنابراین تصمیم Go زمانی صادر می‌شود که evidence همه گیت‌ها کامل باشد؛ وجود خطای مسدودکننده یا نقص تمامیت audit، تصمیم را به No-Go برمی‌گرداند.»

### اسلاید ۱۲ — تصمیم پیشنهادی: کنترل، سپس مقیاس

«تصمیم پیشنهادی، شروع discovery برای v2.8.0-a و اجرای policy workshop مشترک میان Finance، Security و Product است. هدف، افزایش ظاهری نرخ match نیست؛ هدف، ساخت تصمیمی است که بتوان آن را توضیح داد، بازبینی کرد و در close از آن دفاع کرد. پس از آن، v2.8.0-b با داده demo کنترل‌شده، explanation، Split Matching و approval matrix را ارزیابی می‌کند. تنها پس از عبور از UAT مالی، گیت‌های امنیت و ممیزی، آزمون rollback و evidence قابل‌راستی‌آزمایی، v2.8.0-c به certification و rollout کنترل‌شده می‌رسد. در این مسیر، confidence مدل هرگز جای permission، MFA، policy و تأیید انسان را نمی‌گیرد.»

## منابع

[1]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/docs/V2_8_HMAC_AUDIT_RELEASE_GATES_FA.md "HMAC Audit و گیت‌های کیفیت انتشار FinAnalyzer v2.8.0"

[2]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/docs/V2_8_SPLIT_MATCHING_SOD_AND_PRESENTER_SCRIPT_FA.md "Split Matching، کنترل‌های SoD و اسکریپت v2.8.0"

[3]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/bank_reconciliation.py "کنترل‌های موجود BankReconciliationService v2.7.0"

[4]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/audit.py "پیاده‌سازی HMAC Audit در FinAnalyzer"
