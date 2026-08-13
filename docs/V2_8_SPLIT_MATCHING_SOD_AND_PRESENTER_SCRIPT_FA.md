# Split Matching، کنترل‌های SoD و اسکریپت ارائه FinAnalyzer Enterprise v2.8.0

## هدف و وضعیت این سند

این سند، طراحی پیشنهادی برای موج **v2.8.0-b** و اسکریپت سخنران نسخه v2.8.0 را تشریح می‌کند. قابلیت‌های v2.7.0 که در اینجا به آن‌ها ارجاع می‌شود، در سرویس تطبیق بانکی فعلی پیاده‌سازی شده‌اند؛ اما Split Matching، approval matrix و candidate explanation، قابلیت‌های **پیشنهادی** v2.8.0 هستند و نباید پیش از طراحی داده، آزمون، UAT مالی و approval policy به‌عنوان قابلیت منتشرشده معرفی شوند.[1] [2]

> **اصل بنیادین محصول:** موتور هوشمند می‌تواند کاندید، امتیاز و دلیل بسازد؛ اما تا پیش از مجوز، MFA تازه، policy و تأیید انسانی، هیچ حقّی برای mutation دفتر کل ندارد.[1]

## ۱. Split Matching در v2.8.0-b چیست؟

Split Matching حالتی است که **یک ردیف statement بانک** به چند رکورد دفتر کل موجود مرتبط می‌شود؛ برای مثال یک settlement تجمیعی که چند invoice یا entry ثبت‌شده را تسویه می‌کند. در این مدل، سامانه نباید برای «جور کردن مبلغ» سند حسابداری تازه بسازد یا مبلغ entry موجود را تغییر دهد. نتیجه صحیح، ایجاد یک رابطهٔ تطبیق و تصمیم قابل‌ممیزی میان statement line و مجموعه‌ای از ledger entryهای واجد شرایط است.

| اصطلاح | تعریف پیشنهادی | نقش در کنترل |
|---|---|---|
| `BankStatementLine` | ردیف تغییرناپذیر statement واردشده، با شناسه واردات، مبلغ، ارز، تاریخ و hash منشأ | منبع evidence؛ نه محل mutation |
| `ReconciliationCandidate` | گروه پیشنهادی از یک statement line و یک یا چند entry | فقط خروجی rules/AI؛ فاقد اثر مالی |
| `CandidateAllocation` | سهم هر ledger entry از مبلغ statement line | مبنای جمع‌زدن و کنترل عدم‌over-allocation |
| `ReconciliationDecision` | تصمیم immutable برای پذیرش، رد یا exception کردن candidate | ثبت actor، زمان، policy version، evidence hash و reviewer |
| `Certification` | تأیید controller برای توازن opening + movements + closing | پیش‌نیاز Close Readiness در دامنه statement |

به بیان دقیق، split match با **reclassification** فرق دارد. reclassification در v2.7.0 تنها با کنترل contra-only روی یک entry استاندارد انجام می‌شود؛ ولی split match در v2.8.0-b معمولاً یک عملیات certification بین statement و ledger است. اگر واقعاً به اصلاح مبلغ یا ساخت سند تازه نیاز باشد، باید از workflow جداگانه و approved adjustment استفاده شود، نه از مسیر Split Matching.

## ۲. جریان فنی Split Matching

### ۲.۱. تولید candidate، بدون mutation

پس از import یک فایل CSV/OFX و اعتبارسنجی schema، هر `BankStatementLine` با ledger entryهای همان شرکت و حساب بانک مرتبط جست‌وجو می‌شود. موتور ابتدا معیارهای قطعی مانند reference ID، ارز، جهت بدهکار/بستانکار و مبلغ را بررسی می‌کند؛ سپس برای موارد غیرقطعی، ویژگی‌های توضیح‌پذیر مانند فاصله تاریخی، شباهت merchant و الگوی settlement را امتیازدهی می‌کند. خروجی شامل memberهای گروه، allocation پیشنهادی و explanation است؛ نه update دفتر و نه تغییر وضعیت نهایی.[1]

برای حفظ idempotency، کلید منطقی candidate باید دست‌کم شامل `statement_line_id`، مجموعه مرتب‌شده `ledger_entry_id`ها، نسخه آن‌ها و نسخه policy باشد. ایجاد دوباره همان گروه پس از retry نباید تصمیم دوم یا linkage تکراری بسازد.

### ۲.۲. پذیرش، فقط در transaction واحد

