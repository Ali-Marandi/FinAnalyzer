# بازبینی فنی Bank Reconciliation Workspace و کنترل‌های SoD — v2.7.0

## دامنه و نتیجه بازبینی

بازبینی کد `core/bank_reconciliation.py`، migration v2.7، اتصال Plaid sync، RBAC، کنترل Close Readiness و تست‌های `test_bank_reconciliation_v27.py` انجام شد. نتیجه این است که **مسیرهای اصلی تطبیق بانکی، تفکیک وظایف exception و حفاظت از دوره بسته، به‌درستی در لایه سرویس اعمال شده‌اند**؛ UI تنها مصرف‌کننده service است و تصمیم مجوز را اتخاذ نمی‌کند.

مجموعه هدفمند شامل **۲۱ تست** مربوط به reconciliation، Plaid sync و Period Close مجدداً اجرا شد و همگی موفق بودند. اعتبارسنجی پیش از انتشار v2.7.0 نیز کل مجموعه **۴۰ تست** را با موفقیت گذرانده بود.

## مسیر داده و mutation مجاز

`PlaidConnector._post_or_replace()` برای هر تراکنش جدید یا provider revision، `reconciliation_status` را به `NEEDS_REVIEW` بازنشانی، note/reviewer/timestamp پیشین را پاک و یک journal entry متوازن ایجاد یا جایگزین می‌کند. در نتیجه یک match قدیمی با اصلاح provider معتبر باقی نمی‌ماند.

`BankReconciliationService._reconcile()` فقط پس از یافتن mapping در company scope، اعتبار principal، MFA تازه، permission حساس و بازبودن دوره مالی اجرا می‌شود. سپس service شناسه حساب بانک محلی را تعیین می‌کند و انتظار دارد دقیقاً یک خط غیر بانکی در entry وجود داشته باشد. تنها همان خط به contra account منتخب منتقل می‌شود. هیچ مبلغ، تاریخ، خط بانک یا entry جدیدی ساخته نمی‌شود.

| کنترل | محل اجرا | وضعیت بازبینی |
|---|---|---|
| Scope شرکت | `_mapping_for_company()` و کنترل account انتخاب‌شده | تأیید شد |
| MFA تازه | `principal.authorization_context(..., mfa_max_age=15m)` | تأیید شد |
| RBAC deny-by-default | `AuthorizationService.require()` | تأیید شد |
| منع انتخاب حساب بانک به‌عنوان contra | `_reconcile()` | تأیید شد |
| منع تغییر دوره بسته | `_assert_open_and_mutable()` | تأیید شد |
| منع تراکنش pending یا removed | `_assert_open_and_mutable()` | تأیید شد |
| تمامیت حسابداری | تغییر فقط یک contra line در entry متوازن | تأیید شد |
| ردگیری عملیاتی | `AuditLogger.record()` با actor، company، session و target mapping | تأیید شد |

## کنترل‌های SoD

سه سطح عملیاتی برقرار است. نخست، نقش‌های Bank Operator و Accountant فقط `bank.reconcile.match` دارند و permission رفع exception ندارند. دوم، `bank.reconcile.exception.resolve` یک permission حساس مستقل است که به Finance Manager و Financial Controller داده شده است. سوم و مهم‌تر، حتی اگر یک کاربر هر دو permission را داشته باشد، کد بررسی می‌کند که `reconciled_by_user_id` exception با user حل‌کننده یکسان نباشد. در صورت نقض، service رویداد `bank.reconciliation.sod_denied` را در HMAC chain ثبت و operation را رد می‌کند.

> جداسازی permission به‌تنهایی کافی نیست؛ کنترل هویتی در سطح mapping از self-resolution جلوگیری می‌کند.

## پوشش آزمون تأییدشده

| سناریو | تست | نتیجه |
|---|---|---:|
| تراکنش جدید در صف و بدون raw payload | `test_imported_feed_item_appears_as_needs_review_without_raw_payload` | موفق |
| match و حفظ توازن debit/credit | `test_match_changes_only_contra_account_and_preserves_balanced_entry` | موفق |
| self-resolution exception و audit denial | `test_exception_requires_independent_resolver` | موفق |
| منع reclassification در دوره بسته | `test_locked_period_cannot_be_reclassified` | موفق |
| blocker شدن مورد بررسی‌نشده برای close | `test_close_readiness_can_distinguish_unreconciled_feed_work` | موفق |
| rollback mapping/cursor/entry هنگام sync دوره بسته | `test_sync_for_closed_fiscal_period_rolls_back_mapping_cursor_and_entry` | موفق |
| منع void ناشی از revision/removal در دوره بسته | `test_bank_revision_cannot_void_entry_in_closed_fiscal_period` و `test_bank_removal_cannot_void_entry_in_closed_fiscal_period` | موفق |

## یافته‌های بهبود برای v2.8.0

هیچ نقص بحرانی در دامنه بازبینی مشاهده نشد؛ بااین‌حال، سه hardening زیر باید در نسخه بعدی اولویت داشته باشند. نخست، افزودن **optimistic concurrency/versioning** به mapping تا دو reviewer هم‌زمان نتوانند آخرین تصمیم یکدیگر را overwrite کنند. دوم، تعریف **policy مبتنی بر مبلغ و ریسک** تا تراکنش‌های بالاتر از آستانه یا vendorهای پرریسک همیشه به dual approval نیاز داشته باشند؛ match عادی امروز به maker-checker اجباری نیاز ندارد. سوم، استفاده از allow-list برای account type و policy حساب contra تا طبقه‌بندی به حساب‌هایی مانند equity یا contra نامناسب تنها با approval policy مجاز باشد.

قابلیت تجاری سطح بالاتر پیشنهادی، **Statement Reconciliation Intelligence** است: import CSV/OFX، matching قطعی بر اساس شناسه و مبلغ، matching پیشنهادی بر اساس تاریخ/مبلغ/نام merchant، confidence قابل توضیح، split matching و certification balance. هر پیشنهاد باید توسط انسان تأیید شود؛ مدل هوشمند هرگز نباید بدون permission و approval، ledger را mutate کند.
