# ارزیابی فنی و امنیتی Design Partner و گزارش انطباق UAT v2.8.0-a

**تاریخ مرجع:** ۱۴ اوت ۲۰۲۶
**وضعیت:** راهنمای آمادگی و پذیرش پایلوت؛ نه گواهی انطباق، نه تأیید حسابرسی و نه مجوز ورود به production.
**مرز محصول:** کنترل‌های Bank Reconciliation v2.7.0—از جمله MFA، SoD برای حل exception، HMAC audit و Close Readiness—در محصول موجودند. قابلیت‌های v2.8.0-a شامل CSV statement import، provenance، deterministic matching، immutable decision history، idempotency و optimistic concurrency، هنوز طراحی release-gated هستند و باید پیش از هر استفاده محدود، پیاده‌سازی، آزمون و UAT شوند.[1] [2]

> **اصل حاکم:** مصاحبه Design Partner فروش یا security review کامل نیست. هدف آن کشف workflow واقعی، ارزیابی تناسب پایلوت و ثبت constraints است؛ هیچ داده production، راز، token، credential یا ادعای compliance نباید در جلسه مصاحبه درخواست یا دریافت شود.

## ۱. پیش‌نیاز مشترک برای هر ده مصاحبه

پیش از گفت‌وگو، صاحب جلسه باید یک `Interview Record` بسازد که هدف، نقش مصاحبه‌شونده، hypothesis، consent برای ثبت یادداشت، artefact مجاز، data classification، next action و owner را تعیین می‌کند. تنها artefact حذف‌هویت‌شده یا data fixture تأییدشده می‌تواند بررسی شود. فایل خام بانکی، export عمومی، token، secret، cookie، password، customer PII و identifier حساب نباید از طریق ایمیل، chat یا screen-share وارد چرخه discovery شود.

| کنترل مشترک | روش بررسی در جلسه | evidence قابل ثبت | شرط توقف/ارجاع |
|---|---|---|---|
| Data minimization | توضیح دهید چه artifact حداقلی برای فهم workflow کافی است | data map اولیه با دسته‌بندی حساسیت | درخواست فایل خام، PII یا production data بدون charter |
| مجوز و رضایت | اجازه ثبت خلاصه research را دریافت کنید؛ استفاده case-study را جدا کنید | consent note و owner | عدم رضایت یا ابهام در حقوق استفاده از داده |
| Boundary محصول | Control Layer بودن FinAnalyzer و عدم جایگزینی ERP/claim compliance را شفاف کنید | scope statement در note | انتظار ERP replacement یا autonomous posting |
| هویت و نقش | نقش controller، champion، buyer و IT/security contact را مشخص کنید | stakeholder map | نبود owner یا buyer path برای پایلوت |
| SSO/MFA | فقط requirement را بپرسید؛ هیچ login یا credential درخواست نکنید | requirement list | نیاز خارج از capability/roadmap بدون مسیر تجاری |
| Audit/redaction | توضیح دهید raw provider payload وارد audit نمی‌شود و details redact می‌شوند | evidence expectation | الزام retention/export بدون policy/owner |
| Session safety | شرکت‌کنندگان، فایل‌ها، screen-share و note location را ثبت کنید | session record | حضور فرد غیرمجاز یا داده ناخواسته روی صفحه |

## ۲. سناریوهای ارزیابی فنی و امنیت برای ده مصاحبه اولویت‌دار

این سناریوها در سه سطح اجرا می‌شوند. سطح «Discovery» فقط سؤال و observation است. سطح «Concept» از یک concept card بدون داده حساس استفاده می‌کند. سطح «Fixture» تنها پس از تکمیل Charter، Data Map و Security Discovery با داده مصنوعی یا حذف‌هویت‌شده انجام می‌شود. هیچ سناریوی fixture به‌خودی‌خود production approval نیست.

