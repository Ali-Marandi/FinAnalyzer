# FinAnalyzer Enterprise v2.3.0 — MFA، Active Directory/SSO و آزمون امنیت

**وضعیت سند:** نقشه راه فنی و برنامه آزمون؛ نه گواهی انطباق یا گزارش تست نفوذ مستقل.  
**مبنای فنی:** FinAnalyzer v2.2.0 دارای RBAC محدوده‌دار، `AuthorizationService` با رد پیش‌فرض، DPAPI محلی و کنترل سرویس‌های Plaid/گزارش است. v2.3.0 باید هویت قابل‌اتکا و وضعیت MFA واقعی را به همان کنترل‌ها متصل کند.

> **تصمیم معماری پیشنهادی:** برای مشتریان سازمانی Windows، Microsoft Entra ID به‌عنوان مسیر اصلی SSO و OIDC Authorization Code + PKCE در مرورگر سیستمی انتخاب شود. Active Directory محلی از مسیر federation یا hybrid identity به Entra متصل شود؛ Active Directory خام، منبع مستقیم مجوزدهی داخل کلاینت نباشد. AD FS تنها برای مشتریانی نگه داشته شود که الزام عملیاتی موجه دارند.

## 1. هدف و مرز v2.3.0

v2.2.0 متغیر `mfa_verified` را به‌عنوان context کنترل عملیات حساس می‌پذیرد. در v2.3.0 این متغیر نباید از UI یا فراخوانی سرویس به‌صورت آزاد ارسال شود. باید از یک **نشست امضاشده و اعتبارسنجی‌شده** به‌دست آید؛ نشستی که هویت، tenant، زمان احراز هویت، سطح/روش احراز هویت، تاریخ انقضا و شناسه درخواست را حمل می‌کند.

| هدف v2.3.0 | نتیجه قابل‌سنجش |
| --- | --- |
| ورود سازمانی | کاربر با IdP سازمان وارد می‌شود و داده شناسایی‌شده وی به `User` محلی نگاشت می‌شود. |
| MFA واقعی | وضعیت MFA از ادعاها و policy IdP استخراج می‌شود، نه از input قابل‌تغییر کلاینت. |
| Step-up | عملیات `bank.link`، `bank.unlink`، `ledger.entry.post`، تغییر نقش و ارسال بیرونی گزارش به احراز هویت تازه/قوی‌تر وابسته می‌شوند. |
| SSO قابل‌مدیریت | Entra/AD، گروه‌ها و lifecycle کاربر فقط پس از validation token و با mapping کنترل‌شده روی membership و role محلی اثر می‌گذارند. |
| عدم افت RBAC | `AuthorizationService` همچنان مرز نهایی کنترل است؛ IdP هویت و attribute می‌دهد، اما permission را در سرویس محلی جایگزین نمی‌کند. |

Microsoft برای برنامه‌های دسکتاپ استفاده از Authorization Code Flow همراه با PKCE و OIDC را توصیه می‌کند و استفاده از کتابخانه پشتیبانی‌شده را به پیاده‌سازی دستی درخواست‌های خام ترجیح می‌دهد.[1] NIST برای AAL2 وجود دو عامل و ارائه دست‌کم یک گزینه مقاوم در برابر فیشینگ را مطرح می‌کند.[2]

## 2. معماری مرجع هویت و SSO

```text
کاربر Windows
    │ مرورگر سیستمی + MFA
    ▼
Microsoft Entra ID / AD FS (Identity Provider)
    │ Authorization Code + PKCE + OIDC
    ▼
IdentityClient در FinAnalyzer
    │ validate issuer / audience / signature / nonce / state / expiry
    ▼
AuthSessionManager
    │ principal غیرقابل‌تغییر + auth context
    ▼
AuthorizationService
    │ active membership + company scope + explicit permission
    ▼
Plaid / Ledger / Reports / Scheduler
```

### 2.1 اجزای پیشنهادی کد

