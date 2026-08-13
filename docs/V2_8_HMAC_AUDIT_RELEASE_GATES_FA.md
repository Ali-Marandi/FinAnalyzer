# HMAC Audit، رویدادهای SoD و گیت‌های کیفیت انتشار FinAnalyzer v2.8.0

## دامنه و وضعیت

این سند دو بخش دارد. بخش نخست، پیاده‌سازی **موجود** HMAC audit و ثبت رویدادهای SoD در v2.7.0 را بر مبنای کد پروژه تشریح می‌کند. بخش دوم، گیت‌های کیفیت **پیشنهادی** برای سه موج انتشار v2.8.0-a تا v2.8.0-c را تعریف می‌کند. گیت‌های پیشنهادی، معیارهای پذیرش محصول‌اند و تا زمان پیاده‌سازی، آزمون و تصویب مالک مالی/امنیت، نباید به‌عنوان کنترل عملیاتی منتشرشده معرفی شوند.[1] [2]

> **مرز امنیتی:** زنجیره HMAC تغییر غیرمجاز در محتوا یا ترتیب رخدادهای محلی را قابل تشخیص می‌کند؛ اما وقتی مهاجم هم کنترل پروفایل Windows/DPAPI و هم پایگاه‌داده محلی را داشته باشد، جایگزین یک مخزن خارجی تغییرناپذیر نیست. برای استقرار سازمانی، anchorها یا رخدادها باید به SIEM یا evidence store مورد تأیید سازمان صادر شوند.[1]

## ۱. مکانیزم HMAC Audit در کد موجود

### ۱.۱. کلید امضا و حفاظت آن

`AuditSigningKeyStore` ابتدا متغیر محیطی `FINANALYZER_AUDIT_HMAC_KEY` را می‌پذیرد، مشروط به آن‌که حداقل ۳۲ کاراکتر داشته باشد. در Windows، اگر متغیر محیطی تنظیم نشده باشد، کلید ۳۲ بایتی تصادفی ایجاد و با `WindowsDpapiProtector` محافظت می‌شود. فایل محافظت‌شده با پسوند `.dpapi` در عملیات اتمیک نوشته می‌شود؛ اگر کلید خام legacy وجود داشته باشد، یک‌بار migrate و نسخه خام حذف می‌شود. در محیط غیرWindows، مسیر توسعه با مجوز `0600` تعریف شده است و نباید جایگزین حفاظت سازمانی Windows شود.[1]

| کنترل | پیاده‌سازی موجود | اثر امنیتی |
|---|---|---|
| تولید کلید | `os.urandom(32)` | کلید تصادفی ۲۵۶بیتی برای HMAC-SHA256 |
| حفاظت در Windows | DPAPI روی فایل `.dpapi` | وابستگی رمزگشایی به زمینه محافظت‌شده Windows |
| نوشتن کلید | temp file، `fsync` و `os.replace` | جلوگیری از فایل نیمه‌نوشته در قطع ناگهانی |
| مهاجرت legacy | تبدیل raw key به DPAPI و حذف نسخه خام | کاهش exposure کلیدهای قدیمی |
| شناسه کلید | ۱۶ کاراکتر اول SHA-256 کلید | تشخیص تغییر غیرمنتظره کلید در زنجیره |
| تغییر کلید | رد شدن write در صورت اختلاف `key_id` با state | اجبار به rotation procedure تأییدشده |

### ۱.۲. ساخت هر رویداد زنجیره‌ای

`AuditLogger.record()` بدون `action`، `category` و `outcome` رویداد نمی‌سازد. سپس timestamp را به UTC نرمال می‌کند، `AuditChainState(scope="global")` را می‌خواند یا با `GENESIS_HASH = "0" * 64` ایجاد می‌کند. sequence برابر `last_sequence + 1` است و هر event یک UUID جدید می‌گیرد.[1]

قبل از امضا، logger تمام `details` را بازگشتی redact می‌کند. کلیدهایی مانند `access_token`، `authorization`، `client_secret`، `password`، `refresh_token`، `private_key`، `cookie` و `secret` به `[REDACTED]` تبدیل می‌شوند. payload canonical شامل شناسه و sequence، action/category/outcome/severity، actor/company/session/request، source، target، details پاکسازی‌شده، timestamp UTC، `previous_hash` و `key_id` است.