| اولویت | نقش / فرضیه | سناریوی فنی پیشنهادی | کنترل و چک‌لیست امنیت | evidence خروج و معیار تصمیم |
|---:|---|---|---|---|
| ۱ | Controller چندentity؛ close blocker/evidence gap | بازسازی آخرین Close دشوار از statement تا تصمیم Close؛ تعیین queue، owner و evidence | فقط timeline و checklist حذف‌هویت‌شده؛ company names/money/PII ممنوع | یک workflow مشخص، blocker و baseline زمان/rework؛ در نبود آن، discovery only |
| ۲ | Controller با exception backlog؛ ownership/aging | یک exception گذشته را دنبال کنید: flagger، resolver، owner، SLA و file evidence | عدم نمایش transaction واقعی؛ بررسی نقش‌ها بدون user ID؛ منطق SoD توضیح داده شود | lifecycle map و owner/SLA؛ اگر exceptionها واقعاً ad hoc هستند، fit پایین‌تر |
| ۳ | Accounting Manager؛ rework mismatch | Concept: exact match / mismatch / duplicate reference روی fixture سه‌ردیفی | fixture synthetic؛ رقم و merchant واقعی ممنوع؛ immutable history و no-ledger-mutation توضیح داده شود | expected decision path و دلیل rework؛ policy برای exactness روشن |
| ۴ | Controller کنترل‌محور؛ SoD/MFA/audit | Negative path: همان flagger تلاش می‌کند exception خود را resolve کند | actor test identities، MFA تازه، permission matrix و audit redaction؛ بدون credential واقعی | انتظار `sod_denied`، عدم mutation و evidence HMAC-valid؛ bypass یا ambiguity = no-go |
| ۵ | Controller multi-bank / چندارزی؛ import/provenance | Schema walkthrough برای دو format statement؛ exact amount/currency/reference match | sample format mask‌شده، header/encoding/data owner/retention؛ FX tolerance ممنوع مگر policy آینده | data format feasibility، source owner و mismatch handling؛ اگر source classification نامشخص است، hold |
| ۶ | Practice Lead accounting firm؛ template چندمشتری | Concept: tenant/company scope و role template برای دو client ساختگی | company scope، جداسازی artefact، role template و export boundary؛ بدون cross-client data | partner-edition hypothesis و عدم عبور داده بین clientها؛ scope ambiguity = no-go |
| ۷ | CFO / VP Finance؛ buyer و budget | Walkthrough کوتاه از evidence-to-close و decision memo، نه test مالی | data لازم نیست؛ pricing/contract را وعده قطعی ندهید؛ procurement contacts حداقلی | economic buyer، value metric و procurement path؛ فاقد buyer = discovery only |
| ۸ | IT / Security Lead؛ trust/deployment | Security Discovery: SSO/MFA، device/deployment، backup/restore، export، retention و incident | پرسشنامه، threat assumptions، no secrets، no scan در محیط partner بدون مجوز | requirement list، technical no-go و owner؛ security assessment رسمی جداگانه برنامه‌ریزی شود |
| ۹ | External auditor / advisor؛ evidence defensibility | Request reconstruction: برای یک decision چه actor/policy/evidence لازم است؟ | case/PBC pattern حذف‌هویت‌شده؛ هیچ claim assurance یا compliance certification ندهید | evidence acceptance criteria و missing-evidence taxonomy؛ بازخورد advisory، نه approval محصول |
| ۱۰ | Integration / implementation partner؛ connector reality | بررسی integration boundary و failure/retry behavior با pseudo-flow | API key/endpoint واقعی دریافت نشود؛ idempotency/provenance/error ownership پرسیده شود | dependency map، connector risk و owner؛ dependency بی‌مالک = Later/No-Go |

### چک‌لیست امنیتی مصاحبه‌کننده

| زمان | اقدام الزامی | معیار تکمیل |
|---|---|---|
| پیش از جلسه | invite با عبارت «workflow research، نه sales demo» و منع داده حساس ارسال کنید | participantها و scope مشخص‌اند |
| پیش از screen-share | artefact مجاز و ماسک‌شده را تأیید کنید؛ recording default خاموش باشد | هیچ secret/PII/transaction خام در دستور جلسه نیست |
| حین جلسه | از credential، token، database dump، customer export یا screenshot حاوی PII جلوگیری کنید | facilitator مداخله و summary امن ثبت می‌کند |
| حین concept/fixture | test actorها، company scope، MFA freshness و expected audit event را ثبت کنید | fixture به Data Map و Role/SoD Matrix پیوند دارد |
| پس از جلسه | note را در محل مجاز ذخیره و raw artefact ناخواسته را حذف/ارجاع کنید | assumption log، risk register و next action به‌روز شده‌اند |
| پیش از Pilot Charter | Security Discovery، retention، export، incident contact و backup/restore owner را تکمیل کنید | high-risk/unknown blocker بدون owner باقی نمانده است |

