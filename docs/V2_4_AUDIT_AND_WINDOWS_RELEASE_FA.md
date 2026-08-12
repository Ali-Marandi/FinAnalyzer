# راهنمای عملیاتی FinAnalyzer v2.4.0: Audit Logging و انتشار امن Windows

این سند مرجع عملیاتی تیم توسعه، امنیت و release management برای نسخه **2.4.0** است. دو هدف اصلی نسخه عبارت‌اند از: حفظ شواهد قابل‌راستی‌آزمایی از رویدادهای حساس، و جلوگیری از انتشار Windows EXE با وابستگی‌های مسدود یا پایین‌تر از baseline امن.

> پیش‌نیاز انتشار: build باید روی ویندوز، در virtual environment تازه و با Python 3.12 انجام شود. از محیط توسعه روزمره یا محیطی که پیش‌تر پکیج‌های ناشناخته داشته است برای release استفاده نکنید.

## ۱. معماری لاگ ممیزی ساختاریافته

هر فراخوانی `AuditLogger.record()` یک ردیف `AuditLog` ایجاد می‌کند. محتویات canonical رخداد با HMAC-SHA256 امضا می‌شوند؛ hash رخداد جدید شامل `previous_hash` رخداد قبلی نیز هست. بنابراین دست‌کاری content، توالی یا اتصال رخدادها در بررسی زنجیره قابل‌شناسایی است.

| جزء | مسئولیت | نکته امنیتی |
|---|---|---|
| `AuditSigningKeyStore` | ایجاد و بازیابی کلید امضا | در ویندوز با DPAPI از کلید محافظت می‌شود |
| `AuditLogger` | scrub، canonicalization، امضا و ثبت رخداد | داده حساس را پیش از ذخیره حذف می‌کند |
| `AuditLog` | نگهداری metadata و hash هر event | رخدادهای legacy همچنان قابل‌خواندن‌اند |
| `AuditChainState` | checkpoint توالی و hash آخر | از chain واحد و ترتیبی پشتیبانی می‌کند |
| `verify_chain()` | راستی‌آزمایی hash و پیوستگی | باید پیش از export حقوقی یا SIEM اجرا شود |

### فیلدهای الزامی رخداد جدید

| فیلد | نمونه | کارکرد |
|---|---|---|
| `event_id` و `sequence` | UUID و `42` | هویت و ترتیب یکتای رخداد |
| `company_id` و `session_id` | `7` و UUID نشست | محدوده tenant و session |
| `category` و `severity` | `authorization` / `warning` | طبقه‌بندی برای SOC و alerting |
| `outcome` | `success`، `denied`، `failure` | نتیجه قابل جست‌وجوی عملیات |
| `source` و هدف | `plaid_connector` / `plaid_item` | منشأ و دارایی تحت اثر |
| `previous_hash` و `event_hash` | SHA-256 hex | اثبات پیوستگی و تمامیت |
| `key_id` | شناسه key store | قابلیت rotation و بررسی کلید |

## ۲. الگوهای استفاده امن از AuditLogger

در سرویس‌های جدید، به جای `session.add(AuditLog(...))` از logger استفاده کنید. جزئیات باید ساختاریافته، حداقلی و بدون داده محرمانه باشند.

```python
self.audit_logger.record(
    session,
    action="domain.operation_completed",
    category="domain",
    outcome="success",
    severity="info",
    actor_id=principal.user_id,
    company_id=company_id,
    session_id=principal.session_id,
    source="service_name",
    target_type="resource_type",
    target_id=resource_id,
    details={"count": 3},
)
```

از قراردادن رمز، token، cookie، کلید خصوصی، پاسخ خام provider یا مشخصات حساب بانکی در `details` خودداری کنید. دفاع لایه دوم scrub خودکار است، اما مالک سرویس همچنان مسئول حداقل‌سازی داده ثبت‌شده است.

### راستی‌آزمایی دوره‌ای

در job عملیاتی یا پیش از export audit:

```python
with database.get_session() as session:
    result = audit_logger.verify_chain(session)
    if not result.valid:
        raise RuntimeError(
            f"Audit chain mismatch at sequence {result.first_invalid_sequence}"
        )
```

