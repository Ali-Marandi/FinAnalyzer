# اسکریپت کامل ارائه فنی FinAnalyzer Enterprise v2.6.0

**زمان پیشنهادی:** ۱۵ تا ۱۸ دقیقه، به‌علاوه ۷ دقیقه پرسش و پاسخ.
**مخاطب:** هیئت‌مدیره، مدیر مالی، مدیر امنیت، تیم فناوری اطلاعات و حسابرس داخلی.
**لحن:** فنی، شفاف و مبتنی بر کنترل‌های قابل‌آزمون؛ از طرح ادعاهای مطلق امنیتی خودداری شود.

## اسلاید جلد — FinAnalyzer Enterprise v2.6.0

«هدف این جلسه نشان دادن یک تغییر مهم در مسیر FinAnalyzer است. ما از ساخت یک ابزار تحلیل مالی عبور کرده‌ایم و اکنون کنترل‌های حساس مالی را به شواهد قابل‌راستی‌آزمایی متصل می‌کنیم. نسخه v2.6.0 سه موضوع را به هم وصل می‌کند: آمادگی پیش از بستن دوره، تمامیت تراکنش‌های بانکی و قابلیت استخراج evidence برای حسابرسی. در پایان ارائه، مشخص خواهد شد که چرا یک lock ساده برای دوره مالی کافی نیست و چگونه می‌توانیم عملیات، log و artifact انتشار را در یک مدل کنترل‌شده قرار دهیم.»

## اسلاید ۱ — v2.6.0 از «کنترل» به «اثبات» حرکت می‌کند

«مسئله اصلی در نرم‌افزار مالی سازمانی این نیست که فقط یک دکمه Close داشته باشیم. پرسش واقعی این است که آیا در لحظه close، داده بانکی معلق وجود دارد، دفتر متوازن است، فرد درست اقدام می‌کند و evidence قابل دفاع باقی می‌ماند یا نه. v2.6.0 این پرسش را به یک gate اجرایی تبدیل می‌کند. اگر تراکنش بانکی pending باشد، entry نامتوازن باشد یا زنجیره audit اعتبار نداشته باشد، درخواست یا اجرای close متوقف می‌شود. این تصمیم صرفاً در UI نمایش داده نمی‌شود؛ به رخداد ساختاریافته HMAC-chained تبدیل می‌شود تا در بازبینی بعدی معلوم باشد چه کسی، در چه شرکت و با چه نتیجه‌ای اقدام کرده است.»

## اسلاید ۲ — معماری کنترل‌های حساس

«معماری از چهار لایه تشکیل شده است. لایه نخست هویت است: کاربر پس از Entra SSO و OIDC/PKCE، یک principal معتبر دریافت می‌کند. لایه دوم مجوز است: RBAC به شکل deny-by-default اعمال می‌شود و هر permission در scope شرکت ارزیابی می‌گردد. لایه سوم assurance است: عملیات حساس مانند close و export evidence به MFA تازه محدود هستند. لایه چهارم evidence است: event فقط یک متن log نیست؛ actor، company، session، request، source، outcome و hash زنجیره‌ای دارد. این جداسازی اهمیت دارد، زیرا پنهان بودن یک دکمه در رابط کاربری جایگزین authorization در service layer نیست.»

## اسلاید ۳ — آمادگی close یک gate قابل‌توضیح است

«Close Readiness Controls یک گزارش قابل‌فهم می‌سازد؛ هدف آن این نیست که صرفاً بگوید اجازه دارید یا ندارید، بلکه دلیل کنترل را نیز مشخص می‌کند. این گزارش وجود و باز بودن دوره، مناسب بودن retained earnings account، نبودن close request فعال، تراز بودن journal entryها، نبودن bank transaction pending و اعتبار audit chain را کنترل می‌کند. هر finding دارای کد، سطح شدت، پیام و در صورت نیاز reference است. بنابراین مدیر مالی می‌تواند exception را رفع کند، نه اینکه فقط با یک خطای مبهم روبه‌رو شود. این کنترل پیش از request و بار دیگر پیش از approval اجرا می‌شود.»

## اسلاید ۴ — دو کنترل مستقل، یک تصمیم نهایی

