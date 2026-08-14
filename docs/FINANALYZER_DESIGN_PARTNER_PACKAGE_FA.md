# بسته اجرایی جذب Design Partner — FinAnalyzer Close Control

## هدف

جذب ۳ تا ۵ design partner برای اعتبارسنجی یک workflow واقعیِ reconciliation و period close. هدف «گرفتن تعریف مثبت» نیست؛ هدف، سنجش درد، دسترسی به workflow، buyer، readiness امنیتی و willingness-to-pay برای Close Control Center است.

## معیار انتخاب شریک

| معیار | نشانه مثبت | دلیل |
|---|---|---|
| نقش | Controller، Head of Finance، Accounting Manager یا practice lead | به close و review واقعی نزدیک است |
| پیچیدگی | دست‌کم دو entity، چند bank account یا close چندمرحله‌ای | مسئله کنترل/evidence نمایان‌تر است |
| ابزار فعلی | accounting system + Excel/email/manual checklist | جایگاه complement قابل آزمون است |
| درد | exceptionهای باز، review زمان‌بر، audit evidence پراکنده یا close دیر | outcome قابل سنجش می‌شود |
| champion | زمان هفتگی، artifact نمونه و دسترسی به buyer را می‌پذیرد | کاهش ریسک pilot نمایشی |
| امنیت | آماده تکمیل security discovery متناسب با داده pilot است | از استفاده ناخواسته از داده حساس جلوگیری می‌کند |

## معیار رد یا تعویق

| وضعیت | تصمیم |
|---|---|
| فقط به دنبال ERP/payroll/payment کامل است | رد؛ خارج از beachhead |
| مشکل close ندارد و صرفاً dashboard می‌خواهد | تعویق؛ value proposition ضعیف |
| انتظار autonomous posting بدون approval دارد | رد؛ خلاف مرز کنترل محصول |
| داده production حساس می‌خواهد بدون توافق privacy/security | رد تا ایجاد محیط و توافق مناسب |
| buyer/champion قابل شناسایی نیست | تعویق؛ احتمال pilot بی‌نتیجه بالا |

## پیام کوتاه اولیه

### Email / LinkedIn اولیه

**موضوع:** آیا review تطبیق بانکی هنوز یک blocker برای Close شماست؟

«سلام [نام]،

ما روی FinAnalyzer کار می‌کنیم؛ یک control layer برای تیم‌های مالی که می‌خواهند bank reconciliation و Close را با ownership، SoD، MFA و evidence قابل‌راستی‌آزمایی پیش ببرند—بدون جایگزین‌کردن ERP یا سیستم حسابداری فعلی.

در حال انتخاب چند design partner برای بررسی یک workflow واقعیِ [bank/statement reconciliation یا exception management] هستیم. هدف این نیست که product demo عمومی نشان دهیم؛ می‌خواهیم بفهمیم کدام بخش Close شما بیشترین rework، تاخیر یا ریسک audit را ایجاد می‌کند و آیا یک workflow کنترل‌شده واقعاً ارزش دارد.

آیا برای یک گفت‌وگوی ۳۰ دقیقه‌ای درباره آخرین Close چالش‌برانگیزتان زمان دارید؟ در صورت تناسب، pilot کنترل‌شده ۹۰روزه با معیار موفقیت مشترک پیشنهاد می‌کنیم.

با احترام،
Ali Marandi
FinAnalyzer»

### Follow-up پس از ۵ روز کاری

«سلام [نام]، فقط برای پیگیری پیام قبلی. اگر bank reconciliation یا evidence Close اکنون اولویت شما نیست، خوشحال می‌شوم بدانم چه workflow دیگری در close بیشترین زمان review را می‌گیرد. همین پاسخ کوتاه نیز برای تحقیق ما ارزشمند است.»

## Landing Page Copy

### Hero

**Close with evidence, not assumptions.**

*FinAnalyzer turns bank-reconciliation and close decisions into policy-bound, reviewable evidence—without replacing your accounting system.*