| ماژول پیشنهادی | مسئولیت | قاعده امنیتی |
| --- | --- | --- |
| `core/identity/models.py` | مدل provider، external identity، session و authentication context | subject خارجی با `issuer + subject` یکتا شود؛ ایمیل به‌تنهایی شناسه اعتماد نباشد. |
| `core/identity/oidc_client.py` | فراخوانی MSAL/OIDC، دریافت token و refresh کنترل‌شده | برنامه دسکتاپ public client است؛ هیچ `client_secret` در EXE یا فایل محلی قرار نگیرد.[1] |
| `core/identity/token_validator.py` | اعتبارسنجی امضای JWKS، `iss`، `aud`، `exp`، `nbf`، `nonce` و `state` | توکن decodeشده بدون signature هرگز principal تولید نکند. |
| `core/identity/session_manager.py` | صدور/بستن نشست محلی، timeout، step-up و logout | context فقط‌خواندنی و کوتاه‌عمر باشد؛ خروج/لغو نقش، نشست را باطل کند. |
| `core/identity/provisioning.py` | JIT provisioning یا SCIM/Graph sync | گروه خارجی به role داخلی با شناسه object ID map شود؛ نام نمایشی گروه مبنای اعتماد نباشد. |
| `core/identity/mfa_policy.py` | policy عمل حساس و حداکثر سن MFA | تصمیم step-up متمرکز، قابل‌آزمون و ثبت‌شده باشد. |

### 2.2 مدل داده پیشنهادی

| جدول/مدل | ستون‌های حیاتی | کاربرد |
| --- | --- | --- |
| `identity_providers` | `id`, `issuer`, `tenant_id`, `client_id`, `jwks_uri`, `enabled` | نگاشت صریح هر IdP مجاز؛ جلوگیری از issuer ناشناخته. |
| `external_identities` | `user_id`, `provider_id`, `subject`, `object_id`, `last_seen_at` | اتصال کاربر محلی به شناسه immutable IdP. |
| `auth_sessions` | `id`, `user_id`, `provider_id`, `issued_at`, `expires_at`, `auth_time`, `mfa_at`, `aal`, `revoked_at`, `device_id` | منبع context قابل‌اعتماد برای `AuthorizationService`. |
| `group_role_mappings` | `provider_id`, `group_object_id`, `role_code`, `company_scope` | تبدیل گروه‌های سازمانی به نقش محلی در محدوده شرکت. |
| `identity_events` | `session_id`, `event`, `result`, `correlation_id`, `metadata_redacted` | مسیر حسابرسی ورود، step-up، خروج، failure و provisioning. |
| `break_glass_accounts` | `user_id`, `review_due_at`, `vault_reference`, `enabled` | حساب اضطراری با کنترل جداگانه، بازبینی دوره‌ای و MFA قوی. |

### 2.3 جریان ورود پیشنهادی

1. اپلیکیشن فقط authority، tenant شناخته‌شده، client ID و redirect URI ثبت‌شده را بارگذاری می‌کند.
2. `IdentityClient` یک `state` و `nonce` تصادفی تولید می‌کند، PKCE verifier/challenge می‌سازد و مرورگر سیستمی را باز می‌کند.
3. IdP policy سازمانی را اعمال می‌کند: SSO، Conditional Access، MFA و authentication strength.
4. loopback listener فقط callback مورد انتظار را می‌پذیرد؛ redirect URI، `state` و `nonce` باید دقیقاً تطبیق داده شوند.
5. client با MSAL یا کتابخانه پشتیبانی‌شده token را دریافت می‌کند؛ validator امضا، issuer، audience، expiry و claims ضروری را کنترل می‌کند.
6. `sub` به همراه `iss` یا Microsoft `oid` به `ExternalIdentity` نگاشت می‌شود. در صورت مجازبودن JIT، فقط membership پیش‌تأییدشده ساخته می‌شود؛ نقش پیش‌فرض نباید admin باشد.
7. `AuthSessionManager` یک `AuthenticatedPrincipal` غیرقابل‌تغییر ایجاد می‌کند. این principal شامل `actor_id`، شناسه نشست، `auth_time`، `mfa_at`، assurance level و expiry است.
8. هر فراخوانی سرویس، context را از principal می‌سازد. هیچ صفحه PySide6 یا script نباید خودسرانه `mfa_verified=True` ارسال کند.

