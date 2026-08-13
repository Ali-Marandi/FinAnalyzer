# بررسی عمیق DPAPI و HMAC-SHA256 در FinAnalyzer v2.5.0

این سند توضیح می‌دهد که FinAnalyzer چگونه از کلید audit محافظت می‌کند، چرا هر رخداد به رخداد قبلی متصل می‌شود و این کنترل‌ها کدام تهدیدها را پوشش می‌دهند. این معماری به‌طور عمدی **tamper-evident محلی** است؛ یک سامانه WORM، SIEM خارجی یا تضمین حسابرسی قانونی به‌شمار نمی‌رود.

> **نتیجه کلیدی:** DPAPI از key material در حالت rest روی Windows محافظت می‌کند. HMAC-SHA256 با همان کلید، اصالت و اتصال ترتیب audit events را بررسی می‌کند. هیچ‌کدام به تنهایی جایگزین کنترل دسترسی database، backup امن یا نگهداری evidence خارج از workstation نیستند.

## ۱. معماری کنترل‌ها

| لایه | مؤلفه FinAnalyzer | وظیفه |
|---|---|---|
| تولید کلید | `AuditSigningKeyStore` | تولید کلید تصادفی ۳۲ بایتی از `os.urandom(32)` در نخستین اجرا |
| حفاظت local key | `WindowsDpapiProtector` | فراخوانی `win32crypt.CryptProtectData` و ذخیره blob محافظت‌شده در `.dpapi` |
| شناسایی کلید | `key_id` | ۱۶ رقم hex نخست SHA-256 کلید؛ برای تشخیص تعویض ناخواسته کلید، نه برای افشای خود key |
| امضای event | `AuditLogger._sign` | HMAC-SHA256 روی JSON canonical و UTF-8 |
| اتصال رخداد | `previous_hash` | هر event به HMAC رخداد قبلی متصل می‌شود |
| checkpoint | `AuditChainState` | آخرین sequence، hash و key ID را نگهداری می‌کند |
| اعتبارسنجی | `verify_chain()` | sequence، hash-link، HMAC هر event و checkpoint نهایی را بررسی می‌کند |
| حداقل‌سازی داده | `_redact()` | secret، token، password، cookie و authorization header را پیش از persistence حذف می‌کند |

## ۲. DPAPI در پیاده‌سازی پروژه

### ۲.۱ مسیر Windows

در Windows، `AuditSigningKeyStore` ابتدا مسیر `data/.finanalyzer.audit.hmac.dpapi` را بررسی می‌کند. اگر blob وجود داشته باشد، `WindowsDpapiProtector.unprotect()` آن را با `CryptUnprotectData` باز می‌کند. اگر وجود نداشته باشد، سیستم یک کلید ۳۲ بایتی تولید می‌کند، آن را با `CryptProtectData` می‌پوشاند و به شکل atomic می‌نویسد.

Microsoft بیان می‌کند که `CryptProtectData` معمولاً فقط به کاربری که با همان logon credential داده را محافظت کرده و روی همان computer اجرا می‌شود اجازه decrypt می‌دهد. این API در زمان protect یک session key ایجاد می‌کند و در زمان unprotect آن را دوباره مشتق می‌کند؛ همچنین به blob رمز‌شده MAC اضافه می‌کند تا تغییر غیرمجاز قابل‌شناسایی شود.[1] `CryptUnprotectData` نیز decrypt و integrity check blob را انجام می‌دهد.[2]

```text
کلید ۳۲ بایتی audit
       │
       ▼
CryptProtectData(key, description='FinAnalyzer Enterprise local encryption key')
       │
       ▼
data/.finanalyzer.audit.hmac.dpapi
       │
       ▼
CryptUnprotectData(blob) فقط در context کاربر/دستگاه مناسب
```

در پیاده‌سازی، DPAPI با `flags=0` فراخوانی می‌شود؛ بنابراین از user-profile default DPAPI استفاده می‌شود. نرم‌افزار در زمان CI یا migration نباید blob `.dpapi` را به دستگاه یا حساب کاربری دیگری منتقل و قابل‌استفاده فرض کند. failure در unprotect به `AuditIntegrityError` تبدیل می‌شود و مسیر audit به‌صورت fail-closed ادامه نمی‌دهد.

### ۲.۲ مهاجرت key legacy و نوشتن atomic

اگر فایل key legacy خام وجود داشته باشد، store آن را یک بار می‌خواند، blob DPAPI می‌سازد و سپس raw file را حذف می‌کند. نوشتن با فایل موقت، `flush`، `fsync` و `os.replace` انجام می‌شود تا crash وسط نوشتن، فایل key نیمه‌کاره ایجاد نکند. اگر حذف raw legacy key موفق نشود، خطای integrity صادر می‌شود تا نسخه ناامن خام باقی‌مانده نادیده گرفته نشود.

