# گیت‌های v2.8.0-a و راهنمای اجرای Design Partner

**تاریخ مرجع:** ۱۴ اوت ۲۰۲۶
**هدف:** اتصال release-gateهای فنی v2.8.0-a به مدارک، تعامل‌ها و معیارهای پذیرش یک پایلوت Design Partner.

## ۱. وضعیت و مرز ادعا

v2.7.0 کنترل‌های Bank Reconciliation، MFA، SoD exception، HMAC audit و Close Readiness را دارد. ویژگی‌های v2.8.0-a—Statement CSV Import، provenance، deterministic statement matching، immutable decision history و optimistic concurrency—هنوز **طراحی/پیشنهاد** هستند. Design Partner نباید آنها را قابلیت منتشرشده یا کنترل انطباقی تأییدشده تلقی کند تا زمانی که پیاده‌سازی، آزمون و UAT انجام شود.[1]

> پایلوت، «فروش promise» نیست؛ یک محیط یادگیری کنترل‌شده است که با داده حداقلی، policy مشخص و evidence قابل بازبینی، ارزش و آمادگی محصول را می‌آزماید.

## ۲. دامنه v2.8.0-a برای پایلوت

| در دامنه | خارج از دامنه |
|---|---|
| CSV statement import با schema validation | OCR، PDF parsing یا هر agent خودمختار |
| hash و provenance هر import | posting خودکار یا journal entry جدید |
| match قطعی روی reference ID + مبلغ/ارز دقیق | fuzzy/AI match و tolerance غیرصریح |
| immutable decision history | update یا overwrite تصمیم پیشین |
| idempotent command و conflict UX | retry پنهان یا merge خودکار conflict |
| controller UAT با fixture یا data حداقلی | production-wide rollout یا claim رگولاتوری |

## ۳. نقشه گیت‌های کنترل به مدارک Design Partner

| گیت فنی | معیار عبور | مدرک/artefact موردنیاز از Partner | evidence خروج FinAnalyzer | مالک تأیید |
|---|---|---|---|---|
| Scope & data classification | یک workflow، company scope و data-minimization روشن | pilot charter، data map، classification و owner | scope record، model/data boundary و change log | Partner controller + Product |
| Import correctness | header، encoding، missing column، duplicate row و retry نتیجه قابل‌پیش‌بینی دارند | نمونه statement mask‌شده و data dictionary | import test report، rejected-file reasons و accepted-file hash | QA + Partner analyst |
| Provenance | actor، زمان، source، hash و retention/quarantine policy ثبت می‌شود | source declaration، retention preference و contact owner | import manifest و provenance sample | Partner controller |
| Deterministic match | فقط reference ID + amount + currency دقیق؛ بدون fuzzy acceptance | fixture شامل exact match، mismatch و duplicate reference | expected-vs-actual matrix و decision sample | Finance controller + QA |
| Idempotency | ارسال دوباره همان command نتیجه دوم نمی‌سازد | network-retry scenario و command request template | duplicate-attempt evidence و single-result assertion | Engineering + QA |
| Concurrency | دو reviewer تنها یک approval/transition موفق می‌گیرند | role matrix و دو reviewer آزمون | conflict capture، CAS test log و UX screenshot | QA + Partner reviewers |
| No-ledger-mutation | import/candidate/history بدون approval مسیر حسابداری را تغییر نمی‌دهد | current ledger snapshot یا synthetic equivalent | before/after integrity report و negative tests | Controller + QA |
| Audit integrity | success/denial/failure پس از redaction HMAC-valid هستند | policy for allowed test actors and test sessions | `verify_chain()` result و event sample | Security + QA |
| Migration & restore | upgrade/rollback روی کپی production-like یا fixture تمرین شده | backup owner، recovery contact و test data approval | migration log، restore test و rollback runbook | Engineering + Partner IT |
| Financial UAT | controller، match/conflict/no-mutation outcome را تأیید می‌کند | named UAT signatory و success criteria | signed UAT checklist و unresolved-item list | Partner controller |
| Release governance | critical/high blocker باز نیست؛ incident/rollback owner مشخص است | escalation contacts و availability window | release checklist، incident path و go/no-go memo | Release owner + Partner sponsor |

### حداقل بسته مستندات پیش از ورود داده

| مدرک | حداقل محتوا | وضعیت لازم |
|---|---|---|
| Pilot Charter | هدف، workflow، زمان، owner، success measures و exit rule | اجباری |
| Data Map | fields، source، sensitivity، data owner، retention و masking | اجباری |
| Role & SoD Matrix | requester، reviewer، controller، IT/security contact و ممنوعیت‌ها | اجباری |
| UAT Fixture Matrix | scenario، input، expected result، evidence و sign-off | اجباری |
| Security Discovery | MFA/SSO، export، backup، incident و privacy questions | اجباری |
| Change Log | version، config/policy change، impact و approver | اجباری |
| Risk Register | risk، likelihood، impact، mitigation و owner | اجباری |
| Commercial Decision Memo | convert/extend/pivot/stop در روز ۹۰ | پیش از پایان pilot |

