# راهنمای فنی فضای تطبیق بانکی FinAnalyzer Enterprise v2.7.0

## هدف عملیاتی

**Bank Reconciliation Workspace** یک صف کنترل‌شده برای بررسی postingهای ایجادشده از bank feed است. هدف آن ثبت مجدد تراکنش یا تغییر مبلغ نیست. سرویس فقط خط contra یک journal entry متوازن را، پس از authorization و کنترل قفل دوره، از حساب uncategorized به حساب منتخب شرکت منتقل می‌کند. خط بانک، مبلغ، تاریخ و provenance تراکنش تغییری نمی‌کنند.

این طراحی دو مسئله را هم‌زمان حل می‌کند. نخست، Plaid sync می‌تواند بدون تأخیر، یک ورودی متوازن و قابل‌ردیابی در دفتر ثبت کند؛ دوم، طبقه‌بندی نهایی آن به review انسانی صریح تبدیل می‌شود. در نتیجه close دوره به نبودن تراکنش pending محدود نیست و تراکنش‌های posted اما بررسی‌نشده نیز blocker محسوب می‌شوند.

## مدل وضعیت و اثر آن بر close

| وضعیت | معنای عملیاتی | مجاز برای close | رفتار workflow |
|---|---|---:|---|
| `needs_review` | posting جدید یا provider-revised هنوز طبقه‌بندی انسانی نشده است | خیر | در صف workspace نمایش داده می‌شود؛ می‌تواند match یا exception شود |
| `exception` | reviewer مسئله‌ای را ثبت کرده که به رسیدگی مستقل نیاز دارد | خیر | فقط کاربر مستقلِ دارای permission resolve می‌تواند آن را match کند |
| `matched` | contra account توسط reviewer مجاز انتخاب شده است | بله | entry متوازن باقی می‌ماند و metadata review حفظ می‌شود |
| `removed` | provider تراکنش را حذف کرده است | بله | entry متناظر، تنها در دوره باز، void می‌شود؛ مورد قابل review نیست |

`PeriodCloseService` اکنون هم `pending_bank_transactions` و هم `unreconciled_bank_transactions` را بررسی می‌کند. بنابراین pre-check درخواست close و re-check هنگام approval، هر دو در صورت وجود `needs_review` یا `exception` باز، close را block می‌کنند.

## مرزهای امنیتی و تفکیک وظایف

| عملیات | Permission | MFA تازه | کنترل داده |
|---|---|---:|---|
| مشاهده صف | `ledger.read` | خیر | فقط شرکت principal؛ raw provider payload بازگردانده نمی‌شود |
| match تراکنش | `bank.reconcile.match` | بله | account فعال و هم‌شرکت؛ انتخاب حساب بانک به‌عنوان contra مسدود است |
| flag exception | `bank.reconcile.match` | بله | entry تغییر نمی‌کند؛ reason حداقل سه و حداکثر ۵۰۰ نویسه است |
| resolve exception | `bank.reconcile.exception.resolve` | بله | همان flagger نمی‌تواند exception خود را resolve کند |

برای هر mutation، `AuthenticatedPrincipal`، scope شرکت و MFA با حداکثر سن ۱۵ دقیقه در service layer بررسی می‌شوند. مخفی‌کردن دکمه در UI جایگزین این کنترل نیست. عملیات موفق، exception و انکار SoD در AuditLogger ساختاریافته و HMAC-chained ثبت می‌شوند.

## تمامیت حسابداری و بانک

تطبیق فقط برای `JournalEntry` با وضعیت `POSTED` مجاز است. سرویس، PlaidAccount محلی را پیدا می‌کند، شناسه خط بانک را استخراج می‌کند و دقیقاً یک خط دیگر را به‌عنوان contra line انتظار دارد. ساختار غیرمنتظره entry، account خارج از scope، account غیرفعال، تراکنش pending، mapping removed یا دوره قفل‌شده عملیات را متوقف می‌کند.

> در دوره مالی قفل‌شده، هیچ reclassification، void ناشی از revision یا void ناشی از removal انجام نمی‌شود. Plaid sync در این شرایط cursor، mapping و entry را rollback می‌کند و failure ساختاریافته ثبت می‌کند.

## گردش کار پیشنهادی تیم مالی

ابتدا Bank Connections را sync کنید. تراکنش‌های جدید یا اصلاح‌شده با `needs_review` در workspace ظاهر می‌شوند. Accountant یا Bank Operator با evidence عملیاتی، حساب contra را انتخاب و match می‌کند؛ در صورت نبودن evidence کافی، reason را ثبت و exception را flag می‌کند. Financial Controller مستقل، exception را بررسی و در صورت تأیید، آن را resolve می‌کند. تنها پس از صفر شدن pending و unresolved work، کنترل Close Readiness اجازه پیشرفت workflow بستن دوره را می‌دهد.

## پوشش آزمون

`tests/test_bank_reconciliation_v27.py` موارد زیر را کنترل می‌کند:

| سناریو | انتظار کنترل |
|---|---|
| import جدید | وضعیت پیش‌فرض `needs_review` و عدم نمایش raw payload |
| match مجاز | تغییر فقط contra line، تراز ماندن debit/credit و audit event موفق |
| exception | flagger نمی‌تواند exception خود را resolve کند؛ controller مستقل قادر به resolve است |
| دوره قفل‌شده | reclassification رد و وضعیت mapping تغییر نمی‌کند |
| close readiness | mapping بررسی‌نشده، blocker با کد `unreconciled_bank_transactions` ایجاد می‌کند |

## محدودیت‌های فعلی و مسیر توسعه

نسخه v2.7.0 به feed-based review می‌پردازد؛ در حال حاضر import فایل statement، tolerance-based matching، split matching و statement balance certification پیاده‌سازی نشده‌اند. گام تجاری بعدی می‌تواند **Statement Reconciliation** باشد که CSV/OFX statement را به Plaid mappingها و ledger entryها وصل می‌کند و exceptionهای unmatched را با policy سازمانی مدیریت می‌نماید.