**CTA:** Apply to the Controlled Close Design Partner Program

### سه outcome

| Outcome | Copy |
|---|---|
| Know what blocks close | See unreconciled items, exceptions, owners, and policy blockers before close approval. |
| Keep the decision boundary controlled | Enforce company scope, permissions, fresh MFA, and separation of duties for sensitive actions. |
| Reconstruct every material decision | Preserve review notes, actors, policy context, and tamper-evident audit evidence. |

### What it is not

FinAnalyzer is not an ERP replacement, payroll system, payment rail, tax-filing solution, or autonomous journal-posting bot. It is a control workflow for reconciliation and close readiness.

## Pilot Success Plan

| روز | فعالیت | evidence خروج |
|---:|---|---|
| ۰–۷ | kickoff، scope، data handling، baseline و role map | signed scope و baseline dashboard |
| ۸–۲۱ | data import/connectivity و policy configuration | first controlled reconciliation + audit verification |
| ۲۲–۴۵ | exception/SoD workflow با review هفتگی | age/owner/decision evidence |
| ۴۶–۷۵ | close-cycle application و evidence pack | Close Readiness و controller feedback |
| ۷۶–۹۰ | outcome review و commercial decision | conversion/pivot/stop memo |

## Scorecard هفتگی

| شاخص | تعریف | هدف pilot |
|---|---|---|
| Time to first controlled value | از kickoff تا اولین decision policy-bound | روند نزولی در cohortهای بعدی |
| Exception ownership | درصد exceptionهای دارای owner/reason | نزدیک به ۱۰۰٪ در scope pilot |
| Evidence completeness | درصد decisionهای دارای required evidence | نزدیک به ۱۰۰٪ |
| Review time | median زمان از needs_review تا decision | بهبود نسبت به baseline؛ مقدار هدف با partner توافق می‌شود |
| SoD enforcement | self-resolutionهای ممنوع که service رد کرده است | هیچ bypass موفقی وجود نداشته باشد |
| Close blockers | items کنترل‌نشده پیش از close | قابل‌مشاهده، owned و قابل explain باشند |

## Security Discovery Checklist

1. چه داده‌ای وارد می‌شود و چه داده‌ای عمداً وارد نمی‌شود؟
2. data controller و owner هر dataset چه کسی است؟
3. آیا pilot با data synthetic، masked یا minimum-necessary قابل اجراست؟
4. الزامات MFA/SSO، logging، retention، region و DPA چیست؟
5. چه فردی security questionnaire را تأیید می‌کند؟
6. response به incident، backup و restore evidence چگونه خواهد بود؟
7. آیا legal/compliance approval پیش از pilot لازم است؟

> هیچ ادعای certification، data residency یا compliance محلی نباید بدون evidence و تأیید حقوقی در proposal یا landing page اضافه شود.

## تصمیم پایان Pilot

| نتیجه | سیگنال | اقدام |
|---|---|---|
| Convert | buyer، value، security و commercial path روشن است | قرارداد سالانه/تمدید pilot و case-study consent |
| Extend with conditions | pain واقعی است ولی integration/onboarding مانع حل‌نشدنی نیست | scope کوچک‌تر، milestone و deadline جدید |
| Pivot | workflow یا buyer با فرض اولیه متفاوت است | update positioning و test مجدد |
| Stop | value/timing/budget یا champion وجود ندارد | توقف محترمانه و ثبت learnings |

## منابع

[1]: /home/ubuntu/FinAnalyzer_User/docs/FINANALYZER_GLOBAL_PRODUCT_AND_COMMERCIAL_STRATEGY_FA.md "راهبرد جهانی محصول و کسب‌وکار"

[2]: /home/ubuntu/FinAnalyzer_User/docs/FINANALYZER_90_DAY_COMMERCIAL_VALIDATION_PLAN_FA.md "برنامه اعتبارسنجی ۹۰ روزه"
