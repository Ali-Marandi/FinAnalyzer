# راهنمای راه‌اندازی SSO و MFA در FinAnalyzer Enterprise v2.3.0

## هدف و محدوده

v2.3.0 مسیر ورود سازمانی Microsoft Entra را به‌عنوان نمونه مرجع پیاده‌سازی می‌کند. برنامه دسکتاپ یک **public client** است؛ بنابراین نباید `client_secret`، certificate خصوصی یا credential Active Directory در EXE، `.env` یا SQLite ذخیره شود. ورود تعاملی با MSAL و مرورگر سیستمی انجام می‌شود؛ MSAL جریان Authorization Code همراه PKCE را برای public client مدیریت می‌کند.[1]

> **محدوده فعلی:** کد v2.3.0 اعتبار token، نگاشت identity خارجی به کاربر محلی، ایجاد نشست، freshness MFA و اعمال principal در Plaid/گزارش را فراهم می‌کند. provisioning مبتنی بر گروه Entra، SCIM، service account غیرانسانی و استقرار Plaid Production نیازمند تکمیل عملیاتی و بازبینی مستقل هستند.

## 1. ثبت برنامه در Microsoft Entra

در Microsoft Entra admin center یک App Registration برای **Desktop / Mobile public client** بسازید. tenant را single-tenant نگه دارید مگر اینکه مدل کسب‌وکار چندtenant به‌طور جداگانه طراحی و review شده باشد. در بخش Authentication، redirect URI برابر `http://localhost` یا loopback URI ثبت‌شده را برای mobile and desktop applications ثبت کنید. برای native desktop app، هیچ client secret ایجاد یا استفاده نکنید.

| مقدار | محل تنظیم | مقدار نمونه |
| --- | --- | --- |
| Tenant ID | Overview | `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee` |
| Application (client) ID | Overview | `11111111-2222-3333-4444-555555555555` |
| Redirect URI | Authentication | `http://localhost` |
| Supported account type | Authentication | Single tenant | 
| API permissions | API permissions | فقط `openid`, `profile`, `email` در مرحله نخست |

در Conditional Access، روش MFA مورد تأیید مشتری را برای گروه کاربران FinAnalyzer اعمال کنید. برای عملیات حساس، authentication strength مقاوم‌تر در برابر فیشینگ مانند FIDO2، passkey یا Windows Hello for Business را ترجیح دهید. NIST برای AAL2، وجود دو عامل و ارائه دست‌کم یک گزینه مقاوم در برابر فیشینگ را مطرح می‌کند.[2]

## 2. پیکربندی FinAnalyzer

در محیط Windows کاربر یا فایل `.env` محافظت‌شده، فقط تنظیمات غیرمحرمانه زیر را قرار دهید:

```text
FINANALYZER_ENTRA_TENANT_ID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
FINANALYZER_ENTRA_CLIENT_ID=11111111-2222-3333-4444-555555555555
FINANALYZER_ENTRA_REDIRECT_URI=http://localhost
FINANALYZER_ENTRA_PROVIDER_CODE=entra
FINANALYZER_SESSION_MINUTES=60
FINANALYZER_MFA_MAX_AGE_MINUTES=15
```

در صورتی که سازمان یک authentication context class برای step-up تعریف کرده است، `FINANALYZER_ENTRA_REQUIRED_ACR` را با مقدار تصویب‌شده همان policy تنظیم کنید. این مقدار نباید صرفاً برای نمایش UI استفاده شود؛ باید با policy IdP و test tenant اعتبارسنجی شود.

> **ممنوع:** `FINANALYZER_ENTRA_CLIENT_SECRET` نباید در تنظیمات FinAnalyzer تعریف شود. secret برای web/confidential client است و محل امنی در native desktop app ندارد.[1]

## 3. Provisioning اولیه کاربر

FinAnalyzer به‌صورت پیش‌فرض JIT provisioning بی‌قیدوشرط انجام نمی‌دهد. ابتدا یک کاربر محلی فعال ایجاد کنید، سپس subject immutable Entra را به همان user bind کنید. email تنها برای نمایش است و نباید کلید اعتماد باشد. binding باید توسط workflow مدیر دارای `identity.role.assign`، با MFA تازه و audit trail انجام شود.

نمونه اجرایی در یک ابزار مدیریتی مورد تأیید:

```python
from core.database import DatabaseManager
from core.identity import IdentityService

identity = IdentityService(DatabaseManager("finanalyzer.db"))
identity.bind_external_identity(
    user_id=42,
    subject="subject-from-validated-entra-claim",
    object_id="oid-from-validated-entra-claim",
    preferred_username="finance.manager@example.com",
)
```

این helper به‌تنهایی UI مدیریت کاربر نیست. در استقرار واقعی، آن را پشت `AuthorizationService.require(..., "identity.role.assign")`، MFA step-up، کنترل تفکیک وظیفه و بازبینی مدیر دوم قرار دهید.

## 4. رفتار نشست و MFA

پس از ورود، `IdentityService` از claims اعتبارسنجی‌شده یک `AuthenticatedPrincipal` می‌سازد. principal شامل user محلی، session ID، issuer/subject، زمان احراز هویت، زمان MFA، سطح assurance و expiry است. `AuthorizationContext` از principal تولید می‌شود؛ صفحه یا script امکان ارسال آزاد `mfa_verified=True` ندارد.

| عملیات | رفتار v2.3.0 |
| --- | --- |
| تولید گزارش داخلی | principal معتبر + permission `report.generate` |
| sync بانکی | principal معتبر + permission `bank.sync` |
| Link/Unlink Plaid | principal معتبر + permission حساس + MFA تازه |
| زمان‌بندی/ارسال خارجی گزارش | principal معتبر + permission حساس + MFA تازه |
| خروج | نشست محلی revoke و cache MSAL محافظت‌شده پاک می‌شود |

MSAL cache در Windows فقط با DPAPI ذخیره می‌شود. روی غیر-Windows، cache memory-only است تا refresh token در فایل بدون حفاظت پایدار نشود.

## 5. زمان‌بندی گزارش

runner `scripts/run_scheduled_reports.py` دیگر `ACTOR_ID` یا flag MFA را نمی‌پذیرد. برای اجرای خودکار باید `FINANALYZER_SCHEDULER_SESSION_ID` به یک نشست service identity معتبر اشاره کند. این طراحی عمداً fail-closed است. در production، به جای reuse نشست انسانی باید مدل service account، lifecycle، rotation و policy اختصاصی پیاده‌سازی شود.

## 6. پذیرش پیش از Pilot

قبل از pilot با مشتری، باید login interactive در tenant test، token نامعتبر/منقضی، subject provision نشده، MFA کهنه، logout/revocation، tenant isolation، DPAPI cache و عملیات Plaid Sandbox آزمون شوند. اسکن dependency محلی نیز باید بررسی شود. در محیط sandbox این اسکن چهار آسیب‌پذیری در بسته‌های محیط پایه گزارش کرده است: دو مورد در `pypdf 6.14.2` با fix در `6.15.0`، یک مورد در `wheel 0.42.0` با fix در `0.46.2` و یک مورد در `xhtml2pdf 0.2.14` بدون fix ثبت‌شده. این یافته‌ها باید در محیط build نهایی بررسی و با upgrade، حذف dependency یا risk acceptance رسمی مدیریت شوند.

## منابع

[1]: https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow "Microsoft identity platform — OAuth 2.0 authorization code flow"
[2]: https://pages.nist.gov/800-63-4/sp800-63b.html "NIST SP 800-63B — Authentication and Authenticator Management"