### ۲.۳ مسیرهای غیرWindows و environment

| وضعیت | رفتار | وضعیت مجاز |
|---|---|---|
| Windows local | DPAPI blob، بدون raw key پایدار | production desktop Windows |
| Linux/macOS development | فایل raw با permission هدف `0600` | توسعه و تست محلی، نه deployment enterprise |
| `FINANALYZER_AUDIT_HMAC_KEY` | string حداقل ۳۲ کاراکتری از environment | فقط وقتی secret در KMS/secret injection سازمانی محافظت می‌شود |

Environment override مفید است، اما DPAPI را دور می‌زند. بنابراین نباید در `.env`، GitHub repository، console history، log یا asset release قرار گیرد. اگر KMS در دسترس باشد، secret injection زمان اجرا با least privilege نسبت به فایل key یا hard-code ارجح است.

## ۳. HMAC-SHA256 و payload canonical

هر event جدید با `AuditLogger.record()` ساخته می‌شود. پیش از HMAC، timestamp به UTC تبدیل می‌شود و payload با کلیدهای مرتب‌شده، جداکننده‌های ثابت JSON و UTF-8 canonical می‌گردد. این payload شامل داده‌های زیر است:

| گروه | فیلدهای نمونه | هدف |
|---|---|---|
| هویت رخداد | `event_id`، `sequence`، `timestamp` | uniqueness و ترتیب قابل‌بررسی |
| actor/scope | `actor_id`، `company_id`، `session_id`، `request_id` | پیگیری عملیات در tenant و session درست |
| عملیات | `action`، `category`، `outcome`، `severity`، `source` | تحلیل امنیتی و عملیاتی |
| هدف | `target_type`، `target_id` | اتصال رخداد به object یا request مشخص |
| زنجیره | `previous_hash`، `key_id` | اتصال event و تشخیص key تغییرکرده |
| context امن | `details` پس از redaction | evidence کاربردی بدون secret |

تابع `_sign()` معادل مفهومی زیر را اجرا می‌کند:

```python
canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
event_hash = hmac.new(hmac_key, canonical, hashlib.sha256).hexdigest()
```

HMAC یک MAC مبتنی بر کلید است، نه یک hash ساده. شخصی که فقط database را دارد می‌تواند SHA-256 جدید محاسبه کند، اما بدون HMAC key نمی‌تواند `event_hash` معتبر برای payload تغییرکرده بسازد. کتابخانه استاندارد Python HMAC را مطابق RFC 2104 پیاده‌سازی می‌کند و `compare_digest()` را برای کاهش short-circuit مبتنی بر محتوا در مقایسه پیشنهاد می‌دهد.[3] FinAnalyzer در `verify_chain()` از `hmac.compare_digest()` استفاده می‌کند.

## ۴. نحوه اتصال chain

```text
GENESIS_HASH = 000…000
       │
       ▼
Event 1: previous_hash = GENESIS_HASH  ──HMAC──► hash_1
       │
       ▼
Event 2: previous_hash = hash_1        ──HMAC──► hash_2
       │
       ▼
Event 3: previous_hash = hash_2        ──HMAC──► hash_3
       │
       ▼
AuditChainState: last_sequence=3, last_hash=hash_3, key_id=<key fingerprint>
```

این ساختار چهار نوع ناهنجاری را آشکار می‌کند.

| نوع تغییر | نتیجه `verify_chain()` |
|---|---|
| تغییر details، action یا actor یک event | HMAC همان event نامعتبر می‌شود |
| حذف event میانی | `previous_hash` یا sequence رخداد بعدی mismatch می‌شود |
| جابه‌جایی رخدادها | sequence مورد انتظار و previous hash mismatch می‌شود |
| تغییر checkpoint نهایی | checkpoint با head زنجیره برابر نیست |
| جایگزینی HMAC key در فایل local | `key_id` جدید با checkpoint قدیمی متفاوت است و `record()` fail-closed می‌شود |

برای هر event جدید، `AuditChainState` در همان SQLAlchemy transaction همراه event update می‌شود. در failure مسیر business transaction، event success مربوط نیز rollback می‌شود؛ نمونه مهم آن execution ناموفق Period Close و apply ناموفق Plaid sync در دوره بسته است.

## ۵. redaction قبل از امضا و ذخیره‌سازی

`_redact()` یک traversal بازگشتی برای `Mapping` و list/tuple/set انجام می‌دهد. اگر نام key، بدون توجه به بزرگی/کوچکی حروف، در مجموعه حساس باشد، مقدار به `[REDACTED]` تبدیل می‌شود. مجموعه فعلی شامل `access_token`، `refresh_token`، `id_token`، `public_token`، `password`، `secret`، `client_secret`، `private_key`، `cookie`، `authorization` و `encrypted_access_token` است.