```python
canonical = json.dumps(
    payload,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
    default=str,
).encode("utf-8")
event_hash = hmac.new(key, canonical, hashlib.sha256).hexdigest()
```

استفاده از `sort_keys=True` و separatorهای ثابت باعث می‌شود همان داده منطقی همیشه به همان بایت‌های قابل امضا تبدیل شود. `AuditLog` سپس `previous_hash` و `event_hash` را ذخیره می‌کند و در همان transaction، `AuditChainState.last_sequence` و `last_hash` را به‌روزرسانی می‌کند. بنابراین رویداد و checkpoint زنجیره با هم commit یا rollback می‌شوند.[1]

### ۱.۳. مسیر verification

`verify_chain()` همه رخدادهای دارای sequence را به ترتیب می‌خواند و برای هر رویداد سه کنترل انجام می‌دهد:

1. sequence باید از ۱ شروع و بدون gap افزایش یابد.
2. `previous_hash` باید دقیقاً برابر hash رویداد پیشین یا Genesis Hash باشد.
3. canonical payload دوباره ساخته و HMAC آن با `hmac.compare_digest()` با `event_hash` ذخیره‌شده مقایسه شود.

در انتها، checkpoint موجود در `AuditChainState` نیز باید با آخرین sequence و hash زنجیره برابر باشد. نتیجه، `valid`، تعداد رخدادهای بررسی‌شده، اولین sequence نامعتبر (در صورت وجود) و پیام تشخیصی را برمی‌گرداند. رخدادهای legacy فاقد sequence جدا گزارش می‌شوند و جزو زنجیره v2.4+ نیستند.[1]

| الگوی تغییر | کنترل کشف | نتیجه verification |
|---|---|---|
| ویرایش fields یک event | HMAC آن event تغییر می‌کند | `HMAC verification failed` در همان sequence |
| حذف یا جابه‌جایی event | sequence یا `previous_hash` شکسته می‌شود | `Sequence or previous hash mismatch` |
| درج event در میانه | پیوند رویدادهای بعدی و checkpoint ناسازگار می‌شود | خطای hash/sequence یا state checkpoint |
| تغییر checkpoint state | مقایسه state با آخرین event شکست می‌خورد | `Chain state checkpoint does not match` |
| تغییر key بدون rotation | تفاوت `key_id` در زمان write تشخیص داده می‌شود | `AuditIntegrityError` |

## ۲. رویدادهای امنیتی SoD در تطبیق بانکی

### ۲.۱. مرز authorization پیش از mutation

هر مسیر حساس در `BankReconciliationService` ابتدا `_context()` را می‌سازد. این helper فقط `AuthenticatedPrincipal` را می‌پذیرد و `principal.authorization_context(company_id, reason, mfa_max_age=timedelta(minutes=15))` را فراخوانی می‌کند. پس از آن `AuthorizationService.require()` permission مناسب را enforce می‌کند. mapping نیز از طریق join به `PlaidItem` و شرط `company_id` واکشی می‌شود؛ بنابراین UI نمی‌تواند با تغییر شناسه تراکنش به داده شرکت دیگر دسترسی بگیرد.[2]

همچنین `_assert_open_and_mutable()` پیش از تطبیق، تراکنش pending، وضعیت `REMOVED`، entry غیرposted و دوره قفل‌شده را رد می‌کند. در match عادی، حساب contra باید فعال و در همان company باشد، نباید حساب بانکی لینک‌شده باشد و entry باید دقیقاً یک خط غیر بانکی داشته باشد. mutation فقط روی `account_id` همان contra line انجام می‌شود.[2]

### ۲.۲. ثبت رویدادهای موفق و رویدادهای انکاری