هنگام پذیرش، سرویس باید statement line، candidate، allocationها، ledger entryها و decisionهای باز را دوباره از پایگاه داده بارگذاری کند و کنترل‌های زیر را **در یک transaction** اجرا کند. در صورت رد هر کنترل، هیچ allocation یا تصمیم پذیرفته‌شده‌ای ثبت نشود. optimistic concurrency با `decision_version` یا compare-and-swap نیز لازم است تا دو reviewer نتوانند آخرین تصمیم هم را overwrite کنند.[1]

| مرحله | اعتبارسنجی قطعی | نتیجه در صورت شکست |
|---|---|---|
| ۱. دامنه | company، bank account و entity همه یکسان و مجاز باشند | رد با خطای scope؛ ثبت audit denial در موارد حساس |
| ۲. هویت و policy | principal معتبر، MFA تازه، permission مناسب و policy version فعال باشد | عدم ایجاد decision یا allocation |
| ۳. قابلیت تطبیق | statement و همه entryها posted، باز، غیرحذف‌شده و واجد وضعیت مجاز باشند | انتقال به exception یا رد، برحسب علت |
| ۴. یکتایی | statement line و هر ledger entry در decision فعال دیگری نباشند | conflict؛ نمایش مورد به reviewer بدون overwrite |
| ۵. جهت و ارز | sign جریان برابر باشد؛ currency یکسان باشد، مگر policy صریح FX workflow را مجاز بداند | رد/exception؛ cross-currency هرگز تبدیل خودکار ندارد |
| ۶. مبلغ | `sum(allocation.amount)` با مبلغ مطلق statement line برابر باشد؛ tolerance فقط از policy نسخه‌دار و متناسب با ارز خوانده شود | رد با مبلغ اختلاف و توضیح evidence |
| ۷. دقت اعشاری | allocationها مثبت، غیرصفر و در minor-unit ارز quantize شوند؛ جمع آن‌ها از مبلغ entryها تجاوز نکند | رد validation؛ جلوگیری از over/under allocation |
| ۸. تاریخ و evidence | هر entry داخل پنجره تاریخ policy باشد یا override مستدل داشته باشد | approval بالاتر یا exception |
| ۹. SoD | maker، approver و certifier طبق سطح ریسک مستقل باشند | انکار و ثبت رویداد HMAC |
| ۱۰. ثبت نهایی | decision immutable، allocationها و evidence hash با policy version ثبت شوند | rollback کامل transaction |

### ۲.۳. سیاست تحمل اختلاف مبلغ

Tolerance نباید یک عدد ثابت پنهان در کد باشد. policy باید آن را به ترکیبی از **ارز، نوع کارمزد، نوع حساب، دامنه مبلغ و entity** متصل کند و در `ReconciliationDecision` ثبت شود. برای نمونه، اگر policy فقط اختلاف ناشی از کارمزدهای بانکی را مجاز می‌داند، مبلغ اختلاف باید به rule و account مجاز همان policy گره بخورد؛ نه اینکه به‌طور خودکار در یک حساب ناشناخته ثبت شود. اختلافی که با policy پوشش داده نشده است، exception است و close را طبق policy مسدود می‌کند.

### ۲.۴. مرزهای مهم ایمنی

Split Matching نباید به الگوریتمی تبدیل شود که با انتخاب چند entry، هر اختلافی را پنهان کند. در نسخه پیشنهادی، split، cross-currency، tolerance غیرصفر، مبلغ بالا یا vendor پرریسک باید حداقل به **dual approval مستقل** برود. همچنین یک ledger entry نمی‌تواند به‌طور هم‌زمان در دو decision فعال شرکت کند و پذیرش دوباره یک statement line باید idempotent باشد. هر override باید reason، evidence، policy version و زنجیره تأیید مستقل داشته باشد.[1]

## ۳. کنترل‌های SoD و مدیریت استثنا در ماژول فعلی v2.7.0

پیاده‌سازی فعلی در `BankReconciliationService`، تصمیم مجوز را در UI نمی‌پذیرد. تمام عملیات از `AuthenticatedPrincipal`، company scope و `AuthorizationService.require()` عبور می‌کنند. context هر عملیات حساس با حداکثر سن MFA برابر **۱۵ دقیقه** ساخته می‌شود.[2]