Microsoft برای desktop/native application استفاده از redirect URI مناسب و PKCE را بیان می‌کند؛ public client نباید client secret را روی دستگاه نگه دارد.[1]

### 2.4 انتخاب IdP و مسیر Active Directory

| سناریوی مشتری | انتخاب پیشنهادی | دلیل |
| --- | --- | --- |
| سازمان Microsoft 365 یا Hybrid AD | **Microsoft Entra ID + MSAL** | مدیریت MFA، Conditional Access، lifecycle و SSO مدرن متمرکز می‌شود. |
| Active Directory محلی با Entra Connect | **AD → Entra hybrid identity → OIDC** | کلاینت با OIDC استاندارد کار می‌کند و از LDAP مستقیم دور می‌ماند. |
| سازمان با AD FS موجود | **AD FS OIDC**، با migration roadmap به Entra | سازگاری کنترل‌شده با زیرساخت فعلی؛ اما پیچیدگی عملیات و patching باید پذیرفته شود. |
| Windows domain-joined کاملاً داخلی | **IWA فقط به‌عنوان بهینه‌سازی UX** | IWA نشانه هویت است، اما policy MFA/step-up و اعتبار token همچنان باید در IdP/Session layer برقرار باشد. |
| سازمان غیرMicrosoft | **OIDC استاندارد** با adapter IdP | وابستگی محصول به provider خاص کاهش می‌یابد؛ Okta/Ping/Keycloak امکان‌پذیر است. |

**Active Directory مستقیم با LDAP/Kerberos در اپلیکیشن دسکتاپ توصیه اصلی نیست.** این الگو اعتبارسنجی credential و سیاست‌های lifecycle را وارد کلاینت می‌کند، exposure سطح حمله را افزایش می‌دهد و با فروش چندمشتری سخت‌تر سازگار می‌شود. اگر lookup گروه AD لازم است، آن را پشت یک integration service کنترل‌شده و با حساب service حداقل‌دسترسی انجام دهید.

## 3. طراحی MFA و Step-up

### 3.1 سیاست پیشنهادی factorها

| سطح | روش ترجیحی | روش جایگزین محدود | کاربرد |
| --- | --- | --- | --- |
| پایه | SSO Entra + passwordless/FIDO2/Windows Hello for Business | TOTP authenticator app | ورود عادی به داده کم‌حساسیت. |
| حساس | FIDO2/passkey یا Windows Hello for Business در policy IdP | TOTP در صورت پذیرش policy مشتری | اتصال/حذف بانک، تغییر role، ارسال بیرونی گزارش. |
| اضطراری | break-glass جداگانه، Vault و بازبینی دو‌نفره | recovery code یک‌بارمصرف با approval | فقط برای بازگردانی کنترل‌شده، نه مسیر روزمره. |

SMS و email را برای عملیات حساس، factor اصلی یا تنها روش recovery در نظر نگیرید. OWASP یادآوری می‌کند که email فقط زمانی می‌تواند «چیزی که کاربر دارد» تلقی شود که خود حساب ایمیل با MFA حفاظت شده باشد و معمولاً از TOTP یا certificate ضعیف‌تر است.[3]

### 3.2 جایگزینی `mfa_verified` با context قابل‌اثبات

```python
@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: int
    session_id: str
    issuer: str
    subject: str
    authenticated_at: datetime
    mfa_at: datetime | None
    assurance_level: str
    expires_at: datetime

    def is_step_up_valid(self, max_age: timedelta) -> bool:
        return self.mfa_at is not None and utcnow() - self.mfa_at <= max_age
```

`AuthorizationContext` باید از این object تولید شود، نه از checkbox یا پارامتر UI. برای عملیات حساس، `MfaPolicy.require_step_up(principal, action)` حداکثر سن MFA را کنترل می‌کند و در صورت نیاز، جریان OIDC interactive را با policy/claim challenge مناسب آغاز می‌نماید.

### 3.3 سیاست عملیاتی نمونه