| نتیجه | اقدام لازم |
|---|---|
| `valid=True` | نتیجه verification را همراه export ثبت کنید. |
| `valid=False` | دسترسی نوشتن به پایگاه را محدود، snapshot تهیه و رخداد را به تیم امنیت ارجاع دهید. |
| legacy event مشاهده شد | آن رخدادها قبل از v2.4 بدون hash هستند؛ از اولین رخداد ساختاریافته به بعد chain enforce می‌شود. |
| key در دسترس نیست | backup/بازیابی DPAPI یا key-material سازمان را بررسی کنید؛ زنجیره را با کلید جدید معتبر فرض نکنید. |

## ۳. رفع وابستگی‌ها برای Windows EXE

نسخه 2.4.0 baseline زیر را enforce می‌کند.

| مورد | سیاست | اقدام release manager |
|---|---|---|
| `pypdf` | حداقل `6.15.0` | نصب با constraints و بررسی gate |
| `wheel` | حداقل `0.46.2` | نصب با manifest build |
| `xhtml2pdf` | ممنوع در محیط release | نصب نشود؛ در صورت وجود uninstall شود |
| `qifparse` | اختیاری | تنها در صورت نیاز به import QIF نصب شود |
| `pip-audit` | الزامی برای validation | output JSON را نگهداری کنید |

### مراحل استاندارد ساخت

PowerShell را در ریشه repository اجرا کنید:

```powershell
py -3.12 -m venv .venv-build
.\.venv-build\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r requirements-windows-build.txt
py scripts\verify_windows_release.py
py build_exe.py
```

> `build_exe.py` در ویندوز پیش از اجرای PyInstaller، `verify_windows_release.py` را فراخوانی می‌کند. اجرای مجزا و ثبت خروجی آن نیز برای شواهد کنترل انتشار توصیه می‌شود.

### اگر gate شکست خورد

۱. **نسخه پایین `pypdf` یا `wheel`:** محیط build را حذف کنید، virtual environment تازه بسازید و تنها از `requirements-windows-build.txt` استفاده کنید. نصب upgrade روی محیط آلوده یا global قابل اتکا نیست.

۲. **وجود `xhtml2pdf`:** این وابستگی runtime FinAnalyzer نیست و به دلیل نبود نسخه رفع‌شده برای یافته مورد اشاره، باید از محیط build حذف شود:

```powershell
py -m pip uninstall -y xhtml2pdf
```

۳. **یافته جدید `pip-audit`:** انتشار را متوقف کنید. ابتدا مشخص کنید بسته مورد نظر direct یا transitive است، نسخه رفع‌شده را در constraints pin کنید، دوباره محیط تازه بسازید و gate را تکرار کنید. تا موفقیت gate هیچ release asset نباید منتشر شود.

۴. **خروجی JSON غیرقابل‌خواندن:** نسخه `pip-audit` را از manifest نصب کنید و فایل `security-reports/pip-audit.json` را همراه log build نگه دارید. gate به‌صورت fail-closed رفتار می‌کند.

## ۴. شواهد موردنیاز برای تصویب انتشار

| مدرک | محل تولید | کنترل‌کننده |
|---|---|---|
| snapshot وابستگی‌ها | `security-reports/windows-build-dependencies.json` | Release manager |
| نتیجه audit بسته‌ها | `security-reports/pip-audit.json` | Security engineering |
| خروجی تست‌ها | log CI یا build log | QA |
| نتیجه audit-chain verification | job report یا evidence export | Security / Compliance |
| hash فایل EXE و امضای کد | pipeline انتشار ویندوز | Release manager |

## ۵. دامنه و محدودیت‌ها

HMAC chain تغییر offline رکوردهای ثبت‌شده را آشکار می‌کند، اما جایگزین کنترل دسترسی به فایل، رمزنگاری دیسک، backup، code signing، EDR یا SIEM نیست. حفاظت درست از کلید DPAPI و محدودسازی دسترسی به SQLite برای حفظ ارزش اثباتی این زنجیره ضروری است.

برای عملیات Plaid و delivery گزارش، audit فقط metadata حداقلی مانند شناسه هدف، نتیجه و تعداد تغییرات را ثبت می‌کند؛ tokenهای دسترسی، فایل‌های گزارش و داده‌های تراکنش نباید به لاگ ممیزی افزوده شوند.
