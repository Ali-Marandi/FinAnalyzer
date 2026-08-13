# بررسی عمیق کنترل بستن دوره مالی در FinAnalyzer v2.5.0

قابلیت **Controlled Financial Period Close** در نسخه v2.5.0 یک کنترل عملیاتی برای جلوگیری از بستن دوره مالی توسط یک شخص یا یک session فاقد MFA معتبر است. این قابلیت یک workflow قابل‌ممیزی ایجاد می‌کند؛ یعنی «درخواست»، «تأیید مستقل» و «اجرای close» هر کدام دارای مرز هویتی، مجوز و شواهد audit مستقل هستند.

> هدف این کنترل، کاهش ریسک خطای عملیاتی و نقض تفکیک وظایف است. این workflow جایگزین سیاست‌های حسابداری سازمان، بررسی حسابرس، یا الزامات قانونی محلی نیست.

## معماری کنترل

| لایه | مؤلفه | مسئولیت امنیتی |
|---|---|---|
| هویت | `AuthenticatedPrincipal` | حمل user ID، session ID، زمان MFA و سطح اطمینانِ اعتبارسنجی‌شده از SSO/OIDC |
| مجوز | `AuthorizationService` | اعمال deny-by-default، scope شرکت و MFA برای permission حساس |
| workflow | `PeriodCloseService` | ساخت درخواست، enforce کردن SoD، تأیید مستقل و اجرای close |
| داده | `PeriodCloseRequest` | نگهداری چرخه وضعیت، actorهای درخواست/تأیید و timestampها |
| حسابداری | `AccountingEngine.close_fiscal_year()` | ثبت closing entry و قفل کردن سال مالی |
| ممیزی | `AuditLogger` | ثبت رخدادهای ساختاریافته در زنجیره HMAC-SHA256 |
| هم‌زمانی | SQLite partial unique index | ممانعت از بیش از یک درخواست فعال برای یک شرکت و سال مالی |

## چرخه عمر درخواست

درخواست با وضعیت `PENDING` آغاز می‌شود. پس از عبور مجوز حساس و کنترل SoD، تأییدکننده به‌صورت گذرا وضعیت `APPROVED` را دریافت می‌کند؛ سپس entry اختتامیه ثبت، سال مالی قفل و وضعیت نهایی `EXECUTED` در همان تراکنش ثبت می‌شود. اگر درخواست رد شود، وضعیت `REJECTED`، actor تأییدکننده و دلیل محدودشده به ۵۰۰ کاراکتر ثبت خواهد شد.

| وضعیت | چه کسی می‌تواند آن را ایجاد کند | شرط اصلی | وضعیت بعدی مجاز |
|---|---|---|---|
| `PENDING` | Preparer دارای permission درخواست | membership فعال، scope شرکت و MFA تازه | `EXECUTED` یا `REJECTED` توسط شخص مستقل |
| `APPROVED` | فقط درون تراکنش اجرا | شخص مستقل با permission تأیید و MFA تازه | `EXECUTED` یا rollback |
| `EXECUTED` | سرویس workflow | close حسابداری با موفقیت انجام شود | پایانی |
| `REJECTED` | Financial Controller مستقل | دلیل رد غیرخالی | پایانی |

## مسیر درخواست close

متد `request_close(company_id, fiscal_year, closing_account_id, principal)` ابتدا principal را به `AuthorizationContext` تبدیل می‌کند و به MFA حداکثر ۱۵ دقیقه نیاز دارد. سپس `ledger.period.close.request` بررسی می‌شود. فقط پس از مجوز، سرویس وجود سال مالی، بازبودن آن، مالکیت حساب retained earnings در همان شرکت و equity/active بودن حساب را کنترل می‌کند.

در انتها یک `PeriodCloseRequest` با UUID ساخته و رویداد `period_close.requested` با outcome برابر `success` ثبت می‌شود. شناسه درخواست هم در `target_id` و هم در `request_id` audit event قرار می‌گیرد؛ بنابراین یک بررسی‌کننده می‌تواند رخدادهای workflow را دقیقاً بر اساس شناسه درخواست فیلتر کند.

## مسیر تأیید و اجرای close

متد `approve_and_execute(request_id, principal)` درخواست را بازیابی می‌کند، context را با company ID خود درخواست می‌سازد و `ledger.period.close.approve` را بررسی می‌کند. این ترتیب مهم است: actor نمی‌تواند با وارد کردن company ID دلخواه، scope درخواست را تغییر دهد.

پس از authorization، سرویس فقط درخواست `PENDING` را می‌پذیرد. سپس مقایسه مستقیم `requested_by_user_id == principal.user_id` انجام می‌شود. در صورت برابری، سرویس رویداد `period_close.sod_violation` با outcome `denied` ثبت و آن رخداد را پیش از پرتاب `SegregationOfDutiesViolation` commit می‌کند. بنابراین تلاش ناموفق SoD با rollback عمومی از بین نمی‌رود.

اگر actor مستقل باشد، سرویس سال مالی و حساب close را دوباره validate می‌کند، actor و زمان approval را ثبت می‌نماید و `AccountingEngine.close_fiscal_year(..., commit=False)` را فرا می‌خواند. متد accounting در صورت وجود سود یا زیان، closing journal entry متوازن می‌سازد و سپس `FiscalYear.is_closed=True` را تعیین می‌کند. در پایان، workflow به `EXECUTED` تغییر می‌کند و `period_close.executed` در audit ثبت می‌شود.

> هیچ فراخوانی `commit()` در مسیر موفق Period Close وجود ندارد. context manager پایگاه‌داده تنها پس از پایان بدون‌خطای متد commit می‌کند. در نتیجه entry اختتامیه، قفل سال، وضعیت workflow، approval actor و audit success یا همگی ثبت می‌شوند یا همگی rollback می‌شوند.

