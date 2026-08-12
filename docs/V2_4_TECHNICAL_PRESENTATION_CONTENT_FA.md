## Cover

**FinAnalyzer Enterprise v2.4.0**
امنیت قابل‌راستی‌آزمایی، انتشار Windows امضاشده و کنترل بستن دوره

ارائه فنی برای فناوری، امنیت و مالی سازمانی

## Slide 1

### امنیت از «لاگ» به «شواهد» ارتقا یافت

- رویدادها دیگر فقط متن نیستند؛ metadata ساختاریافته، actor، company و session دارند.
- هر عملیات حساس قابل جست‌وجو، دسته‌بندی و بررسی است.
- هدف: قابلیت پاسخ‌گویی در عملیات بانکی، هویت، گزارش و حسابداری.

## Slide 2

### HMAC chain هر تغییر تاریخی را آشکار می‌کند

- هر رخداد با HMAC-SHA256 امضا و به `previous_hash` رخداد قبل متصل می‌شود.
- شماره توالی و checkpoint، ترتیب وقایع را کنترل می‌کند.
- `verify_chain()` دست‌کاری محتوا، حذف حلقه یا گسست زنجیره را تشخیص می‌دهد.

## Slide 3

### داده حساس پیش از ذخیره حذف می‌شود

- access token، refresh token، password، secret، cookie و authorization redact می‌شوند.
- audit فقط context حداقلی و عملیاتی نگه می‌دارد.
- لاگ امنیتی جایگزین محل نگهداری secret نیست.

## Slide 4

### DPAPI کلیدهای محلی Windows را به حساب کاربری گره می‌زند

- کلید امضای audit در Windows با DPAPI محافظت می‌شود.
- key material خام در repository یا release asset قرار نمی‌گیرد.
- SSO/OIDC، MFA، RBAC و session context لایه‌های مکمل حفاظت هستند.

## Slide 5

### کنترل‌های امنیتی در جریان‌های واقعی محصول ثبت می‌شوند

- Authorization: deny-by-default و ثبت grant/deny حساس.
- Identity: ورود SSO، خروج، revoke و خطای ورود بدون ذخیره token.
- Banking & Reporting: اتصال/همگام‌سازی Plaid و تولید/تحویل گزارش با نتیجه ساختاریافته.

## Slide 6

### انتشار Windows با gate و امضای Authenticode محافظت می‌شود

- baseline build: `pypdf>=6.15.0`، `wheel>=0.46.2` و حذف `xhtml2pdf`.
- `pip-audit` و dependency snapshot، ساخت ناامن را fail-closed متوقف می‌کنند.
- ساخت ایزوله، SignTool، SHA-256، RFC 3161 timestamp و verification، artifact قابل انتشار می‌سازند.

## Slide 7

### اعتبارسنجی عملیاتی، نه ادعای امنیت

- ۲۰ تست واحد و یکپارچه برای audit، RBAC، SSO/MFA، Plaid، گزارش و بستن دوره اجرا شد.
- tamper detection و redaction داده حساس به‌صورت مستقل آزموده شد.
- verification وابستگی‌ها باید در VM Windows clean پیش از هر release تکرار شود.

## Slide 8

### قابلیت جدید: بستن دوره با کنترل دو نفره

- کاربر مالی با MFA درخواست close می‌دهد؛ Financial Controller مستقل تأیید و اجرا می‌کند.
- self-approval و self-rejection مسدود و در audit ثبت می‌شود.
- درخواست، journal close، قفل سال مالی و audit در یک تراکنش هماهنگ می‌شوند.

## Slide 9

### نقشه‌راه تجاری: از داده به تصمیم کنترل‌شده

- اولویت اول: Bank Reconciliation Workbench با صف استثنا و matching قابل‌توضیح.
- سپس: AP approvals، cash forecast، close calendar و multi-entity consolidation.
- همه قابلیت‌ها با MFA، SoD، scope شرکت و audit chain طراحی می‌شوند.

## Slide 10

### گام بعدی: release امضاشده و استقرار کنترل‌شده

**ساخت در VM ایزوله، امضا با کلید سازمانی، verification مستقل و انتشار همراه با SHA-256**