| مسیر سرویس | action ثبت‌شده | outcome / severity | details حداقلی | اثر حسابداری |
|---|---|---|---|---|
| `mark_exception()` | `bank.reconciliation.exception_flagged` | `success` / `notice` | فقط `reason_length` | هیچ entry تغییر نمی‌کند |
| `match_transaction()` | `bank.reconciliation.matched` | `success` / `notice` | `contra_account_id` و `resolution_path` | تنها contra line تغییر می‌کند |
| `resolve_exception()` توسط reviewer مستقل | `bank.reconciliation.matched` | `success` / `notice` | account و مسیر resolve | تنها contra line تغییر می‌کند |
| `resolve_exception()` توسط همان flagger | `bank.reconciliation.sod_denied` | `denied` / `warning` | `exception_flagger_cannot_resolve` | هیچ mutation مجاز نیست |

`_audit()` برای همه این رویدادها actor، company، session، request، source=`bank_reconciliation`، target type=`plaid_transaction_mapping` و provider transaction ID را ثبت می‌کند. این فیلدها، رخداد را به principal و target دقیق متصل می‌کنند؛ payload خام provider در این مسیر ثبت نمی‌شود.[2]

در self-resolution، ترتیب عملیات بسیار مهم است. سرویس ابتدا audit denial را با `AuditLogger.record()` می‌سازد، سپس `session.commit()` را صریحاً اجرا می‌کند و بعد `BankReconciliationError` می‌اندازد. علت این ترتیب آن است که context manager تراکنش، exception را rollback می‌کند؛ بدون commit صریح، evidence انکار SoD نیز از بین می‌رفت.[2]

```python
if required_status == EXCEPTION and mapping.reconciled_by_user_id == principal.user_id:
    self._audit(..., action="bank.reconciliation.sod_denied",
                outcome="denied", severity="warning",
                details={"reason": "exception_flagger_cannot_resolve"})
    session.commit()  # حفظ evidence پیش از raise/rollback
    raise BankReconciliationError("... independent reviewer is required.")
```

> **قاعده SoD موجود:** داشتن هم‌زمان permissionهای `bank.reconcile.match` و `bank.reconcile.exception.resolve` برای حل exception شخص کافی نیست؛ هویت actor فعلی با flagger روی خود mapping مقایسه می‌شود.[2]

## ۳. گیت‌های کیفیت مشترک برای همه موج‌های v2.8.0

گیت‌ها باید risk-based باشند، نه checklist صوری. NIST SSDF نیز رویکرد outcome-based و قابل‌سفارشی‌سازی بر پایه ریسک، هزینه و امکان‌پذیری را توصیه می‌کند؛ AI RMF نیز هدف خود را وارد کردن trustworthiness در طراحی، توسعه، استفاده و ارزیابی سیستم‌های AI می‌داند.[3] [4]

| گیت مشترک | شرط عبور پیشنهادی | مالک تأیید | evidence لازم |
|---|---|---|---|
| Design & policy | scope، data classification، approval matrix، retention و threat model مصوب باشد | Product + Security + Finance | ADR، policy version و threat-model review |
| Migration safety | migration روی کپی production-like اجرا، rollback/restore تمرین و idempotency بررسی شود | Engineering + DBA/Operations | migration log، backup/restore record و test report |
| Security & supply chain | dependency/security gate، secret scan و build integrity بدون finding مسدودکننده باشد | Security | CI result، SBOM/lockfile و exceptionهای مصوب |
| Audit integrity | HMAC chain پس از سناریوهای success/denial/failure معتبر بماند؛ redaction secrets تأیید شود | Security + QA | verification result، negative tests و audit sample |
| Financial correctness | هیچ mutation ناخواسته ledger رخ ندهد؛ invariantهای amount/balance policy پاس شوند | Finance Controller + QA | fixture، reconciliation evidence و sign-off |
| Release governance | critical/high defect باز وجود نداشته باشد؛ rollback owner و incident path مشخص باشد | Release Manager | release checklist، change approval و rollback runbook |

## ۴. موج v2.8.0-a — پایه داده و تطبیق قطعی

**دامنه:** CSV import کنترل‌شده، schema validation و hash/provenance؛ matching قطعی بر اساس reference ID و مبلغ/ارز دقیق؛ decision history immutable؛ optimistic concurrency و conflict UX.