| اقدام | وضعیت ورودی مجاز | مجوز لازم | کنترل SoD و نتیجه |
|---|---|---|---|
| مشاهده صف | `needs_review` و `exception`، یا همه وضعیت‌ها برای نمایش resolved | `ledger.read` | صف فقط در company scope خوانده می‌شود و raw provider payload را نمایش نمی‌دهد |
| Flag Exception | مورد باز و mutable، غیرpending، غیرremoved و entry posted در دوره باز | `bank.reconcile.match` | reason باید ۳ تا ۵۰۰ کاراکتر باشد؛ هیچ خط حسابداری تغییر نمی‌کند |
| Match عادی | فقط `needs_review` | `bank.reconcile.match` | MFA تازه، scope، ساختار entry، حساب فعال و contra-only کنترل می‌شود |
| Resolve Exception | فقط `exception` | `bank.reconcile.exception.resolve` | resolver نباید همان exception flagger باشد؛ در غیر این صورت عملیات رد و audit denial ثبت می‌شود |
| بازکردن مجدد مورد matched | مجاز نیست | workflow مستقیم وجود ندارد | نیازمند approved adjustment workflow جداگانه است |
| مورد `pending` یا `removed` | غیرقابل تطبیق | هیچ‌کدام | سرویس پیش از mutation آن را رد می‌کند |
| دوره مالی locked | غیرقابل reclassification | هیچ‌کدام | سرویس پیش از mutation آن را رد می‌کند |

مهم‌ترین کنترل SoD این است که separation فقط نقش‌محور نیست. در `resolve_exception`، حتی اگر یک کاربر هر دو permission را داشته باشد، کد `reconciled_by_user_id` ثبت‌کننده exception را با `principal.user_id` حل‌کننده مقایسه می‌کند. اگر یکسان باشند، رویداد `bank.reconciliation.sod_denied` با outcome=`denied` در HMAC audit chain ثبت و سپس عملیات رد می‌شود. این ثبت عمداً پیش از raise commit می‌شود تا denial در rollback تراکنش گم نشود.[2]

همچنین revision جدید provider، وضعیت تطبیق پیشین را قابل‌اعتماد نمی‌داند: sync، وضعیت را به `needs_review` برمی‌گرداند و note، reviewer و timestamp قبلی را پاک می‌کند. بنابراین یک تأیید قدیمی پس از تغییر provider به‌اشتباه به‌عنوان تأیید فعلی باقی نمی‌ماند.[3]

## ۴. توسعه پیشنهادی SoD برای v2.8.0-b

با ورود split match و مدل‌های پیشنهادی، SoD باید از «flagger در برابر resolver» به تفکیک **سازنده candidate، تصمیم‌گیرنده و certifier** ارتقا یابد. توصیه می‌شود permissionهای جدید جدا از permissionهای فعلی تعریف شوند و هر نقش به کمترین سطح دسترسی لازم محدود بماند.

| سطح | توانمندی پیشنهادی | ممنوعیت مستقل | audit الزامی |
|---|---|---|---|
| Candidate generator | تولید/بازمحاسبه candidate و explanation | پذیرش، override، certification و mutation | مدل/قواعد، featureها، dataset/import hash و زمان اجرا |
| Reviewer / Maker | پذیرش candidate کم‌ریسک در policy | تأیید candidate خودش در موارد dual approval | principal، MFA، candidate version و policy version |
| Independent approver / Checker | تأیید split، high-value، tolerance و cross-currency | تأیید تصمیمی که خود ساخته یا submit کرده است | decision linkage، reason و outcome |
| Controller / Certifier | certification توازن statement و اجازه عبور readiness | ساخت candidate یا تأیید sole همان decision | closing balances، evidence hash و sign-off |
| Exception manager | تعیین owner، SLA و escalation | حل خودکار exception یا دورزدن dual approval | علت، owner، deadline، override و escalation |

برای تبدیل این سیاست به enforcement، `ReconciliationDecision` باید حداقل actorهای `created_by_user_id`، `submitted_by_user_id`، `approved_by_user_id` و `certified_by_user_id` را نگه دارد. در policyهای حساس، هر شناسه باید با شناسه‌های ممنوعه متفاوت باشد و این تفاوت باید در service layer ارزیابی شود، نه در UI. هر change در policy یا override نیز باید به `policy_version` و HMAC evidence chain متصل باشد.

## ۵. اسکریپت سخنران برای معرفی v2.8.0

## Cover

**عنوان:** FinAnalyzer Enterprise v2.8.0 — هوش تطبیق با کنترل انسانی