«ما close را به یک workflow دو نفره تبدیل کرده‌ایم. Finance Manager یا preparer با MFA تازه درخواست می‌سازد. Financial Controller یا Company Admin مستقل که permission approval دارد، درخواست را بررسی می‌کند. یک نفر نمی‌تواند درخواست خودش را approve یا reject کند. این تلاش‌ها در audit به‌عنوان SoD violation ثبت می‌شوند. نکته مهم‌تر این است که approval به وضعیت تاریخی request اعتماد نمی‌کند. درست پیش از اجرا، readiness دوباره محاسبه می‌شود. به این ترتیب، اگر بعد از درخواست یک bank exception جدید ایجاد شده باشد، approval مجاز به قفل کردن دوره نخواهد بود.»

## اسلاید ۵ — Sync بانکی باید اتمیک و idempotent باشد

«در اتصال بانکی، یک sync موفق چهار اثر مرتبط دارد: journal entry، transaction lines، mapping provider transaction و cursor. اگر هر بخش ناموفق باشد، باقی‌گذاشتن سه بخش دیگر ریسک مغایرت ایجاد می‌کند. پیاده‌سازی فعلی این اثرها را در یک transaction نگه می‌دارد. اگر تراکنش به دوره بسته تعلق داشته باشد، قبل از ایجاد entry یا پیشبرد cursor، failure ثبت می‌شود و عملیات rollback می‌گردد. همین کنترل برای revision و removal نیز اعمال شده است. بنابراین تغییر بعدی provider نمی‌تواند entry تاریخچه دوره بسته را void کند. همچنین mapping یکتا، retry شبکه را از ایجاد entry تکراری بازمی‌دارد.»

## اسلاید ۶ — DPAPI و HMAC-SHA256 از evidence محلی حفاظت می‌کنند

«برای integrity local audit، کلید HMAC به صورت تصادفی و ۳۲ بایتی تولید می‌شود. روی Windows، این کلید در قالب blob محافظت‌شده با DPAPI نگهداری می‌شود و معمولاً فقط در context کاربر و دستگاه مناسب قابل بازیابی است. سپس برای هر رخداد، payload canonical پس از redaction با HMAC-SHA256 امضا می‌شود. هر رخداد به hash قبلی و شماره sequence متصل است. بنابراین تغییر محتوای یک event، حذف event میانی یا جابه‌جایی ترتیب رخدادها در verify_chain آشکار می‌شود. ما صریح هستیم که این مدل tamper-evident محلی است؛ اگر مهاجم کنترل کامل Windows profile و database داشته باشد، evidence خارجی مانند SIEM یا WORM همچنان ضروری است.»

## اسلاید ۷ — Evidence Pack خروجی قابل‌ممیزی کنترل‌هاست

«قابلیت جدید Compliance Evidence Pack همان پل بین کنترل داخلی و نگهداری evidence است. export فقط وقتی مجاز است که کاربر MFA تازه داشته باشد، permission صریح `compliance.evidence.export` داشته باشد و زنجیره audit کامل معتبر باشد. بسته JSON شامل رخدادهای شرکت، وضعیت سال‌های مالی، تاریخچه requestهای close و manifest است. manifest برای هر فایل SHA-256، برای chain head hash و sequence ثبت می‌کند. پس از export، خود عمل export نیز audit می‌شود. این بسته نباید به‌عنوان مقصد نهایی evidence روی local disk تلقی شود؛ گام بعد انتقال کنترل‌شده آن به SIEM، DMS یا WORM سازمان است.»

## اسلاید ۸ — انتشار Windows بدون private key در CI

«برای انتشار Windows، اصل راهنما این است که private key وارد GitHub، PFX، command line یا runner نشود. workflow روی runner میزبانی‌شده Windows build و dependency gate را اجرا می‌کند. سپس GitHub OIDC یک token کوتاه‌عمر می‌گیرد و Azure/Entra آن را با access token محدود مبادله می‌کند. Azure Artifact Signing فایل EXE را با Authenticode و SHA-256 امضا می‌کند و timestamp RFC 3161 اضافه می‌شود. خروجی release شامل خود EXE، فایل SHA-256 و JSON evidence است تا verifier مستقل بتواند artifact، signer و timestamp را کنترل کند.»

## اسلاید ۹ — خط لوله release دارای دفاع در عمق است