## ۳. گزارش انطباق گیت‌های v2.8.0-a با مدارک UAT مالی

### ۳.۱. مبنای انطباق

UAT مالی باید «درستی مالی و کنترل» را در یک fixture کنترل‌شده اثبات کند، نه اینکه تنها صفحه UI را تأیید کند. هر سناریو باید input، precondition، actor، expected state، expected audit evidence، expected ledger state، evidence location و signatory داشته باشد. نتیجه هر ردیف فقط یکی از `Pass`، `Fail`، `Blocked` یا `Not Run` است. `Blocked` یا `Not Run` برای گیت بحرانی معادل Go نیست.[1] [2]

| گیت v2.8.0-a | سناریوی UAT مالی | انتظار کنترلی | artefact لازم | مسئول پذیرش | وضعیت پذیرش پیشنهادی |
|---|---|---|---|---|---|
| Scope & data classification | Charter و Data Map برای یک workflow بررسی می‌شود | company scope، fields، owner، sensitivity و retention روشن‌اند | charter مصوب، data map، classification record | Controller + Product | پیش‌نیاز UAT؛ بدون آن شروع نشود |
| Import correctness | CSV معتبر، missing header، encoding نادرست، duplicate row و retry اجرا می‌شوند | نتایج قابل پیش‌بینی؛ فایل ناقص وارد تاریخچه تصمیم نمی‌شود | fixture matrix، import test report، rejected-file reason | QA + partner analyst | همه expected resultها Pass |
| Provenance | import موفق و ردشده بررسی می‌شود | actor، زمان، source و hash ثبت شده؛ quarantine/retention مطابق policy است | manifest، hash sample، retention decision | Partner controller | sample قابل بازسازی است |
| Deterministic match | exact match، amount mismatch، currency mismatch و duplicate reference اجرا می‌شوند | فقط reference+amount+currency دقیق match می‌شود؛ مورد مبهم exception یا review می‌ماند | expected-vs-actual matrix، decision evidence | Controller + QA | هیچ fuzzy acceptance وجود ندارد |
| Idempotency | همان import/command دو بار با key برابر ارسال می‌شود | یک result منطقی و بدون linkage/decision مضاعف | request record، single-result assertion، audit sample | Engineering + QA | duplicate side-effect صفر |
| Concurrency / CAS | دو reviewer با نسخه یکسان تلاش approval دارند | دقیقاً یک transition؛ دیگری conflict قابل فهم؛ history حفظ می‌شود | CAS log، conflict capture، decision history | QA + partner reviewer | overwrite موفق وجود ندارد |
| No-ledger-mutation | import/candidate/decision history با baseline ledger مقایسه می‌شود | بدون approved accounting path، مبلغ، تاریخ، line و account ledger تغییر نمی‌کند | before/after integrity report، negative tests | Controller + QA | integrity report بدون اختلاف ناخواسته |
| Audit integrity / SoD | success، denial و failure با test actors اجرا می‌شود | redaction، HMAC verification و actor/company/target درست؛ self-resolution رد می‌شود | `verify_chain()`، audit sample، denial result | Security + QA | chain معتبر و no bypass |
| Migration & restore | روی production-like copy/fixture upgrade، restore و rollback تمرین می‌شود | migration/retry ایمن؛ داده/decision یا audit chain نیمه‌کاره نمی‌ماند | migration log، restore record، rollback runbook | Engineering + partner IT | recovery objective تمرین‌شده |
| Financial UAT sign-off | همه نتایج و موارد باز مرور می‌شوند | controller تأیید می‌کند workflow برای scope پایلوت قابل استفاده است | signed checklist، unresolved list، assumptions | Partner controller | فقط در نبود critical blocker |
| Release governance | Go/No-Go review پیش از workflow محدود اجرا می‌شود | critical/high finding باز نیست؛ incident و rollback owner دارند | release checklist، risk register، go/no-go memo | Release owner + sponsor | تصمیم ثبت‌شده و قابل بازبینی |

### ۳.۲. سازگاری با کنترل‌های موجود v2.7.0

