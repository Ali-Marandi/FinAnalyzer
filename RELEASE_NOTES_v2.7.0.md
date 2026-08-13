# FinAnalyzer Enterprise v2.7.0 — Controlled Bank Reconciliation

**نوع انتشار:** قابلیت تجاری سازمانی و کنترل تکمیلی پیش از بستن دوره مالی.

## قابلیت جدید: Bank Reconciliation Workspace

v2.7.0 یک فضای تطبیق بانکی به برنامه desktop اضافه می‌کند. postingهای جدید یا اصلاح‌شده در bank feed دیگر به‌عنوان طبقه‌بندی‌شده تلقی نمی‌شوند. هر `PlaidTransactionMapping` وضعیت تطبیق مستقل دارد و پس از import یا provider revision به `needs_review` بازمی‌گردد.

| وضعیت | نتیجه |
|---|---|
| `needs_review` | نیازمند طبقه‌بندی انسانی پیش از close |
| `exception` | نیازمند رفع توسط reviewer مستقل |
| `matched` | طبقه‌بندی contra تأیید شده است |
| `removed` | تراکنش از provider حذف شده و دیگر در صف review نیست |

کاربر مجاز می‌تواند یک حساب contra هم‌شرکت و فعال انتخاب کند. سیستم فقط خط غیر بانکی همان journal entry متوازن را تغییر می‌دهد؛ مبلغ، خط بانک و تعداد lineها تغییر نمی‌کنند. انتخاب حساب بانک به‌عنوان contra، تراکنش pending، journal entry غیرposted، mapping حذف‌شده و هر دوره قفل‌شده block می‌شوند.

## کنترل‌های امنیتی

permissionهای جدید `bank.reconcile.match` و `bank.reconcile.exception.resolve` به RBAC افزوده شدند. هر دو حساس هستند و MFA تازه می‌خواهند. کاربر ثبت‌کننده exception نمی‌تواند همان exception را resolve کند؛ این انکار به‌صورت `bank.reconciliation.sod_denied` در زنجیره HMAC ثبت می‌شود. service layer، نه UI، مجوز و scope شرکت را اعمال می‌کند.

`PeriodCloseService` اکنون علاوه بر تراکنش بانکی pending، هر mapping با وضعیت `needs_review` یا `exception` را به‌عنوان blocker با کد `unreconciled_bank_transactions` گزارش می‌کند. این بررسی هم هنگام request و هم قبل از approval/execution انجام می‌شود.

## تجربه دسکتاپ

یک صفحه جدید با نام **Bank Reconciliation** به navigation اضافه شده است. صفحه summary وضعیت‌ها، صف باز بدون raw provider payload، انتخاب حساب contra، ثبت note و عملیات match/flag exception/resolve exception را فراهم می‌کند. عملیات همواره پس از Enterprise SSO انجام می‌شوند و در صورت شکست، UI ادعای تغییر جزئی موفق نمی‌کند.

## migration و سازگاری

migration افزایشی SQLite v2.7 ستون‌های reconciliation status، note، reviewer و timestamp را به `plaid_transaction_mappings` اضافه می‌کند. mappingهای موجود به‌صورت محافظه‌کارانه با `NEEDS_REVIEW` مقداردهی می‌شوند تا close بدون reviewِ تاریخچه feed انجام نشود. هیچ داده یا entry موجود حذف نمی‌شود.

## آزمون و اعتبارسنجی

تست جدید `test_bank_reconciliation_v27.py` پنج سناریو را پوشش می‌دهد: صف بررسی بدون raw payload، match متوازن، SoD برای exception، منع reclassification در دوره بسته و blocker readiness برای کار بانکی بررسی‌نشده. اجرای نهایی شامل کل test suite، کنترل نحوی، dependency gate Windows و بررسی diff خواهد بود.

## مسیر تجاری بعدی

اولویت بعدی پیشنهادی **Statement Reconciliation** است: import statement، تطبیق شناسه و مبلغ با tolerance کنترل‌شده، split matching، certification balance و exception aging. سپس anchor کردن manifestهای evidence به SIEM یا WORM مستقل، سطح اطمینان audit را از workstation محلی فراتر می‌برد.
