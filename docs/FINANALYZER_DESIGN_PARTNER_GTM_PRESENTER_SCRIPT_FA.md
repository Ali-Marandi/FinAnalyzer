# متن اسلایدها و اسکریپت سخنران

## FinAnalyzer — Design Partner و ورود کنترل‌شده به بازار

**کاربرد:** ارائه به بنیان‌گذار، تیم محصول، controllerهای بالقوه و sponsorهای Design Partner.
**مدت پیشنهادی:** ۱۲ تا ۱۵ دقیقه.
**مرز ادعا:** v2.7.0 منتشر شده است؛ v2.8.0-a یک مسیر release-gated است و نباید قابلیت منتشرشده معرفی شود.

## Cover

**متن روی اسلاید**

FinAnalyzer Enterprise

بسته Design Partner برای Close Control

*از reconciliation پراکنده تا تصمیم قابل دفاع*

**اسکریپت سخنران**

«این ارائه، یک پیشنهاد فروش feature نیست. هدف آن انتخاب شریک‌های طراحی مشترک برای اثبات یک مسئله واقعی است: آیا می‌توان review تطبیق بانکی و Close را به تصمیم‌های policy-bound، قابل پیگیری و قابل دفاع تبدیل کرد؟ ما با یک workflow محدود شروع می‌کنیم، داده حداقلی به‌کار می‌بریم و تنها با evidence تصمیم می‌گیریم که ادامه دهیم، تغییر مسیر دهیم یا متوقف شویم.»

## اسلاید ۱ — مسئله، یک Feed نیست

**متن روی اسلاید**

- Feed جدید ≠ تصمیم مالی تأییدشده
- Close به owner، review مستقل و evidence نیاز دارد
- exception بی‌مالک، ریسک عملیاتی و audit است

**اسکریپت سخنران**

«ورود transaction از بانک یا provider، هیچ‌چیز درباره کامل‌بودن تصمیم مالی نمی‌گوید. controller باید بداند کدام مورد واقعاً review شده، چه کسی مسئول exception است، آیا reviewer مستقل بوده و آیا این item هنوز مانع Close است. ابزارهای accounting روی ثبت و سرعت تمرکز دارند؛ نقطه ورود FinAnalyzer، تبدیل این شکاف کنترلی به workflow قابل اجراست.»

## اسلاید ۲ — جایگاه: Control Layer، نه ERP

**متن روی اسلاید**

| سیستم حسابداری موجود | FinAnalyzer Control Layer | Close قابل دفاع |
|---|---|---|
| Ledger، پرداخت، reporting | policy، SoD، evidence، readiness | تصمیم روشن برای controller |

**اسکریپت سخنران**

«FinAnalyzer قرار نیست ERP، payroll یا payment rail جایگزین کند. ما در کنار سیستم حسابداری موجود می‌نشینیم و برای یک جریان حساس، یعنی reconciliation تا Close، control layer می‌سازیم. این تمرکز عمداً ما را از رقابت پراکنده دور می‌کند و ارزش اولیه را برای controller روشن‌تر می‌سازد: بدانید چه چیزی مانع Close است و چرا.»

## اسلاید ۳ — v2.8.0-a: پایه قابل اعتماد

**متن روی اسلاید**

- CSV statement import + schema validation
- Hash و provenance برای هر import
- match قطعی: reference + amount + currency
- immutable history + idempotency + CAS

**اسکریپت سخنران**

«در موج a، عمداً از AI مبهم یا posting خودکار شروع نمی‌کنیم. ابتدا statement را کنترل‌شده وارد می‌کنیم، منشأ و hash آن را ثبت می‌کنیم، و فقط matchهای قطعی را می‌پذیریم. هر تصمیم history تغییرناپذیر دارد. idempotency جلوی اثر دوباره retry را می‌گیرد و compare-and-swap جلوی overwrite دو reviewer را. این، پایه‌ای است که بعداً Split Matching یا explanation می‌تواند روی آن سوار شود.»

## اسلاید ۴ — گیت فنی، مدرک عملیاتی می‌خواهد

**متن روی اسلاید**

| گیت | evidence پایلوت |
|---|---|
| Import/Provenance | fixture، data map، hash manifest |
| Idempotency/CAS | retry و conflict log |
| No-ledger-mutation | before/after integrity report |
| Audit/SoD | HMAC verification و denial sample |
| Financial UAT | controller sign-off |

**اسکریپت سخنران**

«یک test پاس‌شده برای partner کافی نیست. هر گیت باید evidence عملیاتی داشته باشد: برای import یک data map و manifest، برای retry یک idempotency record، برای concurrency یک conflict log، برای integrity یک before/after report و برای UAT امضای controller. به این ترتیب، مهندسی و عملیات مشتری روی یک definition مشترک از آماده‌بودن توافق می‌کنند.»

## اسلاید ۵ — پایلوت کوچک، کنترل‌شده و قابل توقف

**متن روی اسلاید**

Discovery → Charter & Data Map → Controlled Fixture → Financial UAT → Limited Workflow → 90-Day Decision

**اسکریپت سخنران**

«پایلوت از ورود data شروع نمی‌شود؛ از discovery و charter شروع می‌شود. ابتدا workflow، data classification، role matrix و success measure مشخص می‌شوند. سپس fixture کنترل‌شده، گیت فنی و UAT مالی داریم. فقط بعد از عبور از آن‌ها، یک workflow محدود وارد استفاده واقعی می‌شود. در روز نود، قرارداد یا توسعه feature پیش‌فرض نیست؛ Convert، Extend، Pivot یا Stop با evidence تصمیم‌گیری می‌شود.»

