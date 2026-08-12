# FinAnalyzer Enterprise v2.3.0 — Enterprise Identity & Security

## خلاصه

نسخه v2.3.0 پایه RBAC و DPAPI در v2.2.0 را به هویت فدره سازمانی متصل می‌کند. Microsoft Entra/OIDC و MSAL به‌عنوان نمونه مرجع public desktop client پیاده‌سازی شده‌اند. این نسخه client secret را در برنامه نگه نمی‌دارد و principal تأییدشده را جایگزین `actor_id` و `mfa_verified` قابل‌تغییر در عملیات حساس می‌کند.

## قابلیت‌های افزوده‌شده

| حوزه | تغییر |
| --- | --- |
| OIDC/PKCE و MSAL | `core/identity.py` شامل تنظیمات Entra، MSAL public-client flow، cache DPAPI و اعتبارسنجی JWKS/JWT است. |
| هویت خارجی | `IdentityProvider`، `ExternalIdentity` و `AuthSession` به مدل داده افزوده شدند. |
| نشست و MFA | `AuthenticatedPrincipal` context مجوز را تولید می‌کند؛ حساسیت MFA از claims معتبر و age policy حاصل می‌شود. |
| سرویس Plaid | Link، exchange، sync و unlink فقط principal معتبر می‌پذیرند. |
| گزارش‌گیری | تولید، زمان‌بندی و delivery گزارش فقط principal معتبر می‌پذیرند. |
| رابط دسکتاپ | ورود/خروج SSO و انتقال principal به صفحات Bank Connections و Financial Reports افزوده شد. |
| Scheduler | runner دیگر actor ID و MFA flag نمی‌پذیرد؛ session service identity معتبر لازم است. |
| Security validation | runner محلی، تست‌های OIDC/MFA/RBAC و سناریوهای تست مجاز افزوده شد. |

## تغییرات ناسازگار

1. امضای عملیات Plaid و `AutomatedReportService` از `actor_id` و `mfa_verified` به `AuthenticatedPrincipal` تغییر کرده است.
2. `scripts/run_scheduled_reports.py` اکنون `FINANALYZER_SCHEDULER_SESSION_ID` می‌خواهد؛ متغیرهای `FINANALYZER_SCHEDULER_ACTOR_ID` و `FINANALYZER_SCHEDULER_MFA_VERIFIED` دیگر پذیرفته نمی‌شوند.
3. کاربر Entra باید پیش از ورود به local `User` از طریق `ExternalIdentity` provision شود؛ JIT provisioning بدون review انجام نمی‌شود.

## اعتبارسنجی انجام‌شده

- ۱۳ آزمون محلی برای OIDC/MFA، principal، RBAC، DPAPI، Plaid و گزارش با موفقیت اجرا شده‌اند.
- تحلیل ایستا Bandit پس از اصلاح runner هیچ یافته‌ای گزارش نکرد.
- dependency audit محیط sandbox چهار آسیب‌پذیری در بسته‌های محیط پایه گزارش کرد: `pypdf 6.14.2` (دو مورد، fix در 6.15.0)، `wheel 0.42.0` (fix در 0.46.2)، و `xhtml2pdf 0.2.14` (بدون fix ثبت‌شده). این‌ها پیش از build/release نهایی Windows باید در محیط build هدف رفع یا با risk acceptance مستند شوند.

## محدودیت‌های شناخته‌شده

این نسخه نمونه اجرایی و پایه کنترل را فراهم می‌کند. Entra tenant واقعی، Conditional Access، authentication context، provisioning مبتنی بر گروه/SCIM، service account غیرانسانی، آزمون نفوذ مستقل و تأیید Plaid Production همچنان نیازمند استقرار و assurance سازمانی هستند.
