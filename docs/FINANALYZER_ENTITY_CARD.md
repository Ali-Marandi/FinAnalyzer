# کارت موجودیت — FinAnalyzer

| فیلد | وضعیت فعلی |
|---|---|
| نام محصول / برند | FinAnalyzer Enterprise |
| نام حقوقی | اعلام نشده؛ نیازمند تأیید بنیان‌گذار پیش از قرارداد یا ثبت برند |
| وضعیت مالکیت | محصول نرم‌افزاری خصوصی و self-owned در مخزن `Ali-Marandi/FinAnalyzer` |
| وضعیت بورسی | خصوصی / فاقد ticker و داده مالی عمومی |
| محل فعالیت / حوزه قضایی | اعلام نشده؛ نباید در تحلیل حقوقی یا مالی فرض شود |
| واحد پول گزارشگری | اعلام نشده؛ مدل تجاری جهانی در مرحله پژوهش با USD به‌عنوان واحد مقایسه‌ای و با برچسب «فرض» ارائه خواهد شد |
| سال مالی | اعلام نشده؛ برای forecast مالی نیازمند تعیین است |
| دسته محصول | نرم‌افزار دسکتاپ ویندوزیِ کنترل مالی و عملیات close سازمانی؛ مسیر پیشنهادی به سمت reconciliation intelligence و evidence-driven close |
| مخاطب اولیه محتمل | شرکت‌های کوچک و متوسطِ کنترل‌محور و تیم‌های finance/controller که به segregation of duties، auditability و close controls نیاز دارند؛ نیازمند مصاحبه و اعتبارسنجی |
| فناوری فعلی | Python 3.12، PySide6، SQLite/SQLAlchemy، RBAC، MFA، Entra/OIDC، DPAPI، HMAC audit، Plaid و Bank Reconciliation v2.7.0 |
| محدودیت مهم | قابلیت‌های v2.8.0 مانند PostgreSQL persistence، Split Matching و Statement Intelligence هنوز specification هستند و نباید به‌عنوان قابلیت منتشرشده معرفی شوند |

## نیازهای داده‌ای باز

برای ساخت مدل مالی و برنامه ورود به بازار با سطح اطمینان بالا، داده‌های زیر هنوز موجود نیستند: کشور/بازار beachhead، وضعیت حقوقی شرکت، فهرست مشتری یا design partner، قیمت هدف، هزینه تیم و زیرساخت، چرخه فروش، کانال‌های موجود، و بودجه/مدت runway. تا زمان تکمیل، هر برآورد باید به‌وضوح با برچسب «فرض» یا «سناریوی آزمایشی» ارائه شود.

**تاریخ مرجع کارت:** ۱۴ اوت ۲۰۲۶ (GMT+3:30)

**سطح اطمینان:** متوسط برای وضعیت محصول بر پایه مخزن؛ پایین برای داده‌های تجاری و حقوقی که توسط بنیان‌گذار ارائه نشده‌اند.

## منابع داخلی

- `README.md`، `RELEASE_NOTES_v2.7.0.md` و مستندات v2.7/v2.8 در مخزن FinAnalyzer.
- درخواست راهبردی کاربر در فایل `pasted_content.txt`.

## نتیجه اولیه

FinAnalyzer باید پیش از هر توسعه پراکنده، یک beachhead مشخص، یک بسته ارزش قابل‌فروش، یک مدل استقرار و یک فرضیه قیمت قابل آزمایش تعیین کند. تمایز معنادار اولیه، «کنترل close و تطبیق قابل‌ممیزی با human approval» است، نه صرفاً یک dashboard مالی یا AI عمومی.

```text
Fact: کنترل‌های v2.7.0 در مخزن موجودند.
Assumption: بازار beachhead و willingness-to-pay هنوز تأیید نشده‌اند.
Decision needed: انتخاب بازار، buyer و motion اولیه پیش از مدل‌سازی دقیق TAM/SAM/SOM.
```

## منابع

[1]: https://github.com/Ali-Marandi/FinAnalyzer "مخزن FinAnalyzer"

[2]: https://github.com/Ali-Marandi/FinAnalyzer/releases/tag/v2.7.0 "یادداشت انتشار v2.7.0"

[3]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/docs/V2_8_COMMERCIAL_INTELLIGENCE_ROADMAP_FA.md "نقشه‌راه Commercial Intelligence v2.8.0"

[4]: /home/ubuntu/upload/pasted_content.txt "چارچوب راهبردی تأییدشده کاربر"