| گیت | آزمون و معیار خروج پیشنهادی | دلیل تجاری/کنترلی |
|---|---|---|
| Import correctness | CSV معتبر، header/encoding نامعتبر، ستون missing، duplicate row و file retry باید نتیجه قابل‌پیش‌بینی داشته باشند | جلوگیری از ورود ناقص یا تکراری statement |
| Provenance | برای هر import hash، actor، زمان و منبع ثبت شود؛ raw file طبق policy quarantine/retention شود | قابلیت ردیابی evidence |
| Deterministic match | reference ID، amount و currency دقیق؛ هیچ fuzzy match در این موج پذیرفته نشود | baseline قابل توضیح و کم‌ریسک |
| Idempotency | retry همان import یا همان request، decision/ledger linkage مضاعف ایجاد نکند | پایداری عملیات در failure/retry |
| Concurrency | دو reviewer روی یک candidate؛ فقط یک compare-and-swap موفق و دیگری conflict قابل‌فهم بگیرد | جلوگیری از overwrite تصمیم |
| No-ledger-mutation | candidate generation و decision history بدون approved path نباید entry، مبلغ، تاریخ یا account را تغییر دهد | حفاظت از تمامیت دفتر |
| Financial UAT | controller روی fixture کنترل‌شده، نمونه‌های match قطعی و conflict را تأیید کند | اعتبار کسب‌وکاری پیش از rollout |

**خروج از v2.8.0-a:** تمام آزمون‌های automated تعریف‌شده پاس، HMAC verification معتبر، migration/restore تمرین‌شده، UAT مالی امضاشده و هیچ finding مسدودکننده در گیت امنیت/داده باقی نمانده باشد. معیار حجمی یا درصدی باید پس از داشتن baseline واقعی داده مشتری و به‌صورت policy مصوب تعیین شود؛ نباید از آستانه دل‌بخواهی برای اعلام موفقیت استفاده شود.

## ۵. موج v2.8.0-b — پیشنهاد توضیح‌پذیر، Split Matching و approval matrix

**دامنه:** candidate explanation مبتنی بر تاریخ/مبلغ/merchant/account، split allocation، policy بر اساس مبلغ/ریسک/ارز، dual approval و versioned decision history.

| گیت | آزمون و معیار خروج پیشنهادی | دلیل تجاری/کنترلی |
|---|---|---|
| Explainability completeness | هر candidate غیرقطعی باید featureهای مؤثر، score/rule version و دلیل نمایش‌پذیر داشته باشد | جلوگیری از تصمیم black-box |
| Split invariant | مجموع allocationها برابر statement line؛ allocation مثبت و quantized؛ عدم over-allocation؛ entry در decision فعال دیگر نباشد | جلوگیری از پنهان‌شدن اختلاف در split |
| Policy engine | مبلغ بالا، split، tolerance غیرصفر، cross-currency و vendor پرریسک به policy درست و approval مستقل هدایت شوند | کنترل متناسب با ریسک |
| SoD matrix | maker نتواند تصمیم خودش را checker تأیید کند؛ certifier نتواند sole approver همان تصمیم باشد | جلوگیری از self-approval |
| Exception behavior | mismatch، evidence ناکافی یا policy violation به exception با owner/SLA برود؛ مسیر auto-resolve نداشته باشد | جلوگیری از bypass کنترل |
| Model/rule evaluation | روی dataset کنترل‌شده و جدا از مجموعه تنظیم، performance با baseline deterministic مقایسه و توسط Finance تفسیر شود | سنجش ارزش بدون ادعای مدل غیرقابل‌توضیح |
| Human-in-the-loop UAT | reviewer باید explanation، conflict و denial را بدون UI bypass اجرا/مشاهده کند | اثبات enforce شدن کنترل در service layer |

**خروج از v2.8.0-b:** تمام split و SoD invariantهای منفی/مثبت پاس، exceptionهای policy-blocking در UAT قابل مشاهده، explanations برای همه پیشنهادهای ارائه‌شده کامل، و Finance/Compliance موافقت کنند که policy matrix به‌درستی ریسک‌های هدف را پوشش می‌دهد. هیچ acceptance صرفاً بر مبنای confidence عددی مدل انجام نمی‌شود.

## ۶. موج v2.8.0-c — Certification، exception SLA و Close Readiness

**دامنه:** queue مدیریت‌شده exception، owner و escalation، statement certification، evidence export و اتصال تصمیم‌های policy-blocking به Close Readiness.