«در بازبینی workflow، چند کنترل مشخص را تأیید و تقویت کردیم. تنها tagهای semantic و commit منطبق با tag برای build پذیرفته می‌شوند. environment به نام production-signing نیازمند approval مستقل است و self-review نباید مجاز باشد. actionهای GitHub و Azure اکنون با SHA immutable pin شده‌اند تا tag متحرک action در build بدون تغییر code ما عوض نشود. در پایان، SignTool و Get-AuthenticodeSignature هر دو signature و timestamp را بررسی می‌کنند. اگر timestamp غایب باشد یا signature معتبر نباشد، job fail می‌شود و artifact نباید منتشر گردد.»

## اسلاید ۱۰ — پوشش آزمون از policy تا rollback امتداد دارد

«ارزش کنترل‌ها به testability آن‌هاست. در این پروژه، identity، MFA، RBAC، DPAPI migration و HMAC tamper detection آزموده می‌شوند. در Period Close، self-approval، self-rejection، company scope، MFA منقضی، duplicate request و failure هنگام execution پوشش دارند. در بانک، تست‌ها ثابت می‌کنند که create، revise یا remove روی دوره بسته نمی‌تواند entry قبلی، mapping یا cursor را تغییر دهد. برای Evidence Pack نیز permission، MFA، manifest hash، redaction و block شدن export در زنجیره دستکاری‌شده آزموده شده است. این پوشش به معنای نبودن همه ریسک‌ها نیست، اما مسیر regression برای مهم‌ترین boundaryهای مالی و امنیتی را حفظ می‌کند.»

## اسلاید ۱۱ — اولویت‌های توسعه تجاری بعدی

«پس از v2.6.0، سه محور بیشترین ارزش تجاری را دارند. نخست Reconciliation Workspace است که statement، bank feed و ledger را با workflow exception تطبیق دهد. دوم SIEM/WORM Anchor است که head hash و manifest را به یک مقصد مستقل سازمانی منتقل کند. سوم Approval Policy Builder است تا سقف مبلغ، entity، نقش و قواعد SoD بدون تغییر کد قابل تنظیم شوند. برای شرکت‌های چندملیتی نیز consolidation و FX remeasurement اهمیت بالایی دارد. در این نسخه، Evidence Pack از یک پیشنهاد به قابلیت عملی تبدیل شده است؛ برای دو محور بعدی نیازمند انتخاب سامانه مقصد و policy سازمانی هستیم.»

## اسلاید ۱۲ — تصمیم اجرایی پیشنهادی

«تصمیم کوتاه‌مدت پیشنهادی، تکمیل environment production-signing در Azure، Entra و GitHub و اجرای اولین release امضاشده در staging است. این کار باید با reviewer مستقل، certificate profile آزمایشی و verify روی Windows clean انجام شود. تصمیم میان‌مدت، انتخاب SIEM یا WORM و تعریف retention policy برای manifestهای evidence است. معیار موفقیت ما ساده و قابل اندازه‌گیری است: دوره مالی بدون exception پنهان بسته شود، فایل اجرایی در خارج از محیط build قابل‌راستی‌آزمایی باشد و evidence مورد نیاز حسابرسی از local log فراتر برود. این همان فاصله میان یک قابلیت نرم‌افزاری و یک کنترل سازمانی قابل دفاع است.»

## پرسش‌های محتمل و پاسخ‌های پیشنهادی

| پرسش | پاسخ پیشنهادی |
|---|---|
| آیا DPAPI به‌تنهایی برای audit قانونی کافی است؟ | خیر. DPAPI از key محلی محافظت می‌کند و HMAC تغییر را آشکار می‌سازد، اما برای مقاومت در برابر compromise کامل workstation باید anchor و export evidence به مقصد مستقل داشت. |
| آیا readiness باعث کندی close می‌شود؟ | بررسی‌ها queryهای محلی و verify chain هستند و به‌مراتب کم‌هزینه‌تر از اصلاح close اشتباه‌اند. در شرکت‌های بزرگ، verify می‌تواند به job کنترل‌شده پیش از approval منتقل شود. |
| آیا provider بانک می‌تواند تراکنش دوره بسته را اصلاح کند؟ | provider می‌تواند data را برگرداند، اما FinAnalyzer قبل از void یا post mutation را مسدود می‌کند. اصلاح نیازمند workflow مجاز برای reopen/adjustment خواهد بود. |
| چرا از PFX در GitHub Secret استفاده نمی‌کنیم؟ | OIDC و cloud signing، نگهداری private key در repository و runner را حذف می‌کنند و access token کوتاه‌عمر با scope محدود می‌سازند. |
