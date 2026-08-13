# FinAnalyzer Enterprise v2.6.1 — Verified Compliance Evidence

**نوع انتشار:** قابلیت تجاری و سخت‌سازی انتشار.

## افزوده‌های اصلی

نسخه v2.6.1 قابلیت **Compliance Evidence Pack** را اضافه می‌کند. این سرویس پس از MFA تازه، permission صریح `compliance.evidence.export` و اعتبارسنجی موفق کامل زنجیره HMAC، یک پوشه JSON company-scoped تولید می‌کند. محتوا شامل رخدادهای audit، سال‌های مالی، تاریخچه Period Close و `manifest.json` است. manifest، SHA-256 هر فایل و checkpoint زنجیره audit را نگه می‌دارد تا دریافت‌کننده مستقل بتواند integrity بسته را بررسی کند.

Export از یک chain نامعتبر عبور نمی‌کند. در این حالت، export block می‌شود، یک رخداد audit با outcome `denied` ثبت می‌گردد و هیچ پوشه partial قابل استفاده‌ای باقی نمی‌ماند. موفقیت export نیز به‌عنوان رخداد compliance ثبت می‌شود. فایل محلی evidence فقط یک staging point است و باید به مقصد تأییدشده SIEM، DMS یا WORM سازمان منتقل شود.

| کنترل | رفتار v2.6.1 |
|---|---|
| Authentication | `AuthenticatedPrincipal` معتبر از Enterprise SSO الزامی است |
| Authorization | permission حساس `compliance.evidence.export` در scope همان شرکت بررسی می‌شود |
| MFA | حداکثر سن MFA برای export برابر ۱۵ دقیقه است |
| Audit integrity | `AuditLogger.verify_chain()` پیش از نوشتن فایل‌ها اجرا می‌شود |
| Confidentiality | جزئیات audit که قبلاً redact شده‌اند export می‌شوند؛ secret جدید ذخیره نمی‌شود |
| File integrity | hash هر JSON و hash canonical manifest در evidence ثبت می‌شود |

## رابط دسکتاپ

یک صفحه جدید با نام **Compliance Evidence** به برنامه Windows اضافه شده است. صفحه، session فعال را نمایش می‌دهد، Company ID و output directory می‌گیرد و manifest، SHA-256 و شمارش رخدادها را پس از export گزارش می‌کند. صفحه تنها accessibility UI است؛ authorization واقعی همچنان در service layer اجرا می‌شود.

## بازبینی GitHub Actions

workflow امضای release با چهار SHA immutable برای `actions/checkout`، `actions/setup-python`، `azure/login` و Azure Artifact Signing action سخت‌تر شده است. این تغییر، وابستگی workflow به tagهای متحرک action را کاهش می‌دهد. artifactهای v2.6.1 به نام `FinAnalyzer_Enterprise_v2_6_1.exe` تولید می‌شوند.

> امضای cloud واقعی هنوز منوط به پیکربندی Azure Artifact Signing، Entra federated credential و GitHub Environment `production-signing` است. تا پیش از تکمیل این تنظیمات، هیچ EXE امضاشده‌ای نباید به‌عنوان production artifact منتشر شود.

## آزمون و اعتبارسنجی

مجموعه کامل پروژه با **۳۵ تست موفق** اجرا شد. تست‌های جدید Evidence Pack، permission و MFA، manifest hash، redaction رخداد export و مسدودشدن export برای audit chain دستکاری‌شده را پوشش می‌دهند. کنترل نحوی ماژول‌های جدید، `git diff --check` و dependency gate Windows نیز با موفقیت اجرا شدند.

## قابلیت‌های پیشنهادی بعدی

| اولویت | قابلیت | دلیل تجاری |
|---|---|---|
| بالا | Reconciliation Workspace | حل exceptionهای bank/ledger پیش از close و کاهش زمان بستن ماهانه |
| بالا | SIEM/WORM Anchor | نگهداری مستقل head hash و manifest برای کنترل compromise محلی |
| متوسط | Approval Policy Builder | تنظیم ruleهای مبلغ، entity و SoD بدون تغییر code |
| متوسط | Consolidation و FX | پشتیبانی گروه‌های چندشرکتی و remeasurement کنترل‌شده |
