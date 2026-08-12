# FinAnalyzer v2.3.0 — سناریوهای تست امنیت و پایداری

این برنامه برای آزمون **مجاز، کنترل‌شده و غیرمخرب** ماژول OIDC/PKCE، نشست MFA، RBAC، Plaid و گزارش‌گیری تهیه شده است. ابزارها و سناریوهای این سند نباید علیه tenant واقعی Entra، بانک، Plaid Production، SMTP/Telegram واقعی یا هر شبکه‌ای که مالکیت و مجوز کتبی آن را ندارید اجرا شوند.

> **قانون اجرا:** ابتدا روی محیط ایزوله با DB، کاربر، tenant آزمایشی، Plaid Sandbox و داده ساختگی اجرا کنید. برای هر آزمون دستی یا شبکه‌ای، Rules of Engagement شامل دامنه، ساعت، IPهای مجاز، حساب‌های تست، نرخ درخواست، تماس اضطراری و معیار توقف مصوب داشته باشید.

## 1. دستورات اعتبارسنجی خودکار

### نصب ابزارهای اختیاری توسعه

```powershell
py -m pip install -r requirements.txt
py -m pip install -r requirements-security.txt
```

### اجرای رگرسیون امنیت هویت و RBAC

```powershell
py scripts/run_security_validation.py --suite identity
```

این فرمان فقط unit/integration testهای محلی را اجرا می‌کند و تماس خارجی ندارد. پوشش آن شامل principal OIDC شبیه‌سازی‌شده، token منقضی، provisioning deny، MFA قدیمی، logout/revocation، deny-by-default و tenant scope است.

### اجرای کامل رگرسیون محلی

```powershell
py scripts/run_security_validation.py --suite all
```

### افزودن بررسی کد و dependency

```powershell
py scripts/run_security_validation.py --suite all --include-static --include-dependencies
```

### افزودن secret scan روی repository محلی

```powershell
py scripts/run_security_validation.py --suite all --include-static --include-dependencies --include-secrets
```

> **هشدار:** اگر secret scan یافته‌ای گزارش کند، توکن/رمز را در output یا issue عمومی بازنشر نکنید. credential را فوراً rotate کنید، اثر آن را بررسی کنید و سپس secret را از کد، تاریخچه و artifactها پاکسازی کنید.

## 2. سناریوهای آزمون OIDC/PKCE و SSO

| شناسه | سناریو کنترل‌شده | روش آزمون در محیط test | نتیجه قابل قبول |
| --- | --- | --- | --- |
| ID-01 | Token منقضی | claims شبیه‌سازی‌شده با `exp` گذشته | session ایجاد نشود و event امن ثبت شود. |
| ID-02 | Tenant/issuer نادرست | tenant یا issuer غیرمنتظره در validator test double | ورود رد شود؛ user local یا role جدید ساخته نشود. |
| ID-03 | audience نادرست | client ID غیرمجاز | token برای برنامه دیگر پذیرفته نشود. |
| ID-04 | کاربر provision نشده | subject معتبر اما فاقد `ExternalIdentity` | `IdentityProvisioningDenied`؛ هیچ نقش پیش‌فرض اعطا نشود. |
| ID-05 | logout/revocation | ورود شبیه‌سازی‌شده، سپس `sign_out` و بازیابی session | session باطل شود و principal جدید برنگردد. |
| ID-06 | PKCE/state/nonce | در محیط Entra test، callback با state/nonce یا verifier نامطابق | callback fail شود؛ session صادر نشود. |
| ID-07 | redirect URI | app registration فقط loopback ثبت‌شده را داشته باشد؛ URL غیرثبت‌شده را امتحان کنید | IdP درخواست را رد کند. |

Microsoft برای desktop/native app، Authorization Code Flow همراه با PKCE و استفاده از redirect URI مناسب را توصیف می‌کند. Public client نباید client secret را داخل برنامه ذخیره کند.[1]

## 3. سناریوهای آزمون MFA و Step-up

| شناسه | سناریو | روش آزمون مجاز | نتیجه قابل قبول |
| --- | --- | --- | --- |
| MFA-01 | bypass پس از عامل اول | principal بدون `amr`/`acr` مورد قبول و فراخوانی `bank.link` | authorization denied؛ audit ثبت شود. |
| MFA-02 | MFA قدیمی | `auth_time` قدیمی‌تر از policy و عمل حساس | `mfa_verified=False` و عمل رد شود. |
| MFA-03 | جعل flag رابط کاربری | تلاش برای فراخوانی connector/report با `actor_id` یا bool خام | helper/service principal را نپذیرد. |
| MFA-04 | recovery | reset factor یا recovery code در IdP test | re-authentication و audit لازم باشد؛ کد یک‌بارمصرف شود. |
| MFA-05 | rate limit | فقط در tenant test با حدود rate مصوب، خطای مکرر MFA | IdP/application alert و lock/rate policy قابل مشاهده باشد. |
| MFA-06 | step-up | نشست معتبر ولی بدون MFA تازه برای link/unlink/delivery | درخواست step-up یا رد امن؛ عدم اجرای عمل. |

