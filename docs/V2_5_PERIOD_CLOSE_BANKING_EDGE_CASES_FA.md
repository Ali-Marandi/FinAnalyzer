# ماتریس لبه‌های SoD و یکپارچگی بانکی Period Close — FinAnalyzer v2.5.0

این سند نتیجه بازبینی مسیر Period Close و اتصال Plaid با تمرکز بر سناریوهایی است که می‌توانند پس از قفل سال مالی، تمامیت دفترکل، cursor بانکی یا شواهد audit را تهدید کنند. در این بازبینی، دو کنترل اجرایی نیز تقویت شد: posting بانکی اکنون در transaction مشترک sync commit مستقل انجام نمی‌دهد، و revision/removal یک تراکنش بانکی در دوره قفل‌شده پیش از void کردن entry رد می‌شود.

> **اصل کنترل:** یک بانک ممکن است دیرتر از تاریخ تراکنش، تغییر یا حذف آن را گزارش کند؛ اما این تأخیر نباید منجر به درج، void یا جایگزینی entry در سال مالی قفل‌شده شود.

## یافته‌های کلیدی

| حوزه | کنترل جدید یا تأییدشده | اثر |
|---|---|---|
| sync بانکی | `AccountingEngine.post_journal_entry(..., commit=False)` در مسیر Plaid | transaction، mapping، cursor، status و audit success با هم commit یا rollback می‌شوند |
| تراکنش با تاریخ بسته | posting از طریق `_is_period_locked()` رد می‌شود | bank feed نمی‌تواند entry جدید در دوره بسته ایجاد کند |
| revision بانکی | قبل از void entry قدیمی، قفل دوره entry بررسی می‌شود | یک اصلاح بانکی نمی‌تواند entry دوره بسته را void و جایگزین کند |
| removal بانکی | قبل از void entry، قفل دوره بررسی می‌شود | حذف remote نیز دفترکل بسته را تغییر نمی‌دهد |
| خطای apply | رخداد `bank.sync_apply_failed` در transaction جدا با metadata حداقلی ثبت می‌شود | علت failure قابل پیگیری است، بدون ذخیره payload یا secret حساس |
| cursor | فقط پس از apply کامل تغییرات به‌روز می‌شود | failure باعث ردشدن یا گم‌شدن transaction بانکی نمی‌شود |
| SoD | permission check قبل از self-approval check اجرا می‌شود | کاربر فاقد permission تأیید، قبل از رسیدن به منطق SoD رد می‌شود |

## سناریوهای SoD

| سناریو | انتظار امنیتی | آزمون |
|---|---|---|
| Preparer و Controller مستقل | close اجرا شود، سال قفل شود و request `EXECUTED` شود | `test_different_controller_approves_and_locks_fiscal_year` |
| self-approval توسط Company Admin | درخواست `PENDING` بماند؛ `period_close.sod_violation` با `denied` ثبت شود | `test_self_approval_is_blocked_and_audited` |
| self-rejection | درخواست `PENDING` بماند؛ رخداد SoD در HMAC chain قابل‌verify باشد | `test_requester_cannot_reject_own_close_and_event_is_chained` |
| requester بدون permission تأیید | پیش از SoD، `authorization.denied` دریافت کند | `test_requester_without_approval_permission_is_denied_before_sod_check` |
| MFA با عمر ۱۶ دقیقه | ایجاد درخواست پیش از هر تغییر داده رد شود | `test_stale_mfa_cannot_create_close_request` |
| حساب retained earnings متعلق به شرکت دیگر | درخواست ساخته نشود | `test_request_rejects_closing_account_outside_company_scope` |
| درخواست active تکراری | درخواست دوم رد شود | `test_duplicate_active_close_request_is_rejected` |
| failure در accounting | approval، lock و execution audit موفق rollback شوند | `test_execution_failure_rolls_back_approval_close_and_success_audit` |

## سناریوهای بانکی Period Close

### ۱. تراکنش جدید با تاریخ در دوره بسته

Plaid ممکن است transaction جدیدی را با تاریخ گذشته بازگرداند. `PlaidConnector._post_or_replace()` این record را از طریق `AccountingEngine.post_journal_entry()` ثبت می‌کند. آن متد ابتدا `_is_period_locked(record_date)` را بررسی می‌کند. اگر سال مالی شامل تاریخ record بسته باشد، exception ایجاد می‌شود. transaction کلی apply rollback می‌شود؛ mapping، GL account جدید، journal entry، cursor و success event هیچ‌کدام persist نمی‌شوند. سپس فقط یک رخداد امن `bank.sync_apply_failed` در transaction جدا ثبت می‌شود.