| گیت | آزمون و معیار خروج پیشنهادی | دلیل تجاری/کنترلی |
|---|---|---|
| Statement certification | معادله opening balance + movements = closing balance برای تمام fixtureها برقرار باشد | اثبات سازگاری statement قبل از close |
| Close race protection | پس از request close و پیش از approval/execution، import/decision جدید تزریق شود و gate مجدداً ارزیابی گردد | جلوگیری از race condition عملیاتی |
| Exception SLA | owner، due date، escalation و policy-blocking status ثبت و قابل پیگیری باشند | حذف open item بی‌مالک |
| Evidence export | manifest هش‌شده شامل policy version، decisionها، actorها و verification result باشد | آمادگی حسابرسی و دفاع‌پذیری |
| Resilience | failure injection در import، approval و export باعث half-decision یا close غلط نشود؛ restore تمرین شود | اطمینان از rollback و بازیابی |
| External anchoring | قبل از ادعای immutability سازمانی، export به SIEM/WORM یا مخزن evidence مورد تأیید validate شود | پوشش محدودیت audit محلی |
| Controller sign-off | controller مستقل certification و report نهایی را تأیید کند | مسئولیت‌پذیری مالی پیش از close |

**خروج از v2.8.0-c:** certification روی داده UAT تأیید، exception policy-blocking از Close Readiness عبور نکند، evidence export و restore قابل بازیابی باشد و controller مستقل sign-off کند. پس از این موج، قابلیت را می‌توان در محیط production تحت rollout کنترل‌شده فعال کرد؛ rollout باید با owner عملیاتی، monitoring و rollback plan همراه باشد.

## ۷. پیام‌های کلیدی برای اسلایدهای معرفی v2.8.0

| شماره | پیام اسلاید | پیام گفتاری کوتاه |
|---:|---|---|
| ۱ | از feed review به statement certification | v2.8.0 evidence close را در سطح statement می‌سازد |
| ۲ | AI پیشنهاد می‌دهد، انسان تصمیم می‌گیرد | score و explanation هرگز جای permission و approval را نمی‌گیرند |
| ۳ | HMAC تصمیم‌ها را قابل راستی‌آزمایی می‌کند | event، actor، target و previous hash در زنجیره واحد ثبت می‌شوند |
| ۴ | SoD در service layer enforce می‌شود | self-resolution فقط با UI پنهان نمی‌شود؛ با actor ID رد و audit می‌شود |
| ۵ | Split Matching رابطه می‌سازد، نه سند جدید | allocationها کنترل می‌شوند و دفتر بی‌دلیل mutate نمی‌شود |
| ۶ | Policy بر اساس ریسک approval را تعیین می‌کند | split، مبلغ بالا و FX به independent review می‌روند |
| ۷ | v2.8.0-a پایه‌های قابل اعتماد را می‌سازد | import، deterministic match، immutable history و optimistic lock |
| ۸ | v2.8.0-b هوش توضیح‌پذیر را اضافه می‌کند | explanation، split و SoD matrix پیش از هر اتوماسیون گسترده |
| ۹ | v2.8.0-c Close قابل دفاع را تکمیل می‌کند | certification، SLA، evidence export و re-check close |
| ۱۰ | کیفیت با evidence سنجیده می‌شود | UAT مالی، verification audit و rollback بخشی از release هستند |
| ۱۱ | تصمیم: discovery و policy workshop | ابتدا policy و داده کنترل‌شده؛ سپس rollout مرحله‌ای |

## منابع

[1]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/audit.py "پیاده‌سازی AuditLogger و AuditSigningKeyStore"

[2]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/bank_reconciliation.py "پیاده‌سازی کنترل‌شده BankReconciliationService"

[3]: https://csrc.nist.gov/projects/ssdf "NIST Secure Software Development Framework"

[4]: https://www.nist.gov/itl/ai-risk-management-framework "NIST AI Risk Management Framework"

[5]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/docs/V2_8_SPLIT_MATCHING_SOD_AND_PRESENTER_SCRIPT_FA.md "طراحی Split Matching، SoD و اسکریپت v2.8.0"