| عمل | حداقل شرط | مرحله اضافی |
| --- | --- | --- |
| مشاهده داشبورد یا گزارش داخلی | نشست معتبر + `report.generate` | ندارد، مگر risk signal. |
| sync بانکی | نشست معتبر + `bank.sync` | در صورت تغییر دستگاه یا risk signal، step-up. |
| Link یا unlink بانک | `bank.link` / `bank.unlink` + MFA تازه | تأیید کاربر، audit correlation ID و notification. |
| تغییر role یا membership | `identity.role.assign` + MFA تازه | منع اعطای نقشی بالاتر از اختیار اعطاکننده؛ maker-checker در مشتری حساس. |
| ارسال خارجی PDF/Excel | `report.deliver.external` + MFA تازه | allowlist گیرنده، approval دوم در صورت policy. |
| بستن دوره یا ثبت با ارزش بالا | `ledger.entry.post` + MFA تازه | تفکیک وظیفه و workflow تأیید. |

NIST برای AAL2 یک عامل مقاوم در برابر فیشینگ را گزینه الزامی می‌داند و برای نشست AAL2، overall timeout حداکثر ۲۴ ساعت و inactivity timeout پیشنهادی حداکثر یک ساعت را مطرح می‌کند.[2] مقادیر نهایی باید با مدل تهدید و نیازهای مشتری تنظیم شوند؛ این اعداد جایگزین الزامات قراردادی یا قانونی نیستند.

## 4. اجرای مرحله‌ای v2.3.0

| مرحله | خروجی مهندسی | معیار پذیرش |
| --- | --- | --- |
| 0 — Threat model | asset inventory، trust boundary، policy action matrix | تمام عملیات حساس و مسیرهای مستقیم سرویس در threat model پوشش دارند. |
| 1 — Identity core | مدل provider/session، OIDC validator، AuthenticatedPrincipal | token نامعتبر یا issuer ناشناخته session ایجاد نمی‌کند. |
| 2 — Entra SSO | app registration، MSAL desktop flow، JIT/provisioning محدود | login با user سازمانی و logout/session expiry قابل آزمون است. |
| 3 — MFA/step-up | MFA policy، auth context، reauthentication trigger | عملیات حساس با MFA قدیمی، غایب یا جعلی رد می‌شوند. |
| 4 — RBAC bridge | group-to-role mapping و membership scope | گروه خارجی فقط نقش‌های allowlist‌شده در شرکت مشخص را می‌گیرد. |
| 5 — Operations | audit، alert، break-glass، key/session rotation | رویدادهای هویتی و ردهای حساس قابل پیگیری‌اند. |
| 6 — Assurance | test suite، SAST/DAST، pentest مستقل و remediation | یافته بحرانی/بالا قبل از production بسته یا به‌طور رسمی پذیرفته شده است. |

## 5. برنامه تست نفوذ و پایداری

### 5.1 قواعد اجرا

تست نفوذ فقط باید با **مجوز کتبی**، محدوده مشخص، حساب‌های آزمایشی، محیط ایزوله و پنجره زمانی مصوب انجام شود. Plaid Production، بانک واقعی، token مشتری، email/Telegram واقعی و دیتای مالی واقعی خارج از محدوده پیش‌فرض هستند. برای integration بانکی از Sandbox و داده ساختگی استفاده شود. هیچ تستی نباید به‌صورت مخرب، پنهان یا بدون هماهنگی روی شبکه مشتری یا سرویس ثالث اجرا شود.

| گام | فعالیت | خروجی |
| --- | --- | --- |
| Scope | تعریف دارایی‌ها، endpointها، buildها، providerها و موارد خارج از محدوده | Rules of Engagement و inventory. |
| Threat model | تحلیل هویت، token، RBAC، DPAPI، Plaid، گزارش و scheduler | سناریوهای اولویت‌دار و test cases. |
| Automated checks | SAST، dependency/SBOM، secret scan، lint و unit/integration tests | یافته‌های تکرارپذیر در CI. |
| Manual verification | آزمون مجوز، MFA، OIDC، نگهداری کلید و business logic | گزارش فنی با evidence redacted. |
| Resilience | failure injection کنترل‌شده، backup/restore، concurrency و outage IdP | گزارش پایداری و runbook. |
| Retest | راستی‌آزمایی remediation | وضعیت یافته‌ها و residual risk. |