**زیرعنوان:** Statement Reconciliation Intelligence، Split Matching قابل‌توضیح و Close مبتنی بر evidence

**متن ارائه:**

«v2.7.0 فرآیند review bank feed را کنترل‌پذیر کرد. در v2.8.0 هدف ما برداشتن یک گام دقیق‌تر است: تطبیق statement خارجی بانک با دفتر کل، بدون آن‌که هوش مصنوعی جای مسئولیت مالی و تأیید انسانی را بگیرد. در این نسخه، هر پیشنهاد باید قابل توضیح، قابل بازبینی و قابل ممیزی باشد.»

## Slide 1 — از Bank Feed به Statement Certification

**نکات کلیدی:** CSV/OFX، ارتباط با ledger، گواهی توازن و evidence export.

**متن ارائه:**

«Bank feed برای visibility ارزشمند است، اما برای close سازمانی به certification در سطح statement نیاز داریم. v2.8.0 داده statement را با ledger مقایسه می‌کند، موارد قطعی را سریع‌تر شناسایی می‌کند و موارد غیرقطعی را به صف تصمیم انسانی می‌فرستد. خروجی نهایی فقط یک status نیست؛ evidence آماده برای controller و حسابرس است.»

## Slide 2 — هوش مصنوعی پیشنهاد می‌دهد، دفتر را تغییر نمی‌دهد

**نکات کلیدی:** candidate، confidence قابل‌توضیح، human approval و عدم mutation خودکار.

**متن ارائه:**

«مرز طراحی ما روشن است: مدل می‌تواند match پیشنهاد دهد و توضیح بدهد که چرا reference، مبلغ، تاریخ یا merchant با هم سازگارند. اما حتی confidence بالا هم مجوز تغییر دفتر نیست. permission، MFA، policy و تأیید انسانی همچنان پیش‌شرط پذیرش هستند. به این ترتیب AI زمان review را کم می‌کند، نه اینکه کنترل مالی را دور بزند.»

## Slide 3 — Matching دو لایه: قطعی و قابل‌توضیح

**نکات کلیدی:** reference ID، مبلغ/ارز دقیق، امتیاز تاریخ و merchant، دلیل قابل مشاهده.

**متن ارائه:**

«ابتدا matching قطعی را اجرا می‌کنیم: reference ID، مبلغ و ارز دقیق. این بخش شفاف، قابل تکرار و کم‌ریسک است. سپس فقط برای مواردی که قطعیت کامل ندارند، candidate explanation تولید می‌کنیم. reviewer باید ببیند چه ویژگی‌هایی امتیاز را ساخته‌اند و کدام شرط policy باعث شده تصمیم به approval بالاتر برود.»

## Slide 4 — Split Matching، نه ساخت خودکار سند

**نکات کلیدی:** یک statement line در برابر چند entry، allocation و جمع کنترل‌شده، تصمیم immutable.

**متن ارائه:**

«در settlementهای تجمیعی، یک ردیف statement ممکن است چند entry دفتر را پوشش دهد. Split Matching این رابطه را با allocationهای مشخص ثبت می‌کند؛ اما entry جدید نمی‌سازد و مبلغ entry موجود را تغییر نمی‌دهد. در لحظه پذیرش، سرویس جهت، ارز، مبلغ، یکتایی و محدودیت‌های policy را در یک transaction بررسی می‌کند. اگر اختلاف با policy پوشش داده نشود، مورد exception است، نه یک تطبیق اجباری.»

## Slide 5 — اعتبارسنجی مانع پنهان‌شدن اختلاف می‌شود

**نکات کلیدی:** جمع allocationها، tolerance نسخه‌دار، minor units، idempotency و conflict detection.

**متن ارائه:**

«کیفیت split match به جمع مبلغ خلاصه نمی‌شود. allocationها باید مثبت، دقیق و متناسب با minor unit ارز باشند؛ هیچ entry نباید بیش از مقدار خود allocate شود و هیچ statement line نباید در دو decision فعال قرار بگیرد. tolerance نیز در کد مخفی نیست؛ از policy نسخه‌دار می‌آید و همراه evidence تصمیم ذخیره می‌شود. این کنترل‌ها اجازه نمی‌دهد اختلاف واقعی در یک split ظاهراً متوازن پنهان شود.»

## Slide 6 — SoD از نقش‌ها فراتر می‌رود

**نکات کلیدی:** maker، independent approver و certifier؛ منع self-approval؛ ثبت policy version.

**متن ارائه:**

