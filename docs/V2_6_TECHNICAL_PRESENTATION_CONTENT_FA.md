# محتوای اسلایدهای معرفی فنی FinAnalyzer Enterprise v2.6.0

## Cover

**FinAnalyzer Enterprise v2.6.0**

امنیت قابل‌راستی‌آزمایی، بستن دوره کنترل‌شده و شواهد انطباقی برای عملیات مالی سازمانی

ارائه فنی برای هیئت‌مدیره، مدیر مالی، امنیت و فناوری اطلاعات

## Slide 1 — v2.6.0 از «کنترل» به «اثبات» حرکت می‌کند

- قفل دوره مالی، بدون آمادگی اثبات‌شده اجرا نمی‌شود.
- تراکنش بانکی معلق یا دفتر نامتوازن، close را مسدود می‌کند.
- هر کنترل حساس، evidence ساختاریافته و HMAC-chained ایجاد می‌کند.
- خروجی جدید، بسته شواهد قابل انتقال به نگهداری سازمانی است.

## Slide 2 — معماری کنترل‌های حساس

- **هویت:** Entra SSO، OIDC/PKCE و context کاربر احراز‌شده.
- **اجازه:** RBAC با deny-by-default و scope شرکت.
- **اطمینان:** MFA تازه برای close، export evidence و امضای release.
- **شواهد:** audit ساختاریافته با actor، company، session، request و outcome.

## Slide 3 — آمادگی close یک gate قابل‌توضیح است

- بررسی دوره موجود/باز، account حقوق صاحبان سهام و request فعال.
- تشخیص journal entry نامتوازن در بازه مالی.
- تشخیص pending bank transaction پیش از lock.
- توقف close در صورت نامعتبر بودن audit chain.

## Slide 4 — دو کنترل مستقل، یک تصمیم نهایی

- Finance Manager درخواست close را با MFA تازه ایجاد می‌کند.
- Financial Controller مستقل آن را approve و execute می‌کند.
- Self-approval و self-rejection مسدود و audit می‌شوند.
- readiness در زمان approval دوباره اجرا می‌شود؛ وضعیت درخواست قدیمی کافی نیست.

## Slide 5 — Sync بانکی باید اتمیک و idempotent باشد

- sync موفق: entry متوازن، transaction lines، mapping و cursor همگی ثبت می‌شوند.
- failure: هر چهار اثر به state قبلی rollback می‌شوند.
- created، modified و removed در دوره بسته قبل از mutation مسدود می‌شوند.
- provider transaction ID به mapping یکتا متصل است تا retry، entry تکراری نسازد.

## Slide 6 — DPAPI و HMAC-SHA256 از evidence محلی حفاظت می‌کنند

- کلید audit ۳۲ بایتی روی Windows با DPAPI و context کاربر/دستگاه محافظت می‌شود.
- payload canonical و redacted با HMAC-SHA256 امضا می‌شود.
- `previous_hash` و sequence حذف، reorder و تغییر event را آشکار می‌کنند.
- `key_id` از تعویض خاموش کلید جلوگیری می‌کند؛ rotation نیازمند فرآیند change-controlled است.

## Slide 7 — Evidence Pack خروجی قابل‌ممیزی کنترل‌هاست

- export تنها پس از MFA تازه، permission صریح و verify موفق chain انجام می‌شود.
- JSON pack شامل audit events، fiscal years، period-close history و manifest است.
- manifest شامل SHA-256 هر فایل، head hash و sequence audit است.
- خروجی باید به SIEM، DMS یا WORM سازمان منتقل شود؛ local disk مقصد نهایی evidence نیست.

## Slide 8 — انتشار Windows بدون private key در CI

- GitHub-hosted Windows runner build، dependency gate و test suite را اجرا می‌کند.
- GitHub OIDC، token کوتاه‌عمر را با Microsoft Entra مبادله می‌کند.
- Azure Artifact Signing، Authenticode SHA-256 و RFC 3161 timestamp را اعمال می‌کند.
- Release شامل EXE، SHA-256 و evidence signer/timestamp است.

## Slide 9 — خط لوله release دارای دفاع در عمق است

- فقط tagهای semantic و commit منطبق با tag قابل امضا هستند.
- `production-signing` به approval مستقل و منع self-review وابسته است.
- GitHub Actionها روی SHA immutable قفل شده‌اند.
- `signtool verify /tw` و `Get-AuthenticodeSignature` نبود timestamp یا signature نامعتبر را fail می‌کنند.

## Slide 10 — پوشش آزمون از policy تا rollback امتداد دارد

- آزمون‌های identity، MFA، RBAC، DPAPI، HMAC tamper detection و migration audit.
- آزمون‌های SoD: self-approval، self-rejection، scope، MFA منقضی و duplicate request.
- آزمون‌های بانک: closed-period create/revise/remove و rollback mapping/cursor/entry.
- آزمون‌های evidence: MFA/permission، manifest hash، redaction و chain tamper blocking.

## Slide 11 — اولویت‌های توسعه تجاری بعدی

- **Reconciliation Workspace:** تطبیق statement، bank feed و ledger با workflow exception.
- **SIEM/WORM Anchor:** ارسال head hash و evidence manifest به مخزن مستقل سازمانی.
- **Approval Policy Builder:** سقف مبلغ، نقش، entity و SoD ruleهای قابل پیکربندی.
- **Consolidation و FX:** close چندشرکتی، elimination و remeasurement کنترل‌شده.

## Slide 12 — تصمیم اجرایی پیشنهادی

**تصمیم کوتاه‌مدت:** تکمیل `production-signing` در Azure/Entra/GitHub و اجرای نخستین release امضاشده در staging.

**تصمیم میان‌مدت:** انتخاب مقصد SIEM/WORM و آغاز Reconciliation Workspace.

**معیار موفقیت:** close بدون exception پنهان، artifact قابل‌راستی‌آزمایی و evidence قابل دفاع در حسابرسی.