OWASP تأکید می‌کند که MFA باید در تمام مسیرهای ورود، APIها، providerهای فدره و قابلیت‌های امنیتی حساس به‌صورت یکنواخت بررسی شود؛ همچنین هدف تست MFA، ارزیابی مقاومت و تلاش کنترل‌شده برای یافتن bypass است.[3]

### 5.2 ماتریس سناریوهای امنیتی

| حوزه | سناریوی آزمون کنترل‌شده | نتیجه مورد انتظار |
| --- | --- | --- |
| OIDC/PKCE | redirect URI، `state`، `nonce` یا PKCE verifier نامعتبر/بازپخش‌شده | ورود متوقف، session صادر نشود، event بدون secret ثبت شود. |
| Token validation | issuer، audience، signature، expiry یا clock skew نامعتبر | token رد شود؛ claims بدون validation مبنای role نباشند. |
| MFA bypass | تکمیل عامل اول و فراخوانی مستقیم سرویس حساس؛ تغییر یا حذف flag MFA | عملیات حساس رد شود و audit denial ثبت گردد. |
| MFA recovery | reset MFA، recovery code، تغییر factor یا دستگاه جدید | re-authentication و کنترل حداقل هم‌سطح MFA اعمال شود؛ code یک‌بارمصرف باشد. |
| OTP resilience | تلاش کنترل‌شده برای reuse، expiration، rate-limit و spam request | OTP بازپخش نشود؛ limit/lockout/alert فعال باشد. |
| SSO group mapping | گروه نامعتبر، group object ID ناشناخته، حذف عضویت یا تغییر group | نقش پیش‌فرض admin نشود؛ revoke در چرخه تعیین‌شده اثر کند. |
| Horizontal RBAC | user شرکت A با `company_id` شرکت B، item یا report شناسه B را درخواست کند | وجود منبع افشا نشود یا عمل با deny ثبت‌شده متوقف شود. |
| Vertical RBAC | viewer تلاش کند API/CLI سرویس `bank.link` یا `ledger.entry.post` را مستقیم صدا بزند | سرویس، نه فقط UI، درخواست را رد کند. |
| Stale session | کاربر پس از revoke role/membership یا logout همچنان عمل حساس بخواهد | نشست/permission cache باطل و درخواست رد شود. |
| DPAPI | decrypt فایل `.dpapi` از Windows user یا دستگاه دیگر؛ rollback migration | کلید بازیابی نشود؛ fail-closed و runbook recovery روشن باشد. |
| Secret leakage | بررسی log، crash dump، backup، گزارش PDF/XLSX و error message | token، key، TOTP secret و credential در artifactها وجود نداشته باشد. |
| Plaid | public token reuse، cursor failure، Item شرکت دیگر یا unlink شکست‌خورده | token یک‌بارمصرف، cursor atomic، scope صحیح و عدم حذف داده محلی در خطای remote. |
| Report delivery | recipient خارج از allowlist، header injection، schedule بدون identity | ارسال متوقف و audit ثبت شود؛ service account scope کنترل شود. |
| Scheduler | نبود `ACTOR_ID`، actor فاقد مجوز، MFA context منقضی | job fail-closed شود، نه اینکه با account مدیر اجرا شود. |
| Supply chain | dependency آسیب‌پذیر، secret در git، build بدون `win32crypt` | CI fail شود؛ SBOM و بسته EXE بازبینی شوند. |

### 5.3 سناریوهای پایداری و بازیابی

