# FinAnalyzer Enterprise v2.2.0 — امنیت، RBAC و Windows DPAPI

این سند نحوه استفاده و استقرار ارتقای امنیتی v2.2.0 را تشریح می‌کند. هدف این نسخه آن است که مجوزها در **لایه سرویس** اعمال شوند، نه صرفاً با پنهان‌کردن دکمه‌ها در رابط کاربری؛ و کلید رمزنگاری محلی در ویندوز با **Windows DPAPI** حفاظت شود.

> **محدوده نسخه:** این نسخه کنترل‌های مرکزی RBAC، مدل عضویت کاربر در شرکت، نقش و مجوز، حفاظت DPAPI از کلید Fernet و اعمال مجوز برای سرویس‌های Plaid و گزارش‌گیری را فراهم می‌کند. SSO، MFA واقعی، مدیریت service account و migrationهای تولیدی دیتابیس، مراحل بعدی استقرار Enterprise هستند.

## 1. اصول طراحی

| اصل | اجرای v2.2.0 |
| --- | --- |
| رد پیش‌فرض | هر عملیاتی که مجوز صریح و محدوده شرکت معتبر نداشته باشد با `AuthorizationDenied` متوقف می‌شود. |
| مجوز سرویس‌محور | `PlaidConnector`، `AutomatedReportService` و صفحات بانک/گزارش پیش از عملیات حساس، `AuthorizationService.require()` را فراخوانی می‌کنند. |
| جداسازی tenant | membership کاربر به یک `company_id` متصل است؛ مجوز یک شرکت در شرکت دیگر معتبر نیست. |
| MFA برای عملیات حساس | `bank.link`، `bank.unlink`، مدیریت زمان‌بندی و ارسال بیرونی گزارش نیازمند context با `mfa_verified=True` هستند. |
| حسابرسی | مجوزهای حساس و همه ردشدن‌ها در `AuditLog` ثبت می‌شوند. |
| راز صفر در کد | `PLAID_SECRET` و سایر اسرار از environment خوانده می‌شوند؛ access token Plaid فقط به صورت رمز‌شده در SQLite نگهداری می‌شود. |

OWASP توصیه می‌کند مجوزدهی از احراز هویت جدا باشد، دسترسی به‌صورت پیش‌فرض رد شود و بررسی مجوز برای هر عملیات محافظت‌شده انجام گیرد.[1]

## 2. مدل RBAC و محدوده شرکت

مدل‌های زیر در `core/models.py` افزوده شده‌اند.

| مدل | وظیفه |
| --- | --- |
| `CompanyMembership` | تعیین می‌کند کاربر در کدام شرکت عضو است و وضعیت عضویت `active`، `suspended` یا `revoked` است. |
| `Role` | نقش قابل‌استفاده مجدد مانند `finance_manager` یا `auditor`. |
| `Permission` | مجوز پایدار از نوع `resource.action` مانند `bank.sync`. |
| `MembershipRole` | نقش را به عضویت همان شرکت متصل می‌کند. |
| `RolePermission` | مجوزهای هر نقش را نگاشت می‌کند. |

کاتالوگ نقش‌های سیستمی در `core/authorization.py` به‌صورت idempotent هنگام `DatabaseManager.init_database()` ایجاد می‌شود. این راه‌اندازی **هیچ دسترسی‌ای به کاربر نمی‌دهد**؛ مدیر استقرار باید برای کاربرهای واقعی عضویت و نقش اعطا کند.

```python
from core.authorization import AuthorizationService

with database.get_session() as session:
    authorization = AuthorizationService()
    authorization.grant_role(
        session,
        user_id=42,
        company_id=7,
        role_code="finance_manager",
    )
```

### فراخوانی استاندارد برای سرویس‌ها

هر سرویس باید context معتبر نشست را دریافت کند و پیش از خواندن یا تغییر داده‌های شرکت، مجوز مشخص را بررسی کند.

```python
from core.authorization import AuthorizationContext, AuthorizationService

context = AuthorizationContext(
    actor_id=current_session.user_id,
    company_id=company_id,
    mfa_verified=current_session.mfa_verified,
    reason="bank_sync",
    request_id=current_session.request_id,
)

with database.get_session() as session:
    AuthorizationService().require(session, context, "bank.sync")
```

رابط کاربری فقط می‌تواند دکمه را غیرفعال کند؛ مرز امنیتی اصلی همان فراخوانی `require()` در سرویس است. این موضوع مانع bypass از طریق فراخوانی مستقیم connector، script یا API آینده می‌شود.

## 3. مجوزهای حساس و نمونه نقش‌ها

| مجوز | عملیات | MFA | نمونه نقش |
| --- | --- | ---: | --- |
| `bank.link` | آغاز و تکمیل اتصال Plaid | بله | `finance_manager`، `company_admin`، `bank_operator` |
| `bank.sync` | همگام‌سازی تراکنش | خیر | `accountant`، `bank_operator` |
| `bank.unlink` | لغو دسترسی بانکی | بله | `finance_manager`، `company_admin` |
| `report.generate` | تولید یا مشاهده گزارش | خیر | `viewer`، `analyst`، `accountant` |
| `report.schedule.manage` | ایجاد یا تغییر زمان‌بندی | بله | `finance_manager`، `company_admin` |
| `report.deliver.external` | ارسال ایمیل/تلگرام | بله | `finance_manager`، `company_admin` |
| `ledger.entry.post` | ثبت نهایی دفتر کل | بله | `accountant`، `finance_manager` |

## 4. Windows DPAPI برای کلید رمزنگاری

