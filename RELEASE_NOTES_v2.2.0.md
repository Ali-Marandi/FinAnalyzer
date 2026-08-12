# FinAnalyzer Enterprise v2.2.0 — Enterprise Security Foundation

## خلاصه

نسخه v2.2.0 لایه امنیت سازمانی FinAnalyzer را از نقش‌های ساده در رابط کاربری به کنترل مجوز سرویس‌محور، محدوده‌دار و رد-پیش‌فرض ارتقا می‌دهد. این نسخه همچنین حفاظت کلید رمزنگاری محلی را در Windows از فایل raw به **Windows DPAPI** منتقل می‌کند.

## قابلیت‌های جدید

| حوزه | تغییر |
| --- | --- |
| RBAC محدوده‌دار | مدل‌های `CompanyMembership`، `Role`، `Permission`، `MembershipRole` و `RolePermission` افزوده شد. |
| رد پیش‌فرض | `AuthorizationService` تنها در صورت عضویت فعال در شرکت و مجوز صریح، عملیات را مجاز می‌کند. |
| MFA policy | عملیات حساس Plaid، زمان‌بندی گزارش و تحویل خارجی گزارش به context MFA نیاز دارند. |
| اعمال در سرویس | `PlaidConnector` و `AutomatedReportService` کنترل مجوز را در خود سرویس اجرا می‌کنند. |
| رابط کاربری | صفحات Bank Connections و Financial Reports بدون actor مجاز، عملیات محافظت‌شده را غیرفعال می‌کنند. |
| DPAPI | کلید Fernet محلی در Windows با DPAPI محافظت می‌شود؛ failure در DPAPI به fallback فایل raw تبدیل نمی‌شود. |
| مهاجرت کلید | فایل خام legacy در اولین اجرای موفق به `.dpapi` منتقل و حذف می‌شود. |
| بسته‌بندی EXE | اسکریپت Windows، ماژول `core.authorization` و `win32crypt` را به PyInstaller اضافه می‌کند. |

## تغییرات ناسازگار

1. عملیات Plaid اکنون `actor_id` می‌گیرند؛ اتصال و حذف بانک نیازمند `mfa_verified=True` هستند.
2. ساخت یا اجرای زمان‌بندی گزارش اکنون identity مجاز نیاز دارد. Task Scheduler باید `FINANALYZER_SCHEDULER_ACTOR_ID` را داشته باشد.
3. در Windows، اگر DPAPI نتواند کلید را بازیابی کند، برنامه عمداً به key-file خام برنمی‌گردد.

## اعتبارسنجی

هفت آزمون یکپارچه برای deny-by-default، tenant scope، MFA، DPAPI، مهاجرت کلید، رمزنگاری Plaid و گزارش‌های زمان‌بندی‌شده با موفقیت اجرا شده‌اند. جزئیات استقرار در [`docs/ENTERPRISE_SECURITY_V2_2.md`](docs/ENTERPRISE_SECURITY_V2_2.md) موجود است.
