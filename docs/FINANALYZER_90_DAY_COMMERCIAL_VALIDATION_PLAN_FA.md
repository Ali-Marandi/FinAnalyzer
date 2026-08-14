# برنامه ۹۰ روزه اعتبارسنجی تجاری و اقتصادی FinAnalyzer

**هدف:** اثبات یا رد فرضیه «تیم مالی کنترل‌محور برای evidence-first reconciliation و close control حاضر به پرداخت است» پیش از سرمایه‌گذاری گسترده روی platform، agent یا ERP features.

## ۱. تصمیم‌هایی که باید با داده گرفته شوند

| تصمیم | فرضیه فعلی | داده لازم | معیار تصمیم |
|---|---|---|---|
| Beachhead | controllerهای شرکت‌های ۲ تا ۱۰ entity یا accounting firmها درد شدیدتری دارند | ۱۰–۱۵ مصاحبه ساختاریافته | حداقل ۵ نفر با workflow/درد مشابه و willingness-to-pilot |
| Job اصلی | مشکل، «صرفاً match کردن» نیست؛ close blocker/evidence/exception ownership است | artifactهای واقعی close و گردش کار | تکرار دست‌کم ۳ مشکل با severity بالا |
| Buyer | Controller یا practice lead، champion؛ CFO، economic buyer | org map و approval process | budget owner و procurement path روشن |
| Packaging | close-control product مستقل بهتر از ERP replacement می‌فروشد | demo + objection log | حداقل ۳ تیم جایگاه complementary را معتبر بدانند |
| Price metric | entity/workload بهتر از per-seat است | Van Westendorp سبک + proposal tests | metric قابل‌فهم و متناسب با value پیدا شود |
| Deployment | desktop-first/hybrid برای pilot کافی است | security questionnaire و IT interview | blockerهای deployment و SSO/data residency مستند شوند |

## ۲. Design Partner Charter

هر design partner باید یک charter امضاشده یا دست‌کم email-confirmed داشته باشد که هدف، محدوده و معیار موفقیت را روشن کند.

| بخش | محتوای لازم |
|---|---|
| مسئله | یک close workflow مشخص: bank/statement reconcile، exception یا evidence pack |
| داده | dataset غیرحساس/حداقل‌داده یا محیط کنترل‌شده؛ ممنوعیت استفاده از production data بدون توافق privacy/security |
| baseline | days-to-close، itemهای باز، median review time، aged exceptions، rework و evidence gaps |
| intervention | workflow FinAnalyzer، policy، roles، MFA، human approval و export evidence |
| outcome | بهبود زمان، شفافیت ownership یا evidence quality؛ نه صرفاً رضایت عمومی |
| مدت | ۹۰ روز با checkpoint هفتگی و review در روزهای ۳۰/۶۰/۹۰ |
| commercial path | paid pilot یا conversion criteria، بدون تعهد ارائه capability منتشرنشده |

## ۳. اسکریپت مصاحبه مسئله

مصاحبه باید با workflow واقعی آغاز شود، نه demo محصول. سؤال‌های اصلی:

1. آخرین close که دردناک بود را از اولین bank/statement import تا sign-off شرح دهید.
2. کدام items بیشترین زمان را گرفتند و چه evidenceی برای آنها نگه داشتید؟
3. چه کسی owner بود، چه کسی approval داد و در چه نقطه‌ای SoD یا دسترسی مشکل‌ساز شد؟
4. اگر یک reconciliation اشتباه یا stale باشد، چگونه کشف می‌شود و چه چیزی مانع close می‌شود؟
5. امروز از کدام سیستم‌ها، spreadsheetها و emailها استفاده می‌کنید؟ کدام بخش باید بماند؟
6. در ۱۲ ماه گذشته چه هزینه یا ریسکی از close دیرهنگام، rework یا audit request ایجاد شد؟
7. برای حل این مسئله چه چیزی را قبلاً خریده/ساخته‌اید و چرا کافی نبوده است؟
8. چه کسی budget را تأیید می‌کند و procurement/security review چگونه است؟
9. اگر FinAnalyzer فقط یک workflow را بهتر کند، کدام workflow ارزش pilot دارد؟
10. چه چیزی باعث می‌شود محصول را پس از ۹۰ روز نگه ندارید؟

## ۴. آزمایش قیمت و بسته‌بندی

### گزینه‌های آزمایشی

| گزینه | مشتری هدف | value metric | پیام آزمایشی | ریسک |
|---|---|---|---|---|
| A: Close Control | controller-led company | active controlled entity / close workload | evidence، exception ownership و close readiness | ممکن است پیچیدگی metric زیاد باشد |
| B: Firm Control Workspace | accounting firm | active client entity | standardize client review و evidence | نیازمند multi-client/multi-tenant maturity |
| C: Enterprise Assurance | گروه بزرگ | policy/integration/support scope | SSO، audit export و private deployment | sales cycle و implementation سنگین |

### روش اعتبارسنجی

در هر مصاحبه، ابتدا مسئله و workflow ثبت شود؛ سپس در پایان، سه بسته بدون اعلام «قیمت درست» ارائه و response ثبت شود. برای مشتریان مناسب، proposal واقعی paid pilot فرستاده شود. به‌جای سؤال «چقدر می‌پردازید؟»، این تصمیم‌ها سنجیده شود: آیا champion حاضر است CFO را وارد کند؟ آیا security questionnaire می‌فرستد؟ آیا budget line یا purchase path نشان می‌دهد؟ آیا برای pilot زمان و data اختصاص می‌دهد؟