## ۴. مسیر اجرایی و گیت‌های پایلوت

```text
Discovery → Charter/Data Map → Controlled Fixture → Technical Gate → Financial UAT
         → Limited Workflow Use → Day-30 Review → Day-60 Commercial Check → Day-90 Decision
```

| مرحله | سؤال تصمیم | شرط ورود | شرط خروج |
|---|---|---|---|
| Discovery | آیا pain و buyer واقعی‌اند؟ | Prospect با workflow واقعی | مشکل، champion و scope مشخص |
| Charter | آیا data/policy قابل کنترل است؟ | champion + owner | charter، data map و role matrix تأیید |
| Controlled Fixture | آیا محصول درست رفتار می‌کند؟ | test data امن | import/match/idempotency/concurrency gate پاس |
| Financial UAT | آیا controller به outcome اعتماد دارد؟ | fixture matrix | sign-off یا فهرست defect/assumption |
| Limited Workflow | آیا ارزش در close واقعی قابل مشاهده است؟ | UAT پاس | telemetry و evidence بهبود نسبت به baseline |
| Commercial Review | آیا پایلوت به قرارداد تبدیل می‌شود؟ | حداقل چند هفته usage | buyer، price metric و procurement path روشن |

**No-Go فوری:** HMAC verification نامعتبر، bypass موفق SoD/MFA، mutation ناخواسته ledger، data handling بدون توافق، critical defect بدون rollback یا role/company-scope violation.

## ۵. ده مصاحبه اولویت‌دار

اولین ده گفت‌وگو برای تعمیم آماری نیستند؛ برای رد/تأیید سریع فرضیه beachhead هستند. ترتیب زیر عمداً با controllerهای نزدیک به مشکل شروع می‌شود، نه با مدیرانی که فقط دید کلی دارند.

| اولویت | پروفایل مصاحبه‌شونده | فرضیه‌ای که می‌آزماید | artifact درخواست‌شده | خروج معتبر |
|---:|---|---|---|---|
| ۱ | Controller شرکت ۲–۱۰ entity با close دستی/Excel | close blocker و evidence gap شدید است | close checklist اخیرِ حذف‌هویت‌شده | یک workflow مشخص برای pilot |
| ۲ | Controller با bank/statement exception backlog | ownership/aging مشکل واقعی است | نمونه exception lifecycle | owner/SLA و metric baseline |
| ۳ | Accounting Manager در شرکت رشد سریع | bank feed و ledger/statement mismatch rework می‌سازد | report یا reconciliation pack | علت rework و decision path |
| ۴ | Controller در صنعت کنترل‌محور | SoD/MFA/audit نیاز ملموس دارد | role matrix یا audit request خلاصه | security/compliance buyer map |
| ۵ | Controller چندارزی یا multi-bank | import/provenance و exact match درد واضح دارد | sample statement format | feasibility input/data format |
| ۶ | Practice Lead در accounting/outsourcing firm | template و review چند مشتری ارزش دارد | client close workflow بدون داده حساس | partner-edition hypothesis |
| ۷ | CFO یا VP Finance همان شرکت هدف | economic buyer و budget path مشخص می‌شود | procurement/budget process | buyer, objection و ACV boundary |
| ۸ | Finance Systems / IT Security Lead | deployment، SSO، retention و data constraints روشن می‌شود | security questionnaire | technical no-go / requirements |
| ۹ | External auditor یا controllership advisor | evidence قابل دفاع و audit reconstruction مهم است | anonymized PBC/request pattern | evidence requirements، نه product approval |
| ۱۰ | Integration / implementation partner | channel و connector reality بررسی می‌شود | implementation playbook | partner motion یا dependency risk |

### امتیازدهی پس از هر گفت‌وگو

هر معیار از ۰ تا ۲ امتیاز می‌گیرد. مجموع ۹ یا بیشتر، candidate برای design-partner discussion است؛ کمتر از ۶، discovery فقط برای learning ثبت می‌شود.

| معیار | ۰ | ۱ | ۲ |
|---|---|---|---|
| شدت درد | کلی/نامشخص | درد مقطعی | close/audit/blocker مکرر |
| تکرار workflow | مورد استثنایی | ماهانه ولی متغیر | ماهانه و تکرارپذیر |
| Champion | ندارد | علاقه‌مند اما کم‌وقت | owner با اختیار و وقت |
| Buyer access | نامشخص | مسیر غیرمستقیم | CFO/practice lead قابل معرفی |
| Data readiness | production حساس بدون راهکار | partial/masking مبهم | fixture یا data حداقلی ممکن |
| Fit کنترل | فقط ERP replacement می‌خواهد | کنترل یکی از نیازهاست | evidence/SoD/close readiness ضروری است |

## ۶. سناریوی تعامل ۴۵ دقیقه‌ای با Controller

### پیش از جلسه