این مسیر با `test_sync_for_closed_fiscal_period_rolls_back_mapping_cursor_and_entry` پوشش داده شده است. آزمون ثابت می‌کند mapping و journal entry ایجاد نمی‌شوند، cursor در مقدار قبلی می‌ماند، item همچنان `linked` است و chain audit معتبر می‌ماند.

### ۲. اصلاح تراکنش قبلی در دوره بسته

برای record موجود، sync ممکن است آن را در مجموعه `modified` بیاورد. قبل از v2.5 hardening، مسیر revision می‌توانست entry اصلی را void کند و سپس تلاش ناموفق برای entry جایگزین داشته باشد. اکنون `_assert_entry_not_locked()` تاریخ entry اصلی را کنترل می‌کند. اگر fiscal period بسته باشد، void پیش از هر mutation رد می‌شود.

آزمون `test_bank_revision_cannot_void_entry_in_closed_fiscal_period` ابتدا transaction بانکی را در دوره باز ثبت می‌کند، سپس همان سال را می‌بندد و revision را دریافت می‌کند. نتیجه مورد انتظار و آزموده‌شده این است که cursor تغییر نکند، mapping همچنان به entry اصلی اشاره کند، status entry `posted` بماند و رخداد failure در زنجیره ثبت شود.

### ۳. حذف تراکنش قبلی در دوره بسته

برای record موجود در مجموعه `removed`، منطق حذف نیز پیش از تبدیل status entry به `VOIDED` از همان `_assert_entry_not_locked()` استفاده می‌کند. بنابراین Plaid removal نمی‌تواند تاریخچه دفترکل بسته را تغییر دهد. آزمون `test_bank_removal_cannot_void_entry_in_closed_fiscal_period` این تقارن را به‌صورت regression test تثبیت می‌کند: cursor ثابت می‌ماند، mapping تغییر نمی‌کند، entry همچنان `posted` است و رخداد failure زنجیره‌ای ثبت می‌شود.

## مرزهای باقیمانده و تصمیم‌های policy

| موضوع | رفتار فعلی | پیشنهاد سازمانی |
|---|---|---|
| late bank adjustment در دوره بسته | sync امن rollback و failure audit می‌شود | workflow «adjustment in next open period» با approval مستقل طراحی شود |
| Plaid pending→posted | revision در دوره بسته رد می‌شود | policy مشخص برای pending transaction پیش از close و reconciliation exception لازم است |
| close هم‌زمان با sync | SQLite transaction و partial unique index از request close محافظت می‌کنند؛ sync از period lock پیروی می‌کند | برای استقرار چندکاربره، database server با locking قوی‌تر و queue عملیاتی ارزیابی شود |
| failed sync retry | cursor حفظ می‌شود؛ sync بعدی همان تغییرات را دوباره دریافت می‌کند | dashboard exception و مسئول رسیدگی برای finance team اضافه شود |
| payload بانکی | raw payload در mapping برای چرخه عادی نگهداری می‌شود | retention، دسترسی و redaction payload مطابق policy حریم‌خصوصی سازمان تعریف شود |

## اجرای آزمون‌ها

```bash
python3 -m unittest tests.test_period_close_v25 tests.test_plaid_v2 -v
```

آخرین اجرای بازبینی‌شده شامل **۱۲ آزمون موفق** در دو ماژول Period Close و Plaid بود: ۸ آزمون SoD/Period Close و ۴ آزمون Plaid شامل happy path، تراکنش جدید در دوره بسته، revision در دوره بسته و removal در دوره بسته.

## منابع کد داخلی

| فایل | نقش |
|---|---|
| `core/period_close.py` | workflow درخواست، تأیید، SoD و close اتمی |
| `core/plaid_connector.py` | sync بانکی، cursor، revision/removal و audit failure |
| `core/accounting_engine.py` | قفل دوره در posting journal entry |
| `tests/test_period_close_v25.py` | SoD، permission precedence، MFA، scope و rollback |
| `tests/test_plaid_v2.py` | rollback sync بانکی و عدم void دوره بسته |
