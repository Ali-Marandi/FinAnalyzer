# یادداشت انتشار FinAnalyzer Enterprise — نسخه 2.5.0

**تاریخ انتشار:** ۱۳ اوت ۲۰۲۶
**وضعیت:** آماده برای build و امضای Windows در محیط ایزوله
**حوزه انتشار:** کنترل بستن دوره مالی، تفکیک وظایف، رابط دسکتاپ و automation امضای EXE

> نسخه 2.5.0 بر پایه امنیت v2.4.0 ساخته شده است. این انتشار، یک کنترل تجاری قابل‌استفاده را به محصول اضافه می‌کند: بستن سال مالی تنها با درخواست و تأیید دو کاربر مستقل، MFA تازه و شواهد audit زنجیره‌ای انجام می‌شود.

## قابلیت جدید: Controlled Financial Period Close

FinAnalyzer اکنون workflow بستن دوره مالی را از یک فراخوانی مستقیم حسابداری به یک فرایند کنترل‌شده تبدیل می‌کند. کاربر دارای مجوز `ledger.period.close.request` می‌تواند با یک session دارای MFA تازه درخواست بستن سال مالی ثبت کند. سپس کاربر مستقل دارای مجوز `ledger.period.close.approve`—نقش پیشنهادی `financial_controller`—می‌تواند درخواست را بررسی، رد یا تأیید و اجرا کند.

| کنترل | رفتار v2.5.0 |
|---|---|
| MFA | هر دو مرحله درخواست و تأیید به MFA حداکثر ۱۵ دقیقه نیاز دارند. |
| RBAC | دو permission حساس مستقل برای درخواست و تأیید تعریف شده‌اند. |
| تفکیک وظایف | درخواست‌کننده نمی‌تواند درخواست خود را تأیید یا رد کند. |
| محدوده شرکت | درخواست، حساب retained earnings و سال مالی در scope همان company بررسی می‌شوند. |
| atomicity | closing entry، قفل سال مالی، وضعیت workflow و رخداد audit در یک تراکنش هماهنگ ثبت می‌شوند. |
| هم‌زمانی | SQLite فقط یک درخواست active (`PENDING` یا `APPROVED`) برای هر شرکت/سال مالی می‌پذیرد. |
| ممیزی | درخواست، اجرا و تلاش نقض SoD با audit event ساختاریافته در HMAC chain ثبت می‌شوند. |

## تجربه دسکتاپ

صفحه جدید **Period Close Controls** به navigation اپلیکیشن افزوده شد. این صفحه امکان ثبت درخواست، انتخاب درخواست، تأیید/اجرای close و مشاهده تاریخچه درخواست‌ها را فراهم می‌کند. عملیات حساس تا زمان SSO سازمانی و ارائه evidence MFA معتبر، غیرفعال هستند.

## انتشار Windows امضاشده

اسکریپت PowerShell جدید `scripts/build_signed_windows_release.ps1` کل مسیر release را در یک فرایند fail-closed انجام می‌دهد: ایجاد virtual environment تازه، نصب manifest ساخت، اجرای dependency gate، ساخت EXE، امضای Authenticode با گواهی موجود در certificate store کاربر release، RFC 3161 timestamp، verification با SignTool و تولید evidence SHA-256.

| خروجی | مسیر |
|---|---|
| فایل اجرایی | `dist/FinAnalyzer_Enterprise_v2_5.exe` |
| snapshot وابستگی‌ها | `security-reports/windows-build-dependencies.json` |
| خروجی ممیزی بسته‌ها | `security-reports/pip-audit.json` |
| evidence امضا | `security-reports/signed-release-evidence.json` |

کلید خصوصی گواهی در آرگومان خط فرمان، repository یا فایل release قرار نمی‌گیرد. اسکریپت فقط thumbprint گواهی را می‌پذیرد و وجود private key، Code Signing EKU و اعتبار گواهی را پیش از امضا کنترل می‌کند.

## اعتبارسنجی

| کنترل | نتیجه |
|---|---|
| syntax compile ماژول‌های جدید و رابط UI | موفق |
| تست کامل پروژه | ۲۰ تست موفق |
| بستن دوره با تأیید کاربر مستقل | موفق |
| مسدودسازی self-approval و ثبت audit | موفق |
| رد درخواست با MFA منقضی | موفق |
| وابستگی‌های Windows و `pip-audit` | موفق در محیط اعتبارسنجی |

## سازگاری و ملاحظات ارتقا

migration این نسخه افزایشی است. جدول `period_close_requests` و index کنترل درخواست فعال با `Base.metadata.create_all()` و migration SQLite ایجاد می‌شوند. اجرای `DatabaseManager.init_database()` در شروع برنامه علاوه بر schema، role و permission جدید `financial_controller` و catalog مجوزهای بستن دوره را به‌صورت idempotent bootstrap می‌کند.

برای release عمومی Windows، باید فایل EXE نهایی طبق `docs/V2_5_SIGNED_WINDOWS_EXE_FA.md` در VM ویندوز clean ساخته، امضا و مستقلاً verify شود. این repository هیچ private key، PFX یا artifact امضانشده‌ای را منتشر نمی‌کند.
