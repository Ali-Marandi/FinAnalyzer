# FinAnalyzer Enterprise v2.6.0 — آمادگی بستن دوره و انتشار Windows قابل‌راستی‌آزمایی

**نوع انتشار:** قابلیت تجاری و سخت‌سازی امنیتی.
**دامنه:** کنترل‌های پیش از Period Close، اتمیک‌سازی بانک، نمونه قابل‌اجرا برای audit chain و راه‌اندازی امضای خودکار Windows.

## قابلیت تجاری جدید: Close Readiness Controls

v2.6.0 یک کنترل پیشگیرانه پیش از ایجاد یا اجرای Period Close اضافه می‌کند. سرویس `PeriodCloseService.assess_readiness()` یک گزارش explainable تولید می‌کند و request یا approval را دوباره پیش از mutation اصلی بررسی می‌کند. بنابراین «ready بودن در زمان درخواست» برای اجرای close کافی نیست؛ تمام blockerها در مرحله approval نیز ارزیابی می‌شوند.

| blocker | اثر تجاری |
|---|---|
| `fiscal_year_missing` یا `fiscal_year_already_closed` | جلوگیری از close روی دوره نامعتبر یا از پیش قفل‌شده |
| `closing_account_out_of_scope` یا `closing_account_ineligible` | جلوگیری از انتقال سود/زیان به حساب خارج از شرکت یا غیرحقوق صاحبان سهام |
| `active_close_request` | جلوگیری از workflow موازی یا تأییدهای مبهم |
| `unbalanced_journal_entry` | جلوگیری از قفل شدن دفتر دارای entry نامتوازن |
| `pending_bank_transactions` | جلوگیری از close قبل از تعیین تکلیف تراکنش‌های بانکی معلق |
| `audit_chain_invalid` | جلوگیری از close هنگامی که evidence امنیتی local نامعتبر است |

نتیجه assessment در زنجیره HMAC با رخداد `period_close.readiness_assessed` ثبت می‌شود. outcome برابر `success` یا `denied` و جزئیات آن فقط شامل phase، fiscal year و کدهای blocker/warning است؛ secret یا payload بانکی در audit ذخیره نمی‌شود.

## کنترل‌های بانکی و SoD

مسیر Plaid اکنون در sync روی دوره بسته، در revision تراکنش و در removal تراکنش قبل از mutation متوقف می‌شود. failure باید به‌طور atomic journal entry، transaction lines، mapping و cursor را rollback کند. v2.6.0 همچنین readiness را در approval دوباره ارزیابی می‌کند تا pending bank work ایجادشده پس از request، period را به‌اشتباه قفل نکند.

## امضای خودکار Windows و OIDC

workflow `.github/workflows/release-sign.yml` برای release tagهای semantic، build، dependency gate، test suite، Azure OIDC، Azure Artifact Signing، RFC 3161 timestamp، Authenticode verification و upload evidence را آماده می‌کند. این workflow تا زمان پیکربندی Entra Federation و GitHub Environment `production-signing` امضای واقعی انجام نمی‌دهد.

| asset انتشار پس از پیکربندی | هدف |
|---|---|
| `FinAnalyzer_Enterprise_v2_6.exe` | EXE امضاشده Authenticode |
| `FinAnalyzer_Enterprise_v2_6.exe.sha256` | تأیید integrity دانلود |
| `signed-release-evidence.json` | commit، signer، timestamp و hash قابل‌ممیزی |

## نمونه آموزشی audit chain

فایل `scripts/demo_hmac_audit_chain.py` نمونه مستقل و بدون database ارائه می‌دهد. این نمونه redaction، payload canonical، HMAC-SHA256، verification و تغییر عمدی event را نشان می‌دهد. اجرای موفق باید ابتدا chain معتبر و سپس دستکاری در sequence دوم را به‌شکل `HMAC mismatch` گزارش کند.

## اعتبارسنجی

مجموعه Period Close به ۱۲ تست رسید و سناریوهای SoD، MFA، account scope، duplicate request، rollback، pending bank blocker، unbalanced legacy entry و approval recheck را پوشش می‌دهد. مجموعه کامل test suite قبل از release باید همراه dependency gate Windows اجرا شود.

## قابلیت‌های تجاری بعدی

| اولویت | قابلیت | ارزش تجاری |
|---|---|---|
| بالا | Evidence export به SIEM/WORM و anchor روزانه hash | حسابرسی مستقل و کاهش ریسک compromise محلی |
| بالا | Reconciliation workspace برای بانک، ledger و statement | کوتاه‌شدن close cycle و کنترل exceptionها |
| بالا | Approval matrix قابل‌پیکربندی با سقف مبلغ و SoD rule builder | انطباق شرکت‌های چندواحدی و کنترل داخلی دقیق‌تر |
| متوسط | Budget vs actual، forecast scenario و driver-based planning | مدیریت عملکرد و برنامه‌ریزی مالی |
| متوسط | Multi-currency remeasurement و FX gain/loss workflow | پشتیبانی شرکت‌های بین‌المللی |
| متوسط | e-Invoicing، tax engine و integration با ERP/CRM | کاهش ورود دستی و افزایش اتوماسیون |
| متوسط | Document retention، OCR invoice و three-way matching | کنترل AP و آماده‌سازی audit |
| پایین | Mobile approval برای مدیران با device posture | تسریع approvalهای کنترل‌شده |
| پایین | Plugin/connector SDK با sandbox و policy | گسترش اکوسیستم و درآمد B2B |

در این release، قابلیت اولویت‌دار **Close Readiness Controls** از پیشنهاد به پیاده‌سازی، آزمون و رابط دسکتاپ تبدیل شده است. قابلیت بعدی پیشنهادی، Reconciliation Workspace به‌همراه export evidence خارجی است؛ این دو قابلیت باید پس از تعیین سامانه مقصد SIEM/WORM و بانک‌های هدف پیاده‌سازی شوند.