OWASP تأکید می‌کند که MFA باید در همه مسیرهای ورود، APIها و providerهای فدره یکسان enforce شود و مسیرهای bypass، recovery و مدیریت factor نیز آزمون شوند.[2]

## 4. سناریوهای RBAC و tenant isolation

| شناسه | سناریو | روش آزمون | نتیجه قابل قبول |
| --- | --- | --- | --- |
| AUTH-01 | deny-by-default | permission ناشناخته یا role بدون grant | `AuthorizationDenied` و audit denial. |
| AUTH-02 | privilege escalation عمودی | viewer مستقیم `bank.link` یا `ledger.entry.post` را صدا بزند | سرویس، نه فقط UI، درخواست را رد کند. |
| AUTH-03 | دسترسی افقی بین شرکت‌ها | principal شرکت A با شناسه item/report شرکت B | داده افشا نشود و عمل رد گردد. |
| AUTH-04 | revoke آنی | membership/role را revoke کنید و دوباره عمل حساس را امتحان کنید | request بعدی deny شود؛ cache کهنه مجوز ایجاد نکند. |
| AUTH-05 | schedule identity | scheduler بدون session ID یا با session منقضی | runner fail-closed شود. |
| AUTH-06 | group-to-role mapping | group object ID ناشناخته یا display name مشابه | هیچ role پیش‌فرض به‌ویژه admin داده نشود. |

## 5. سناریوهای محافظت از راز و Plaid

| شناسه | سناریو | روش آزمون | نتیجه قابل قبول |
| --- | --- | --- | --- |
| SEC-01 | DPAPI user boundary | فایل `.dpapi` را فقط در Windows test profile دوم بررسی کنید | decrypt موفق نشود و برنامه raw-key fallback نکند. |
| SEC-02 | crash در migration | fault injection کنترل‌شده میان write اتمیک و حذف legacy key | کلید سالم بازیابی شود یا اجرای امن متوقف شود؛ فایل raw ناخواسته باقی نماند. |
| SEC-03 | artifact leakage | log، traceback، SQLite، PDF/XLSX، backup و cache را برای token/key جست‌وجو کنید | access token، TOTP secret، refresh token و key plaintext یافت نشود. |
| SEC-04 | Plaid scope | principal خارج از company item، sync/unlink بخواهد | عمل رد شود؛ cursor یا داده تغییر نکند. |
| SEC-05 | replay/public token | فقط Plaid Sandbox و token test یک‌بارمصرف | token تکراری پذیرفته نشود و access token log نشود. |

## 6. سناریوهای پایداری و بازیابی

| شناسه | سناریو | روش ایمن | نتیجه قابل قبول |
| --- | --- | --- | --- |
| RES-01 | outage IdP | timeout/DNS failure روی محیط test | ورود جدید fail شود؛ عملیات نیازمند step-up انجام نشود. |
| RES-02 | token expiry حین کار | token کوتاه‌عمر در tenant test | کاربر به ورود مجدد هدایت شود؛ ثبت مالی دوباره انجام نشود. |
| RES-03 | هم‌زمانی sync/report | parallel test روی داده مصنوعی | cursor نیمه‌کاره ذخیره نشود؛ دفترکل متوازن بماند. |
| RES-04 | revoke حین schedule | revoke session یا role در میانه اجرای تست | اجرای بعدی مجوز را دوباره کنترل کند؛ ارسال جدید متوقف شود. |
| RES-05 | backup/restore | restore در sandbox با key policy صحیح | بازیابی بدون افشای secret و مطابق runbook باشد. |

## 7. معیار توقف و گزارش‌دهی

آزمون باید فوراً متوقف شود اگر احتمال تماس با محیط Production، افشای داده واقعی، اختلال در حساب کاربر، افزایش غیرعادی خطا یا عبور از نرخ مصوب به وجود آمد. یافته‌ها باید با شناسه، پیش‌نیاز، مراحل بازتولید در محیط test، evidence redacted، شدت، مالک اصلاح، نسخه هدف و وضعیت retest ثبت شوند. هیچ secret، token، payload بانکی یا داده شخصی نباید در گزارش یافته‌ها قرار گیرد.

## منابع

[1]: https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow "Microsoft identity platform — OAuth 2.0 authorization code flow"
[2]: https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/04-Authentication_Testing/11-Testing_Multi-Factor_Authentication "OWASP WSTG — Testing Multi-Factor Authentication"