## اسلاید ۶ — چه کسی شریک مناسب است؟

**متن روی اسلاید**

- Controller یا practice lead با close واقعی
- ۲ تا ۱۰ entity، چند bank account یا exception backlog
- Champion با دسترسی به buyer و زمان هفتگی
- data حداقلی و security discovery ممکن

**اسکریپت سخنران**

«شریک مناسب کسی نیست که فقط به AI علاقه دارد. او یک close واقعی، مشکل تکرارشونده و champion عملیاتی دارد. به‌ویژه controller شرکت‌های چندentity یا practice leadهای accounting firm، اگر workflow مشابهی داشته باشند، می‌توانند fit اولیه را نشان دهند. اگر فرد فقط ERP replacement می‌خواهد یا buyer ندارد، باید محترمانه خارج از pilot نگه داشته شود.»

## اسلاید ۷ — ده مصاحبه برای رد یا اثبات فرضیه

**متن روی اسلاید**

| موج گفتگو | سؤال اصلی |
|---|---|
| Controller / Accounting Manager | آخرین Close دشوار کجا شکست؟ |
| CFO / Practice Lead | budget و buyer چه کسی است؟ |
| IT / Security | data، SSO و deployment چه محدودیتی دارد؟ |
| Auditor / Advisor / Partner | چه evidenceی واقعاً قابل دفاع است؟ |

**اسکریپت سخنران**

«ده مصاحبه اول market survey نیست. ما به دنبال الگوی تکرارشونده هستیم. ابتدا controllerهایی را می‌بینیم که نزدیک workflow هستند. بعد CFO یا practice lead را برای economic buyer، IT/security را برای constraint و auditor/advisor را برای evidence requirement وارد می‌کنیم. هر گفت‌وگو باید یک artifact، یک next action و یک score تولید کند. اگر سه گفت‌وگوی نخست workflow مشترک ندهند، feature build متوقف و فرضیه بازنگری می‌شود.»

## اسلاید ۸ — تعامل با Controller: از گذشته، نه از Demo

**متن روی اسلاید**

1. آخرین Close دشوار را بازسازی کنید
2. exception، owner، evidence و approval را دنبال کنید
3. فقط یک concept card نشان دهید
4. یک next action مشخص توافق کنید

**اسکریپت سخنران**

«جلسه را با demo محصول شروع نمی‌کنیم. از controller می‌خواهیم آخرین Close دشوار را قدم‌به‌قدم بازسازی کند. سپس روی یک exception واقعی تمرکز می‌کنیم: چه کسی آن را ساخت، چه کسی حل کرد، evidence کجا بود و چه چیزی نشان می‌داد فرد مستقل است. تنها بعد از فهم workflow، concept card Queue-to-Close را نشان می‌دهیم. هدف نهایی جلسه نیز یک next action روشن است؛ نه یک علاقه‌مندی مبهم.»

## اسلاید ۹ — معیار موفقیت: Evidence، نه Vanity Metrics

**متن روی اسلاید**

| محصول | کنترل | کسب‌وکار |
|---|---|---|
| Time to first controlled value | SoD بدون bypass، HMAC معتبر | paid pilot conversion |
| exception age / ownership | no unintended ledger mutation | buyer و pricing path روشن |
| evidence completeness | UAT controller sign-off | retention در هفته ۸ |

**اسکریپت سخنران**

«موفقیت را با تعداد clicks، تعریف کلی رضایت یا confidence مدل نمی‌سنجیم. ابتدا باید اولین تصمیم policy-bound سریع و قابل‌اعتماد شکل بگیرد. سپس evidence completeness، ownership exception و enforce شدن SoD بررسی می‌شود. در سطح کسب‌وکار، behavior متعهد اهمیت دارد: buyer معرفی می‌شود، داده مناسب اختصاص می‌یابد، security discovery کامل می‌شود و pilot به مسیر تجاری واقعی می‌رسد.»

## اسلاید ۱۰ — تصمیم و CTA

**متن روی اسلاید**

3–5 Design Partners

یک workflow کنترل‌شده، یک معیار موفقیت مشترک، یک تصمیم ۹۰روزه

**اسکریپت سخنران**

«درخواست ما ساده است: سه تا پنج شریک طراحی مشترک که حاضرند یک workflow محدود را با معیار موفقیت مشترک بررسی کنند. در مقابل، ما نه ERP replacement و نه automation بی‌ضابطه وعده می‌دهیم؛ یک مسیر کنترل‌شده از import تا evidence و Close Readiness می‌سازیم. اگر نتیجه ارزش واقعی ایجاد نکرد، پایلوت باید متوقف شود. اگر evidence نشان داد زمان review، ownership یا آمادگی Close بهتر شده است، مسیر قرارداد و توسعه مرحله‌ای روشن خواهد بود.»

## منابع

[1]: /home/ubuntu/FinAnalyzer_User/docs/FINANALYZER_V28A_DESIGN_PARTNER_GATES_AND_INTERVIEW_PLAYBOOK_FA.md

[2]: /home/ubuntu/FinAnalyzer_User/docs/FINANALYZER_DESIGN_PARTNER_PACKAGE_FA.md

[3]: /home/ubuntu/FinAnalyzer_User/docs/FINANALYZER_GLOBAL_PRODUCT_AND_COMMERCIAL_STRATEGY_FA.md