گیت UAT نباید کنترل‌های v2.7.0 را صرفاً فرض کند. در مورد تطبیق بانکی موجود، UAT باید MFA تازه، company-scoped authorization، status precondition، locked-period guard، contra-only mutation و SoD exception resolution را به‌صورت regression جداگانه اجرا کند. به‌ویژه، self-resolution exception باید هیچ mutation حسابداری ایجاد نکند، رویداد `bank.reconciliation.sod_denied` را با outcome `denied` ثبت کند، و زنجیره HMAC پس از denial همچنان معتبر باشد.[2] [3]

| کنترل موجود v2.7.0 | ردیف regression UAT | evidence پذیرش |
|---|---|---|
| MFA + RBAC + company scope | actor فاقد permission، MFA قدیمی و mapping شرکت دیگر را امتحان می‌کند | denial، بدون mutation و audit outcome مناسب |
| SoD exception | flagger می‌خواهد exception خودش را resolve کند؛ reviewer مستقل سپس resolve می‌کند | denial persist می‌شود؛ resolution مستقل با actor صحیح ثبت می‌شود |
| Contra-only | match معتبر و ساختار entry نامعتبر اجرا می‌شوند | تنها account contra مجاز تغییر می‌کند؛ ساختار نامعتبر reject می‌شود |
| Locked period/pending/removed | سناریوهای status و period منع می‌شوند | هیچ decision یا ledger mutation ناخواسته رخ نمی‌دهد |
| HMAC verification | success، failure و denial اجرا و `verify_chain()` خوانده می‌شود | sequence، previous hash و checkpoint معتبرند |

### ۳.۳. قواعد Go/No-Go و مدیریت نقص

| طبقه | مثال | اقدام پیش از workflow محدود |
|---|---|---|
| Critical / No-Go | HMAC نامعتبر، SoD/MFA bypass، mutation ناخواسته ledger، role/company-scope violation، بدون rollback | توقف؛ incident record، علت‌یابی، fix و UAT تکراری |
| High / معمولاً No-Go | import غیرقابل‌پیش‌بینی، idempotency side-effect، CAS overwrite، restore ناموفق یا data handling بدون owner | توقف یا فقط با risk acceptance کتبی و برنامه اصلاح مصوب |
| Medium | UI evidence مبهم یا usability issue که کنترل را bypass نمی‌کند | owner/date؛ در backlog؛ بررسی در Go/No-Go review |
| Low | copy/layout یا بهبود غیرکنترلی | ثبت و اولویت‌بندی بعدی |

هیچ partner یا customer controller نباید صرفاً با یک sign-off کلی، ریسک Critical یا High کنترل‌نشده را بپذیرد. هر exception به release policy باید owner، تاریخ انقضا، جبران‌کننده، دلیل، سطح اختیار و تصمیم ثبت‌شده داشته باشد. این تصمیم، جایگزین رفع نقص یا گواهی امنیت/حسابرسی نیست.

## ۴. اسکریپت کامل سخنران ارائه Design Partner

نسخه کامل و مستقل اسکریپت، شامل متن روی هر ۱۱ اسلاید و گفتار پیشنهادی، در سند زیر نگهداری می‌شود تا از چند منبع متفاوت روایت نشود:

`docs/FINANALYZER_DESIGN_PARTNER_GTM_PRESENTER_SCRIPT_FA.md`

> پیام ثابت در تمام اسلایدها: «ما برای اثبات یک workflow کنترل‌شده آمده‌ایم، نه برای ارائه promise مبهم. v2.7.0 کنترل‌های موجود را نشان می‌دهد؛ v2.8.0-a فقط پس از گیت فنی، evidence و UAT مالی وارد استفاده محدود می‌شود.»

## منابع

[1]: /home/ubuntu/FinAnalyzer_User/docs/FINANALYZER_V28A_DESIGN_PARTNER_GATES_AND_INTERVIEW_PLAYBOOK_FA.md "گیت‌های v2.8.0-a و راهنمای اجرای Design Partner"

[2]: /home/ubuntu/FinAnalyzer_User/docs/V2_8_HMAC_AUDIT_RELEASE_GATES_FA.md "HMAC Audit، SoD و گیت‌های کیفیت v2.8.0"

[3]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/bank_reconciliation.py "BankReconciliationService v2.7.0"

[4]: https://csrc.nist.gov/projects/ssdf "NIST Secure Software Development Framework"