«در v2.7.0، ثبت‌کننده exception نمی‌تواند خودش آن را resolve کند. v2.8.0 این منطق را توسعه می‌دهد: سازنده candidate، reviewer و certifier در موارد پرریسک باید اشخاص مستقل باشند. این تفکیک نه با دکمه‌های UI، بلکه با actor ID، permission، MFA و policy version در service layer enforce می‌شود. هر denial هم به evidence audit تبدیل می‌شود.»

## Slide 7 — Exceptionها یک صف مدیریت‌شده هستند

**نکات کلیدی:** owner، SLA، escalation، exception aging و close blocker.

**متن ارائه:**

«هدف از exception، کنار گذاشتن یک مسئله نیست؛ هدف، تبدیل آن به کار قابل مالکیت و قابل پیگیری است. هر exception باید دلیل، owner و deadline داشته باشد. موارد قدیمی یا policy-blocking به escalation می‌روند و تا حل یا approval معتبر، مانع Close Readiness می‌مانند. این رویکرد از انباشته‌شدن open itemهای بی‌مالک جلوگیری می‌کند.»

## Slide 8 — Approval متناسب با ریسک است

**نکات کلیدی:** مبلغ بالا، split، ارز خارجی، vendor پرریسک و dual approval.

**متن ارائه:**

«همه تطبیق‌ها ریسک یکسان ندارند. policy می‌تواند مشخص کند که مبلغ بالا، split match، ارز خارجی، tolerance غیرصفر یا vendor پرریسک، independent approval نیاز دارد. بنابراین کنترل، مزاحم همه کارهای روزمره نمی‌شود؛ اما هر جا ریسک بالاتر می‌رود، شواهد و استقلال تصمیم نیز افزایش می‌یابد.»

## Slide 9 — Certification، Close را قابل دفاع می‌کند

**نکات کلیدی:** opening + movements + closing balance، controller sign-off و evidence export.

**متن ارائه:**

«در نقطه پایانی، هدف این است که controller بتواند مسیر از opening balance تا movements و closing balance را با evidence ببیند. close فقط وقتی ready است که statement certification کامل، exceptionهای policy-blocking حل و sign-off لازم ثبت شده باشد. این همان تبدیل تطبیق عملیاتی به کنترل close قابل دفاع است.»

## Slide 10 — برنامه انتشار، کنترل را جلوتر از پیچیدگی نگه می‌دارد

**نکات کلیدی:** v2.8.0-a پایه داده و optimistic lock؛ v2.8.0-b explanation و split؛ v2.8.0-c certification و SLA.

**متن ارائه:**

«دامنه را مرحله‌ای تحویل می‌دهیم. در v2.8.0-a، import، matching قطعی، history تصمیم و هم‌زمانی را تثبیت می‌کنیم. در v2.8.0-b، explanation، split matching و approval matrix را با UAT مالی اضافه می‌کنیم. در v2.8.0-c، certification، SLA و Close Readiness تکمیل می‌شود. این توالی باعث می‌شود ارزش AI بر پایه کنترل و داده واقعی ساخته شود.»

## Slide 11 — تصمیم پیشنهادی

**نکات کلیدی:** تصویب discovery، policy workshop، داده demo کنترل‌شده و UAT مالی.

**متن ارائه:**

«تصمیم پیشنهادی، آغاز discovery برای v2.8.0-a و هم‌زمان تعریف policyهای مبلغ، ارز، tolerance و separation of duties است. سپس برای v2.8.0-b با داده demo کنترل‌شده، precision/recall پیشنهادها و تجربه reviewer را ارزیابی می‌کنیم. معیار موفقیت صرفاً نرخ match نیست؛ قابلیت توضیح، استقلال تصمیم، evidence و آمادگی close نیز بخشی از معیار خروج هستند.»

## منابع

[1]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/docs/V2_8_COMMERCIAL_INTELLIGENCE_ROADMAP_FA.md "نقشه‌راه تجاری و هوشمند FinAnalyzer v2.8.0"

[2]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/bank_reconciliation.py "سرویس BankReconciliationService v2.7.0"

[3]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/docs/V2_7_BANK_RECONCILIATION_CODE_REVIEW_FA.md "بازبینی فنی Bank Reconciliation و کنترل‌های SoD v2.7.0"

[4]: https://plaid.com/docs/transactions/transactions-data/ "Plaid — Transaction states"

[5]: https://www.nist.gov/itl/ai-risk-management-framework "NIST — AI Risk Management Framework"
