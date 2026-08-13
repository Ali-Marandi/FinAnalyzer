# سناریوهای تست Atomicity و Idempotency سینک بانکی در دوره مالی بسته

این برنامه آزمون مسیرهای Plaid و Period Close را بررسی می‌کند تا اطمینان دهد یک failure در sync باعث entry نیمه‌ثبت‌شده، mapping ناقص یا cursor پیش‌رفته نمی‌شود و هیچ تراکنش تازه، اصلاح‌شده یا حذف‌شده‌ای نمی‌تواند period بسته را تغییر دهد.

> **قاعده کنترل:** اگر transaction به fiscal year بسته تعلق داشته باشد، سیستم باید پیش از هر mutation از جمله `post_journal_entry`، void entry، ساخت mapping یا ذخیره cursor متوقف شود. نتیجه باید یک خطای قابل‌فهم و رخداد audit ساختاریافته باشد، نه تغییر جزئی در database.

## مرز transaction مورد آزمون

یک sync موفق چهار اثر persistent دارد: journal entry متوازن، transaction lines، `PlaidTransactionMapping` برای idempotency و cursor جدید روی `PlaidItem`. در failure، این چهار اثر باید با یک database transaction rollback شوند.

| اثر persistent | انتظار در sync موفق | انتظار هنگام failure یا دوره بسته |
|---|---|---|
| Journal entry | یک entry متوازن و posted | هیچ entry جدید یا void ناخواسته |
| Transaction lines | debit و credit با جمع برابر | هیچ line باقی‌مانده |
| Mapping | یک mapping برای provider transaction ID | هیچ mapping تازه یا تغییر mapping قدیمی |
| Cursor | به cursor پاسخ provider منتقل می‌شود | cursor قبلی بدون تغییر می‌ماند |
| Audit | رخداد success زنجیره‌ای | رخداد failure/denied زنجیره‌ای با company و target درست |

## ماتریس سناریوهای دقیق

| شناسه | setup | محرک | assertionهای اجباری | وضعیت پوشش |
|---|---|---|---|---|
| BS-01 | دوره باز، payload جدید متوازن | اولین sync | یک entry posted، یک mapping، cursor جدید، chain valid | پوشش‌شده در `test_exchange_encrypts_token_and_sync_posts_balanced_entry` |
| BS-02 | همان provider transaction ID دوباره دریافت شود | retry provider / network retry | entry دوم ایجاد نشود؛ mapping یکتا باقی بماند؛ cursor فقط طبق پاسخ معتبر جلو برود | باید در هر تغییر provider client regression شود |
| BS-03 | دوره باز، provider payload باعث failure پس از آغاز transaction شود | خطای post یا mapping | entry، lines، mapping و cursor همگی به state قبل برگردند | کنترل transaction و rollback service |
| BS-04 | FiscalYear شامل تاریخ تراکنش از قبل `is_closed=True` | تراکنش جدید در `added` | `PeriodCloseError`/خطای کنترل؛ entry=۰، mapping=۰، cursor ثابت، audit failure | پوشش‌شده در `test_sync_for_closed_fiscal_period_rolls_back_mapping_cursor_and_entry` |
| BS-05 | تراکنش قبلاً import شده، دوره آن اکنون بسته است | همان تراکنش در `modified` | entry قبلی void نشود؛ mapping و cursor تغییر نکنند؛ audit failure | پوشش‌شده در `test_bank_revision_cannot_void_entry_in_closed_fiscal_period` |
| BS-06 | تراکنش قبلاً import شده، دوره آن اکنون بسته است | همان تراکنش در `removed` | entry قبلی void نشود؛ mapping و cursor تغییر نکنند؛ audit failure | پوشش‌شده در `test_bank_removal_cannot_void_entry_in_closed_fiscal_period` |
| BS-07 | Period Close pending، سپس pending bank mapping ایجاد شود | approval و execute close | close مسدود، request pending، fiscal year باز، readiness audit denied | پوشش‌شده در `test_approval_rechecks_readiness_before_locking` |
| BS-08 | pending bank mapping موجود است | ایجاد close request | هیچ request جدید؛ readiness blocker `pending_bank_transactions` و audit chain valid | پوشش‌شده در `test_pending_bank_transaction_blocks_request_and_is_audited` |
| BS-09 | provider transaction ID موجود، mapping inconsistency | sync retry | از index یکتا exception یا service-safe rejection؛ duplicate entry ممنوع | regression تست توصیه‌شده پیش از تغییر schema |
| BS-10 | دو sync هم‌زمان روی همان item | concurrent calls | حداکثر یک entry و یک mapping؛ cursor monotonic؛ transaction دوم conflict-safe | تست integration روی SQLite/WAL یا DB target نهایی توصیه می‌شود |
| BS-11 | response شامل چند transaction: یکی باز و یکی بسته | sync batch mixed period | **سیاست فعلی atomic batch:** failure closed-period نباید partial batch یا cursor advance ایجاد کند | باید در contract provider تغییر نکند |
| BS-12 | audit HMAC key یا event تاریخی دستکاری شده است | readiness یا close بعد از tamper | `audit_chain_invalid` blocker؛ هیچ close و هیچ bank mutation مجاز نیست | readiness control v2.5 |