ایمیل کوتاه ارسال و درخواست می‌شود که controller صرفاً آخرین close دشوار را به خاطر بیاورد؛ نیازی به آماده‌کردن product feedback یا data حساس نیست. اگر مثال واقعی ممکن نیست، سناریوی anonymized پذیرفته است. هدف جلسه در invitation به‌صورت «workflow research، نه sales demo» اعلام می‌شود.

### دقیقه ۰ تا ۵ — ایجاد چارچوب امن

**گفتار پیشنهادی:**

> «هدف ما امروز فروش یا نمایش roadmap نیست. می‌خواهیم آخرین Close دشوار شما را بازسازی کنیم. لطفاً نام مشتری، مبلغ یا داده حساس را مطرح نکنید. اگر در پایان هم تناسبی نبود، همان نتیجه برای ما مفید است.»

تأیید کنید که اطلاعات برای research محصول ثبت می‌شود و فقط با مجوز قابل استفاده در case study خواهد بود.

### دقیقه ۵ تا ۲۰ — بازسازی Close واقعی

> «از لحظه ورود statement یا bank feed تا لحظه‌ای که CFO یا شما تصمیم گرفتید Close انجام شود، چه اتفاقی افتاد؟ کجا مکث کردید؟ چه چیزی را نتوانستید اثبات کنید؟»

به‌جای پرسش «آیا Split Matching می‌خواهید؟»، از رفتار گذشته بپرسید: چه کسی item را می‌بیند، چه کسی تغییر می‌دهد، evidence کجا می‌رود، و اگر فردی مرخص باشد چه می‌شود.

### دقیقه ۲۰ تا ۳۰ — exception، SoD و evidence

> «یک exception واقعی را انتخاب کنیم. چه کسی آن را ساخت، چه کسی آن را حل کرد، چه چیزی نشان می‌دهد reviewer مستقل بوده، و اگر حسابرس همین امروز سؤال کند، چه فایل‌ها یا emailهایی را پیدا می‌کنید؟»

نقاط اصطکاک، rework، missing evidence، approval ambiguity و frequency را ثبت کنید. هیچ claim compliance یا وعده autonomous posting ندهید.

### دقیقه ۳۰ تا ۳۸ — Concept test کوتاه، نه demo سنگین

یک concept card نشان دهید: Queue → Owner/Reason → Independent Review → Evidence → Close Gate. سپس بپرسید:

> «کدام بخش این جریان با workflow شما ناسازگار است؟ چه چیزی باید قبل از هر استفاده تغییر کند؟ چه کسی می‌گوید این خروجی برای Close کافی است؟»

### دقیقه ۳۸ تا ۴۵ — qualification پایلوت و next step

اگر fit وجود دارد، پیشنهاد Design Partner مطرح شود:

> «برای یک workflow محدود، با data حداقلی و معیار موفقیت مشترک، آیا حاضر هستید یک پایلوت ۹۰روزه را بررسی کنیم؟ برای شما ارزش فقط زمانی ایجاد می‌شود که زمان review، ownership exception یا evidence Close بهبود قابل اندازه‌گیری داشته باشد.»

در پایان، دقیقاً یک next action توافق کنید: ارسال charter، معرفی buyer، جلسه security discovery یا ارسال sample format mask‌شده.

## ۷. ثبت نتایج و تصمیم هفته‌ای

| artifact | پرسش پاسخ‌داده‌شده | owner |
|---|---|---|
| Interview Note | workflow، pain، quote، artifact، score، objection | Product |
| Assumption Log | چه چیزی تأیید/رد/نامشخص شد | Founder/Product |
| Prospect Board | stage، champion، buyer، next action و date | GTM owner |
| Risk Register | data/security/technical/commercial blocker | Engineering + Security |
| Product Decision | Now/Next/Later/Do Not Do update | Product council |

اگر سه گفت‌وگوی اول یک workflow مشترک نشان ندهند، ساخت feature جدید pause می‌شود و segment یا problem definition بازنگری خواهد شد. اگر سه Design Partner با workflow مشابه و buyer روشن دیده شوند، v2.8.0-a به همان workflow محدود می‌شود و هر feature خارج از گیت UAT به Later منتقل می‌گردد.

## منابع

[1]: /home/ubuntu/FinAnalyzer_User/docs/V2_8_HMAC_AUDIT_RELEASE_GATES_FA.md "گیت‌های کیفیت v2.8.0"

[2]: /home/ubuntu/FinAnalyzer_User/docs/FINANALYZER_DESIGN_PARTNER_PACKAGE_FA.md "بسته اجرایی Design Partner"

[3]: /home/ubuntu/FinAnalyzer_User/docs/FINANALYZER_90_DAY_COMMERCIAL_VALIDATION_PLAN_FA.md "برنامه اعتبارسنجی ۹۰روزه"

[4]: /home/ubuntu/FinAnalyzer_User/docs/FINANALYZER_GLOBAL_PRODUCT_AND_COMMERCIAL_STRATEGY_FA.md "راهبرد جهانی محصول و کسب‌وکار"