## کنترل‌های تفکیک وظایف

| کنترل | پیاده‌سازی | اثر |
|---|---|---|
| جداسازی permission | `ledger.period.close.request` و `ledger.period.close.approve` هر دو حساس هستند | آماده‌کننده و کنترل‌کننده نقش یکسانی ندارند |
| نقش مستقل | `financial_controller` فقط permission تأیید close را دارد | role کوچک‌تر و مناسب‌تر برای بازبین مالی |
| MFA تازه | `MFA_MAX_AGE = 15 minutes` در context درخواست و تأیید | session قدیمی نمی‌تواند close حساس را اجرا کند |
| scope شرکت | membership و account/fiscal year هر دو با company ID درخواست بررسی می‌شوند | actor نمی‌تواند بین شرکت‌ها close انجام دهد |
| جلوگیری از self-approval | مقایسه actor با requester در service | حتی `company_admin` نمی‌تواند درخواست خودش را تأیید کند |
| جلوگیری از self-rejection | همان مقایسه در مسیر `reject()` | رد کردن درخواست خود نیز کنترل مستقل محسوب نمی‌شود |
| هم‌زمانی | index `uq_period_close_requests_active_v25` برای `PENDING` و `APPROVED` | درخواست‌های هم‌زمان فعال برای یک سال مالی محدود می‌شوند |

## رخدادهای ممیزی

تمام رخدادهای Period Close با category برابر `financial_close` و source برابر `period_close_service` ثبت می‌شوند. هر رخداد شامل user، company، session، شناسه درخواست، target type و target ID است. جزئیات رویدادها فقط context حداقلی مانند سال مالی، شناسه حساب و وجود دلیل رد را نگه می‌دارند؛ logger عمومی همچنان مقادیر حساس را redact می‌کند.

| action | outcome | زمان ثبت | دوام مورد انتظار |
|---|---|---|---|
| `period_close.requested` | `success` | پس از ساخت درخواست | همراه با درخواست commit می‌شود |
| `period_close.executed` | `success` | پس از close حسابداری | فقط در commit موفق کل تراکنش باقی می‌ماند |
| `period_close.rejected` | `success` | پس از رد مستقل | همراه با وضعیت `REJECTED` commit می‌شود |
| `period_close.sod_violation` | `denied` | self-approval یا self-rejection | پیش از exception صراحتاً commit می‌شود |
| `authorization.denied` | `denied` | membership، permission یا MFA نامعتبر | پیش از propagate شدن denial commit می‌شود |

HMAC-SHA256 رخداد فعلی را با هش رخداد پیشین و sequence یکتا پیوند می‌دهد. `verify_chain()` در آزمایش‌ها پس از مسیر موفق، denial SoD، denial MFA و rollback failure فراخوانی می‌شود تا اعتبار زنجیره بعد از هر حالت مهم تأیید شود.

## پوشش آزمون SoD و کنترل‌ها

فایل `tests/test_period_close_v25.py` اکنون شش سناریوی کنترل‌شده را اجرا می‌کند.

| سناریو | انتظار | نتیجه آزمون |
|---|---|---|
| تأیید توسط Financial Controller دیگر | سال مالی قفل و درخواست `EXECUTED` شود | موفق؛ actor تأییدکننده، correlation audit و chain بررسی می‌شود |
| self-approval | exception SoD و درخواست همچنان `PENDING` بماند | موفق؛ رخداد `denied` و chain بررسی می‌شود |
| self-rejection | exception SoD و درخواست همچنان `PENDING` بماند | موفق؛ target audit با شناسه درخواست بررسی می‌شود |
| MFA با عمر ۱۶ دقیقه | درخواست close پیش از ایجاد رد شود | موفق؛ `authorization.denied` و chain بررسی می‌شود |
| خطای accounting در execution | approval، قفل سال، execution audit و تغییر وضعیت rollback شوند | موفق؛ درخواست `PENDING` و سال باز باقی می‌مانند |
| درخواست فعال تکراری | درخواست دوم برای همان شرکت/سال رد شود | موفق؛ service و partial unique index مانع می‌شوند |

اجرای آخرین مجموعه اختصاصی: **۶ تست موفق**. این مجموعه در کنار آزمون کامل پروژه اجرا می‌شود.

## ملاحظات طراحی و گام‌های تقویتی پیشنهادی

در طراحی فعلی، `APPROVED` وضعیت انتقالی در تراکنش واحد است و در حالت موفق سریعاً به `EXECUTED` تبدیل می‌شود. اگر سازمان به تأیید غیرهمزمان، پنجره review یا مدارک ضمیمه نیاز دارد، باید تأیید و اجرای close به دو عملیات جداگانه با policy انقضا برای درخواست `APPROVED` تبدیل شود.

همچنین SQLite برای deployment محلی مناسب است، اما برای چند کاربر هم‌زمان در مقیاس سازمانی بهتر است database server با row-level locking و migration manager رسمی در نقشه راه قرار گیرد. هر توسعه آینده باید همچنان سه اصل را حفظ کند: **مجوز صریح در scope شرکت، MFA تازه برای عملیات حساس و audit ساختاریافته قابل‌راستی‌آزمایی.**

## منابع کد داخلی

| منبع | بخش مرتبط |
|---|---|
| `core/period_close.py` | workflow، SoD، MFA context و audit Period Close |
| `core/authorization.py` | catalog permission، role `financial_controller` و deny-by-default |
| `core/accounting_engine.py` | closing journal entry و قفل سال مالی |
| `core/models.py` | وضعیت‌ها و مدل `PeriodCloseRequest` |
| `core/database.py` | partial unique index و transaction context |
| `tests/test_period_close_v25.py` | سناریوهای SoD، rollback و MFA |