ترتیب عملیات مهم است: **ابتدا redaction، سپس canonicalization و HMAC، سپس persistence**. بنابراین هم database و هم HMAC payload فاقد مقدار secret هستند. تغییر مستقیم database از `[REDACTED]` به مقدار دیگر نیز verification را شکست می‌دهد.

> redaction مبتنی بر نام key است، نه data-loss-prevention کامل. توسعه‌دهندگان نباید secret را در keyهای نامرتبط مانند `comment` یا `description` قرار دهند. برای production، review schema، logging guideline و secret scanning مکمل این کنترل هستند.

## ۶. key rotation و recovery

در نسخه فعلی، تعویض key بدون procedure approved **عمداً مسدود** است. `AuditChainState.key_id` با fingerprint کلید فعلی مقایسه می‌شود؛ عدم تطابق باعث `AuditIntegrityError` می‌شود. این رفتار مانع از آن است که حذف یا جایگزینی blob DPAPI به‌طور خاموش به یک زنجیره جدید و غیرقابل‌مقایسه منجر شود.

فرایند پیشنهادی برای rotation سازمانی چنین است:

۱. export و `verify_chain()` آخرین chain قدیمی را انجام دهید؛ head hash، sequence، زمان و key ID را در evidence غیرقابل‌تغییر ثبت کنید.

۲. approval دوگانه امنیت و مالی دریافت کنید و window نگهداری اعلام کنید.

۳. key جدید را از KMS یا CSPRNG ایجاد کنید، با DPAPI context صحیح protect و key ID آن را ثبت کنید.

۴. یک migration versioned بنویسید که checkpoint chain قدیمی، chain جدید و evidence anchor را به‌صراحت نگهداری کند. `key_id` صرفاً با overwrite فایل تغییر نکند.

۵. در SIEM/evidence store ثبت کنید که زنجیره جدید از کدام sequence و head hash قبلی آغاز شده است.

۶. verify مستقل، تست recovery و بازبینی دسترسی‌های DPAPI/KMS را اجرا کنید.

این workflow در کد فعلی خودکار نشده است؛ به‌دلیل اثر حسابرسی، باید به‌صورت change-controlled پیاده‌سازی و آزموده شود.

## ۷. تهدیدها، پوشش و محدودیت‌ها

| تهدید | کنترل فعلی | محدودیت یا کنترل مکمل |
|---|---|---|
| خواندن database بدون Windows profile/key | HMAC key در DPAPI blob است؛ event جعل‌پذیر نیست | دسترسی database را همچنان با ACL و encryption کنترل کنید |
| تغییر تک event | HMAC mismatch | verifier باید واقعاً اجرا و نتیجه نگهداری شود |
| حذف یا reorder event | sequence و previous hash mismatch | snapshot/evidence خارجی برای تشخیص حذف کل database لازم است |
| copy فایل DB به دستگاه دیگر | DPAPI user/machine scope معمولاً unprotect را ناکام می‌کند.[1] [2] | backup/recovery policy باید context DPAPI یا key escrow مجاز داشته باشد |
| compromise کاربر Windows و database | attacker ممکن است همان DPAPI context را استفاده کند | SIEM/WORM، EDR، least privilege و evidence export لازم است |
| key حذف/تعویض تصادفی | key ID mismatch؛ write fail-closed | rotation runbook approved و backup recovery لازم است |
| secret در audit | redaction بر اساس key name | logging policy و secret scanner برای semantic leakage لازم است |

فایل `core/audit.py` نیز تصریح می‌کند که attacker دارای کنترل Windows profile، local database و DPAPI context ممکن است از مدل محلی عبور کند. بنابراین برای استقرار enterprise، anchorهای head hash، export رویدادها و نتیجه verification باید به SIEM یا evidence store مورد تأیید سازمان منتقل شوند.

## ۸. کنترل‌های عملیاتی پیشنهادی

| تناوب | کنترل | evidence |
|---|---|---|
| هر release | اجرای تست audit و `verify_chain()` روی database نمونه | log test و report verification |
| روزانه یا هر close | export sequence/head hash به SIEM یا storage جدا | hash anchor با زمان ثبت |
| ماهانه | review failure eventها، `key_id` و ACL مسیر data | گزارش access review |
| هر تغییر key | dual approval، anchor قدیمی/جدید و recovery test | ticket change و report validation |
| هر incident | copy read-only از DB، `verify_chain()`، حفظ blob و logs | پرونده evidence و chain result |

## مراجع

[1] [Microsoft Learn — CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)

[2] [Microsoft Learn — CryptUnprotectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptunprotectdata)

[3] [Python Documentation — hmac: Keyed-Hashing for Message Authentication](https://docs.python.org/3/library/hmac.html)