> نرخ demo request یا تعریف شفاهی «علاقه‌مندم» معیار PMF نیست. رفتار تعهدآور، مانند sharing workflow، معرفی buyer، اجرای pilot یا پذیرش proposal، سیگنال معتبرتر است.

## ۵. Dashboard اقتصاد واحد — داده‌هایی که باید جمع شوند

| شاخص | فرمول | منبع داده | وضعیت پیش از revenue |
|---|---|---|---|
| Qualified discovery rate | interviewهای دارای pain شدید ÷ کل interviews | CRM/research log | قابل اندازه‌گیری |
| Pilot conversion | paid pilots ÷ qualified discovery | proposal tracker | قابل اندازه‌گیری |
| Time to First Controlled Value | زمان signup تا نخستین decision policy-bound | product telemetry | باید instrument شود |
| Pilot activation | accountهای دارای connected workflow و evidence export ÷ pilots | telemetry | باید instrument شود |
| Pilot retention | pilotهای active در هفته ۸ ÷ pilots شروع‌شده | usage log | باید instrument شود |
| ACV | annualized contract value | قرارداد | پس از paid pilot |
| Gross margin | (revenue − connector/hosting/support variable cost) ÷ revenue | finance ledger | پس از paid pilot |
| CAC payback | acquisition spend ÷ monthly gross profit/account | CRM + finance | فقط با داده واقعی |
| Net revenue retention | (opening ARR + expansion − contraction − churn) ÷ opening ARR | billing | بعد از cohort کافی |

## ۶. فرضیه‌های مالی و سناریوها

بدون logo universe، قیمت validated، conversion rate، sales cycle، headcount cost و connector cost، forecast عددی معتبر نیست. بنابراین فقط سه سناریوی قابل‌مدل‌سازی تعریف می‌شوند:

| سناریو | فرض کلیدی | تصمیم اگر مشاهده شد |
|---|---|---|
| محتاطانه | pain موجود است اما paid conversion کم/طولانی | narrow‌تر کردن beachhead یا partner motion؛ feature build محدود |
| پایه | ۲–۳ paid conversion، time-to-value تکرارپذیر و workflow مشابه | سرمایه‌گذاری روی onboarding، v2.8.0-a و case studies |
| تهاجمی | partner channel و demand تکرارشونده، expansion interest | توسعه platform/connector و تیم GTM با budget stage-gated |

مدل بعدی باید با forecast پنج‌ساله، سه scenario و driverهای جداگانه برای accounts، ACV، conversion، churn، gross margin، headcount و sales spend ساخته شود. هیچ رقم ثابت نباید بدون منبع یا assumption register وارد مدل شود.

## ۷. گیت‌های Go / Pivot / Stop

| checkpoint | Go | Pivot | Stop / Pause |
|---|---|---|---|
| روز ۳۰ | pain تکرارشونده و buyer روشن | segment یا job مبهم | مشکل فوری یا buyer واقعی پیدا نشد |
| روز ۶۰ | ۳ design partner active و telemetry معتبر | onboarding یا packaging مشکل دارد | data access/security مانع بنیادی است |
| روز ۹۰ | حداقل ۲ paid conversion یا commitment تجاری معادل | price/segment/channel دوباره طراحی شود | retention/value نامشهود و pilot فاقد champion است |
| v2.8.0-b gate | invariant، SoD، concurrency و UAT مالی پاس | explanation/model threshold بازتنظیم شود | control violation یا evidence integrity failure |

## ۸. مالکیت و cadence

| cadence | جلسه / artifact | مالک پیشنهادی |
|---|---|---|
| هفتگی | pilot health، blockers، telemetry review | Product + Engineering + Customer champion |
| دو هفته یک‌بار | interview synthesis و pricing evidence | Founder/Product |
| ماهانه | roadmap / budget / risk gate | Founder + Finance/Security advisor |
| پایان ۹۰ روز | Go/Pivot/Stop memo | Founder با evidence pack |

## ۹. اقدامات هفت روز آینده

1. یک صفحه landing page با پیام «Close Control Center» و form برای design partner آماده شود.
2. فهرست ۳۰ prospect نخست از controllerها، accounting firmها و advisorهای نزدیک تهیه شود.
3. اسکریپت interview و consent/privacy note نهایی شود.
4. instrumentation eventهای activation، exception، evidence export و Close Readiness طراحی شود.
5. v2.8.0-a را به یک scope قابل demo و acceptance criteria محدود کنید.
6. یک template proposal برای paid pilot و security discovery آماده کنید.

## یادداشت شفافیت

این سند توصیه راهبردی و برنامه اعتبارسنجی است؛ قیمت، conversion، CAC، LTV، revenue و margin در آن پیش‌بینی نشده‌اند، زیرا داده واقعی FinAnalyzer ارائه نشده است. هر مدل مالی بعدی باید بر پایه داده actual و assumption register قابل audit ساخته شود.

## منابع

[1]: /home/ubuntu/FinAnalyzer_User/docs/FINANALYZER_GLOBAL_PRODUCT_AND_COMMERCIAL_STRATEGY_FA.md "راهبرد جهانی محصول و کسب‌وکار FinAnalyzer"

[2]: /home/ubuntu/FinAnalyzer_User/docs/FINANALYZER_ENTITY_CARD.md "کارت موجودیت FinAnalyzer"

[3]: https://www.xero.com/us/accounting-software/reconcile-bank-transactions/ "نمونه pricing/value packaging عمومی Xero — فقط برای مقایسه scope"

[4]: https://www.floqast.com/pricing "بسته‌بندی value-based و quote-based FloQast"