## ساختار assertion استاندارد

هر تست failure باید پیش و پس از call، state database را مقایسه کند. صرف انتظار برای exception کافی نیست.

```python
before_cursor = item.cursor
before_entry_count = count_journal_entries(company_id)
before_mapping_count = count_transaction_mappings(item.id)

with self.assertRaises(PeriodCloseError):
    connector.sync_transactions(...)

self.assertEqual(current_cursor(item.id), before_cursor)
self.assertEqual(count_journal_entries(company_id), before_entry_count)
self.assertEqual(count_transaction_mappings(item.id), before_mapping_count)
self.assertTrue(audit_logger.verify_chain(session).valid)
```

برای revision و removal باید علاوه بر count، status entry اصلی assert شود:

```python
self.assertEqual(existing_entry.status, TransactionStatus.POSTED)
self.assertFalse(entry_was_voided(existing_entry.id))
```

## سناریوی Regression برای بستن دوره

۱. fiscal year 2025 را باز، retained earnings account را فعال و دو کاربر مستقل دارای MFA معتبر ایجاد کنید.

۲. یک تراکنش بانکی وارد و mapping آن را ثبت کنید. در مرحله اول bank sync باید entry متوازن، mapping یکتا و cursor جدید بسازد.

۳. کاربر اول close request می‌سازد؛ کاربر دوم آن را approve و execute می‌کند. `FiscalYear.is_closed` باید true شود.

۴. همان `provider_transaction_id` را یک‌بار در `modified` و یک‌بار در `removed` به fake provider برگردانید. هر دو call باید failure بدهند، اما entry قبلی همچنان posted بماند، mapping حذف/تغییر نشود و cursor جلو نرود.

۵. یک provider transaction جدید با تاریخ داخل 2025 برگردانید. entry یا mapping جدید نباید persist شود.

۶. `AuditLogger.verify_chain()` را اجرا کنید. نتیجه باید valid باشد و رخدادهای failure دارای `company_id`، `source='plaid_connector'` و target مرتبط باشند.

## معیار پذیرش انتشار

| شرط | معیار پذیرش |
|---|---|
| Atomicity | در تمام failureها state چهارگانه entry/lines/mapping/cursor بدون تغییر یا کامل rollback شود |
| Idempotency | هر `provider_transaction_id` حداکثر به یک mapping و یک journal entry مرتبط باشد |
| Close lock | created، modified و removed مربوط به دوره بسته قبل از mutation مسدود شوند |
| Authorization | عملیات بانکی حساس بدون `AuthenticatedPrincipal` و MFA تازه مجاز نباشد |
| Evidence | audit chain پس از success و failure معتبر باشد و secret provider در details دیده نشود |
| Regression | `python -m unittest tests.test_plaid_v2 tests.test_period_close_v25 -v` موفق باشد |

## نکته عملیاتی

ماتریس BS-10 و BS-11 باید پیش از انتقال به database server چندکاربره به integration test واقعی ارتقا یابد. SQLite/WAL برای desktop خوب است، اما رفتار lock و concurrency در SQL Server/PostgreSQL یا sync worker توزیع‌شده باید جداگانه آزمایش شود. هیچ policy حسابداری حساس نباید صرفاً بر رفتار mock provider تکیه کند.