| سناریو | روش ایمن | انتظار عملیاتی |
| --- | --- | --- |
| قطع IdP یا اینترنت | شبیه‌سازی timeout و DNS failure در محیط test | ورود جدید انجام نشود؛ نشست قبلی فقط در policy تعریف‌شده کار کند؛ عمل حساس step-up نشود. |
| انقضای token حین عملیات | token کوتاه‌عمر آزمایشی و retry کنترل‌شده | refresh/interactive flow صحیح باشد؛ عملیات مالی دوبار ثبت نشود. |
| هم‌زمانی sync و گزارش | اجرای parallel روی داده مصنوعی با قفل/transaction واقعی | ledger متوازن بماند، cursor نیمه‌کاره ذخیره نشود و report snapshot سازگار باشد. |
| crash در migration DPAPI | fault injection میان write اتمیک و حذف raw key | یا حالت قبل باقی بماند یا نسخه DPAPI سالم موجود باشد؛ هر دو کلید ناامن نمانند. |
| revoke نقش هنگام job | revoke در میانه schedule test | job بعدی مجوز را دوباره بررسی کند؛ ارسال جدید رخ ندهد. |
| backup/restore | restore در محیط منفصل با key policy معتبر | داده بازیابی شود بدون انتشار secret؛ recovery در runbook مستند باشد. |
| حجم گزارش و بار UI | داده ساختگی و افزایش تدریجی تا ظرفیت مصوب | responsiveness، timeout و memory در برابر SLO مصوب سنجیده شوند؛ نه با عدد فرضی. |

### 5.4 ابزارها و اتوماسیون پیشنهادی

| لایه | ابزار/روش پیشنهادی | زمان اجرا |
| --- | --- | --- |
| Python SAST | Bandit و Semgrep ruleهای سفارشی برای token/logging/DPAPI | هر Pull Request. |
| Dependency | `pip-audit`، lockfile و SBOM | هر build و اسکن دوره‌ای. |
| Secret scan | Gitleaks یا ابزار مشابه با pre-commit و CI | هر commit/PR. |
| Unit/integration | pytest/unittest با fake IdP و fake Plaid | هر PR. |
| Authorization regression | ماتریس user × company × role × permission × action | هر PR و پیش از release. |
| Desktop package | Windows VM تمیز، نصب EXE، تست `win32crypt` و ACL | هر release candidate. |
| Manual penetration test | تیم مستقل با Rules of Engagement | پیش از Production حساس و پس از تغییر عمده هویت. |

OWASP توصیه می‌کند کنترل‌های مجوز در هر عملیات حفاظت‌شده validate شوند، با تست واحد و یکپارچه پوشش داده شوند و رفتار deny-by-default برقرار باشد.[4]

### 5.5 معیار خروج از release candidate

نسخه v2.3.0 زمانی آماده pilot سازمانی است که: مسیرهای ورود و step-up با token معتبر/نامعتبر آزمون شده باشند؛ هیچ عملیات حساس بدون session context معتبر انجام نشود؛ mapping گروه به role قابل‌ممیزی باشد؛ testهای tenant isolation و revoke پاس شوند؛ اسکن dependency/secret و SAST clean یا با risk acceptance مکتوب باشند؛ package Windows DPAPI را در حساب استاندارد کاربر تست کرده باشد؛ و تست نفوذ مستقل برای محیط target برنامه‌ریزی و نتایج آن وارد چرخه remediation شده باشد.

## 6. ریسک‌های قابل‌مدیریت

| ریسک | کنترل کاهش‌دهنده |
| --- | --- |
| lockout گسترده در زمان تغییر IdP | pilot گروهی، break-glass کنترل‌شده، runbook و roll-back. |
| role بیش‌ازحد از گروه AD | allowlist گروه با object ID، role کوچک، review دوره‌ای و deny-by-default. |
| MFA fatigue | phishing-resistant method، number matching در provider، rate limiting و step-up فقط برای عمل حساس. |
| offline desktop | محدودیت زمان نشست local، عدم اجازه عمل حساس نیازمند step-up در حالت offline، audit محلی با sync بعدی. |
| اشتراک workstation | DPAPI user scope، قفل screen، session timeout و عدم اشتراک پروفایل Windows. |
| service account قدرتمند | scope شرکت/عمل محدود، credential vault، rotation و audit جداگانه. |

## منابع

[1]: https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow "Microsoft identity platform — OAuth 2.0 authorization code flow"
[2]: https://pages.nist.gov/800-63-4/sp800-63b.html "NIST SP 800-63B — Authentication and Authenticator Management"
[3]: https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/04-Authentication_Testing/11-Testing_Multi-Factor_Authentication "OWASP WSTG — Testing Multi-Factor Authentication"
[4]: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html "OWASP Authorization Cheat Sheet"