### 4.1 چرا DPAPI

نسخه‌های قبل در نبود `FINANALYZER_MASTER_KEY`، کلید Fernet را به‌صورت فایل خام محلی نگه می‌داشتند. در v2.2.0، `LocalSecretStore` در Windows فایل کلید raw ایجاد نمی‌کند. کلید Fernet با `CryptProtectData` از Windows DPAPI تحت پروفایل کاربر ویندوز محافظت و در مسیر زیر نگهداری می‌شود:

```text
data/.finanalyzer.key.dpapi
```

بدون همان پروفایل Windows یا مسیر بازیابی تأییدشده، بازیابی کلید باید شکست بخورد. این رفتار **fail closed** است: اگر DPAPI در Windows در دسترس نباشد یا decrypt شکست بخورد، برنامه به فایل raw برنمی‌گردد.[2]

### 4.2 ترتیب منبع کلید

| اولویت | منبع | کاربرد |
| ---: | --- | --- |
| 1 | `FINANALYZER_MASTER_KEY` | استقرار کنترل‌شده با KMS/HSM یا secret manager سازمانی؛ مقدار باید Fernet key معتبر باشد. |
| 2 | Windows DPAPI | پیش‌فرض ویندوز برای استقرار desktop local-first. |
| 3 | فایل با سطح دسترسی `0600` | فقط fallback توسعه روی سیستم‌های غیر Windows؛ برای production حساس توصیه نمی‌شود. |

### 4.3 مهاجرت از نسخه‌های قبلی

در اولین اجرا در Windows، اگر `data/.finanalyzer.key` قدیمی موجود باشد، برنامه مراحل زیر را اجرا می‌کند:

1. کلید Fernet قدیمی را می‌خواند.
2. آن را با DPAPI محافظت می‌کند.
3. فایل `data/.finanalyzer.key.dpapi` را با نوشتن اتمیک ایجاد می‌کند.
4. فایل key خام را حذف می‌کند.

قبل از ارتقا، از دیتابیس و فایل کلید موجود backup امن بگیرید. بعد از اجرای موفق برنامه v2.2.0 با همان کاربر Windows، وجود فایل `.dpapi` و حذف فایل raw را تأیید کنید. **فایل `.dpapi` را میان کاربران Windows یا رایانه‌ها کپی نکنید**؛ DPAPI در حالت فعلی به پروفایل همان کاربر متکی است.

### 4.4 وابستگی و ساخت EXE

روی Windows وابستگی `pywin32` را نصب کنید:

```powershell
py -m pip install -r requirements.txt
```

`build_exe.py` اکنون `win32crypt` را به‌صورت hidden import به PyInstaller اضافه می‌کند تا مسیر DPAPI در فایل EXE موجود باشد. سپس فایل اجرایی را با دستور زیر بسازید:

```powershell
py build_exe.py
```

## 5. پیکربندی زمان‌بندی گزارش

اجرای زمان‌بندی‌شده دیگر بدون هویت انجام نمی‌شود. برای Task Scheduler باید متغیرهای زیر در حساب اجرای task تعریف شوند:

```text
FINANALYZER_SCHEDULER_ACTOR_ID=<authorized-user-id>
FINANALYZER_SCHEDULER_MFA_VERIFIED=true
```

این کاربر باید برای هر شرکت هدف، نقش مجاز و دست‌کم `report.generate` داشته باشد. اگر زمان‌بندی گزارش ارسال بیرونی دارد، مجوز `report.deliver.external` نیز لازم است. در استقرار Enterprise کامل، این حساب باید به service account اختصاصی با credential rotation و scope حداقلی تبدیل شود؛ از حساب انسانی مدیر برای task استفاده نکنید.

## 6. آزمون و پذیرش

آزمون‌های زیر در `tests/test_enterprise_security.py` و `tests/test_plaid_v2.py` اضافه یا به‌روزرسانی شده‌اند:

| آزمون | تضمین |
| --- | --- |
| deny-by-default | viewer بدون مجوز صریح برای sync بانکی رد و رویداد audit ثبت می‌شود. |
| Scope شرکت | مدیر شرکت A قادر به اتصال بانک در شرکت B نیست. |
| MFA | اتصال Plaid بدون context MFA رد می‌شود. |
| DPAPI | key raw روی Windows شبیه‌سازی‌شده ذخیره نمی‌شود و ciphertext قابل بازیابی است. |
| Plaid | access token رمز‌شده و تراکنش sync شده با ثبت دوطرفه متوازن است. |
| گزارش | خروجی PDF/Excel و job زمان‌بندی‌شده فقط با actor مجاز اجرا می‌شوند. |

فرمان اعتبارسنجی محلی:

```bash
python -m unittest tests/test_enterprise_security.py tests/test_plaid_v2.py tests/test_reporting_v2.py -v
```

## 7. محدودیت‌های شناخته‌شده و گام بعدی

این نسخه یک **هسته کنترل دسترسی** فراهم می‌کند، اما راهکار IAM کامل نیست. قبل از استقرار حساس، موارد زیر را اجرا کنید: احراز هویت واقعی و MFA با OIDC/SAML، provisioning/deprovisioning، جدول service account، migration کنترل‌شده برای دیتابیس‌های موجود، کلیدهای DPAPI با machine scope یا KMS در سناریوهای shared workstation، قفل دوره مالی و maker-checker، tamper-evident audit trail و آزمون نفوذ مستقل.

## منابع

[1]: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html "OWASP Authorization Cheat Sheet"
[2]: https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata "Microsoft Learn — CryptProtectData"
