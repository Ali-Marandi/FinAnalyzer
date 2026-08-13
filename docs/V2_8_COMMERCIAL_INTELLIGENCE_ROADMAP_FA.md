# نقشه‌راه تجاری و هوشمند FinAnalyzer Enterprise v2.8.0

## مبنای اولویت‌گذاری

نسخه v2.7.0 جریان **bank-feed review** را امن کرده است، اما هنوز statement خارجی را با دفتر کل certify نمی‌کند. این شکاف، مناسب‌ترین نقطه برای نسخه v2.8.0 است: ابتدا matching قابل‌توضیح و انسان‌محور بین statement و ledger، سپس policy و automation کنترل‌شده. Plaid نیز صراحتاً pending و posted را رویدادهای مستقل می‌داند و اعلام می‌کند که posting، modification و removal باید به‌ترتیب اعمال شوند؛ بنابراین نسخه بعدی باید event-driven، idempotent و محافظه‌کارانه طراحی شود.[1] [2]

> **اصل محصول برای هوش مصنوعی مالی:** مدل می‌تواند پیشنهاد و دلیل تولید کند؛ اما تا پیش از permission، MFA، policy و تأیید انسانی، حق mutation دفتر کل ندارد. این رویکرد با هدف NIST AI RMF برای واردکردن ملاحظات trustworthiness در طراحی، استفاده و ارزیابی سیستم‌های AI هم‌راستاست.[3]

## پیشنهاد اصلی v2.8.0: Statement Reconciliation Intelligence

این قابلیت فایل statement بانک را از CSV و OFX وارد می‌کند، تراکنش‌ها را با Plaid mappingها و journal entryها مقایسه می‌کند و **سه نوع نتیجه** می‌دهد: match قطعی، پیشنهاد match با confidence و exception. confidence باید حاصل قواعد قابل‌توضیح باشد؛ برای نمونه، تطابق شناسه reference، مبلغ در tolerance مجاز، بازه تاریخ و نام merchant. هیچ confidence—even 100%—نباید به‌تنهایی entry را تغییر دهد.

| جزء | قابلیت | کنترل تجاری | شاخص ارزش |
|---|---|---|---|
| Import | CSV/OFX parser و schema validation | quarantine فایل نامعتبر؛ hash و provenance فایل | کاهش ورود دستی statement |
| Deterministic matching | reference ID و مبلغ/ارز دقیق | match بدون AI؛ idempotency key | دقت بالا و audit ساده |
| Explainable suggestion | امتیاز تاریخ، مبلغ، merchant و account | دلیل هر پیشنهاد و threshold policy | کاهش زمان review بدون black box |
| Split matching | یک statement row در برابر چند ledger entry | جمع مبلغ و tolerance با approval سطح بالاتر | پوشش settlementهای تجمیعی |
| Exception aging | queue، owner، SLA و escalation | close blocker پس از آستانه policy | کاهش open itemهای قدیمی |
| Certification | opening + movements + closing balance | controller sign-off و evidence export | آمادگی حسابرسی و close سریع‌تر |

## قابلیت‌های پیشرفته دیگر

| اولویت | قابلیت | شرح تجاری | وابستگی و کنترل |
|---:|---|---|---|
| P0 | Policy-driven reconciliation approvals | آستانه مبلغ، account type، vendor risk و currency برای تعیین maker-checker یا dual approval | مکمل مستقیم v2.7؛ policy version در audit ثبت شود |
| P0 | Optimistic concurrency و decision versioning | جلوگیری از overwrite تصمیم دو reviewer هم‌زمان روی یک mapping | version field، compare-and-swap و conflict UI |
| P1 | Continuous Controls Monitoring | ruleهای روزانه برای duplicate، account غیرمجاز، stale exception و sync failure | alert فقط پس از audit؛ acknowledgement مجزا |
| P1 | Close Calendar و task orchestration | checklist ماهانه، owner، due date، evidence و dependency | اجرای زمان‌بندی‌شده باید approval و notification policy داشته باشد |
| P1 | Cash-flow forecasting با سناریو | forecast rolling مبتنی بر ledger و bank data؛ base/upside/downside | output advisory، نه تصمیم خودکار پرداخت یا سرمایه‌گذاری |
| P2 | Multi-entity consolidation | chart mapping، intercompany elimination و FX translation | مجوز entity-scoped و reconciliation قبل از consolidation |
| P2 | SIEM/WORM evidence anchoring | export manifest هش‌شده به مخزن مستقل یا SIEM | secretless/OIDC، retry idempotent و retention policy |
| P2 | Financial copilot با RAG محلی | پرسش از policy، evidence و report با citation داخلی | read-only پیش‌فرض، redaction و approval برای هر action |

## معماری پیشنهادی v2.8.0

مدل داده باید `BankStatementImport`، `BankStatementLine`، `ReconciliationCandidate` و `ReconciliationDecision` را اضافه کند. هر decision باید immutable history داشته باشد: actor، timestamp، policy version، score features، evidence hash، وضعیت و reviewer مستقل. جدول mapping فعلی باید فقط وضعیت نهایی operational را نگه دارد و history تصمیم‌ها در جدول جداگانه قرار گیرد؛ این کار audit و rollback را قابل‌فهم‌تر می‌کند.

Service پیشنهادی باید از این مرزها پیروی کند:

1. import فایل در transaction جدا و با hash انجام شود؛ فایل خام در UI نمایش داده نشود مگر permission مناسب وجود داشته باشد.
2. candidate generation هیچ mutation مالی انجام ندهد و خروجی explanation تولید کند.
3. acceptance با `bank.reconcile.match`، MFA تازه و policy threshold کنترل شود.
4. high-value، split یا cross-currency decision به reviewer مستقل هدایت شود.
5. close readiness فقط پس از certification statement و حل exceptionهای policy-blocking، وضعیت ready بگیرد.

## برنامه انتشار پیشنهادی

| موج | دامنه | معیار خروج |
|---|---|---|
| v2.8.0-a | import CSV، match قطعی، decision history و optimistic lock | migration، unit/integration tests و evidence audit |
| v2.8.0-b | candidate explanation، split match و approval matrix | precision/recall روی داده demo کنترل‌شده و UAT مالی |
| v2.8.0-c | exception SLA، certification و Close Readiness integration | controller sign-off، export evidence و disaster/rollback test |

## مراجع

[1]: https://plaid.com/docs/transactions/transactions-data/ "Plaid — Transaction states"

[2]: https://plaid.com/docs/api/products/transactions/ "Plaid — Transactions API and incremental sync"

[3]: https://www.nist.gov/itl/ai-risk-management-framework "NIST — AI Risk Management Framework"
