# Audit Integrity، تست‌های منفی SoD و اسلایدهای GTM / گیت‌های v2.8.0-a

**تاریخ مرجع:** ۱۴ اوت ۲۰۲۶
**وضعیت:** این سند رفتار پیاده‌سازی موجود v2.7.0 را از specification پیشنهادی v2.8.0-a تفکیک می‌کند. HMAC audit و SoD exception موجودند؛ CAS، idempotency و statement reconciliation v2.8.0-a تا زمان پیاده‌سازی و UAT، منتشرشده تلقی نمی‌شوند.[1] [2]

> **حد اعتماد:** زنجیره محلی HMAC تغییر غیرمجاز در محتوا، ترتیب و حذف رویدادها را قابل تشخیص می‌کند، اما جایگزین sink خارجی immutable/WORM نیست؛ اگر مهاجم به database و context کلید DPAPI دسترسی کامل داشته باشد، باید evidence به SIEM یا مخزن تأییدشده سازمان صادر شود.[1]

## ۱. مکانیزم Audit Integrity و `verify_chain`

### ۱.۱. چرخه ثبت رخداد

`AuditLogger.record()` یک event ساختارمند را در transaction فراخواننده ثبت می‌کند. اگر state زنجیره وجود نداشته باشد، `AuditChainState(scope="global")` با `last_sequence=0` و `last_hash=GENESIS_HASH` ایجاد می‌شود؛ `GENESIS_HASH` برابر ۶۴ کاراکتر صفر است. قبل از ثبت، شناسه کلید (`key_id`) زنجیره با کلید در دسترس مقایسه می‌شود تا تغییر خاموش کلید متوقف شود.[1]

| گام | رفتار پیاده‌سازی | اثر کنترلی |
|---:|---|---|
| ۱ | انتخاب/بارگذاری کلید HMAC | در Windows، فایل `.dpapi` با DPAPI محافظت می‌شود؛ در توسعه غیرWindows، فایل با mode 0600 نگهداری می‌شود. |
| ۲ | پاک‌سازی `details` | کلیدهایی مانند `token`، `password`، `client_secret`، `authorization` و `cookie` به‌صورت بازگشتی با `[REDACTED]` جایگزین می‌شوند. |
| ۳ | ساخت payload canonical | event ID، sequence، actor/company/session/request، action، outcome، target، details، timestamp UTC، `previous_hash` و `key_id` در payload قرار می‌گیرند. |
| ۴ | امضای HMAC-SHA256 | JSON با `sort_keys=True` و separator ثابت serialize و با کلید HMAC امضا می‌شود. |
| ۵ | درج event | `previous_hash`، `event_hash` و `key_id` همراه event ذخیره می‌شوند. |
| ۶ | checkpoint | `AuditChainState.last_sequence` و `last_hash` به sequence/hash جدید به‌روز می‌شوند. |

فرمول مفهومی هر رخداد چنین است:

```text
payload_n = CanonicalJSON(
  event_id, sequence_n, action, category, outcome, severity,
  actor/company/session/request, target, redacted_details,
  timestamp_utc, previous_hash=hash_(n-1), key_id
)

hash_n = HMAC-SHA256(audit_signing_key, payload_n)
```

### ۱.۲. الگوریتم `verify_chain`

`verify_chain(session)` تمام eventهای دارای sequence را به ترتیب صعودی می‌خواند و eventهای legacy بدون sequence را فقط جداگانه شمارش می‌کند. سپس از `expected_sequence=1` و `expected_previous=GENESIS_HASH` شروع می‌شود. برای هر event سه کنترل انجام می‌دهد: تداوم sequence، تطابق `previous_hash` و تطابق HMAC با payload بازساخته‌شده. در پایان، hash/sequence آخر با checkpoint موجود در `AuditChainState` مقایسه می‌شود.[1]

```python
expected_previous = GENESIS_HASH
expected_sequence = 1

for event in ordered_events:
    if event.sequence != expected_sequence or event.previous_hash != expected_previous:
        return AuditVerificationResult(False, expected_sequence - 1, legacy, event.sequence,
                                       "Sequence or previous hash mismatch.")

    payload = canonical_payload_from_stored_event(event)
    if not event.event_hash or not hmac.compare_digest(event.event_hash, sign(payload)):
        return AuditVerificationResult(False, expected_sequence - 1, legacy, event.sequence,
                                       "HMAC verification failed.")

    expected_previous = event.event_hash
    expected_sequence += 1

if events and (state is None or state.last_hash != expected_previous
               or state.last_sequence != len(events)):
    return AuditVerificationResult(False, len(events), legacy, None,
                                   "Chain state checkpoint does not match the event chain.")
return AuditVerificationResult(True, len(events), legacy, None, "Audit chain verified.")
```

| دستکاری آزمایشی | نقطه تشخیص | نتیجه مورد انتظار |
|---|---|---|
| تغییر `details`، action یا outcome | HMAC payload بازساخته‌شده | `valid=False` و پیام `HMAC verification failed.` |
| حذف event میانی یا جابه‌جایی ترتیب | sequence و `previous_hash` | `valid=False` و پیام sequence/previous mismatch |
| تغییر checkpoint state | مقایسه انتهایی با `AuditChainState` | `valid=False` و checkpoint mismatch |
| واردکردن secret در details | `_redact()` پیش از signing/persistence | مقدار `[REDACTED]`؛ secret خام در log ساختارمند نیست |
| تغییر کلید بدون rotation مجاز | مقایسه `state.key_id` با key store | `AuditIntegrityError` و توقف ثبت event |

### ۱.۳. مدیریت کلید

`AuditSigningKeyStore` در Windows، کلید ۳۲ بایتی تصادفی را با `WindowsDpapiProtector` محافظت می‌کند و با atomic write فایل `.dpapi` را جایگزین می‌سازد. اگر کلید خام legacy وجود داشته باشد، migration یک‌باره انجام و فایل raw حذف می‌شود. متغیر محیطی `FINANALYZER_AUDIT_HMAC_KEY` فقط در صورت طول حداقل ۳۲ کاراکتر پذیرفته می‌شود. محیط development غیرWindows نباید به production یا evidence store قابل اتکا تبدیل شود.[1]

## ۲. SoD و مدیریت استثنا در لایه سرویس

`BankReconciliationService` لایه UI را منبع کنترل نمی‌داند. در هر عملیات، `AuthenticatedPrincipal` به context شرکتی با `mfa_max_age=15 minutes` تبدیل می‌شود و `AuthorizationService.require()` permission لازم را بررسی می‌کند. mapping فقط از join با `PlaidItem.company_id` بارگذاری می‌شود؛ بنابراین lookup خارج از company scope، event target قابل حدس را افشا نمی‌کند.[2]

| عملیات | پیش‌شرط و کنترل | اثر داده و audit |
|---|---|---|
| `mark_exception()` | `bank.reconcile.match`، MFA معتبر، mapping در company، posted/open/non-pending/non-removed/unlocked و note ۳ تا ۵۰۰ حرف | status=`exception`، flagger و زمان ثبت؛ ledger تغییر نمی‌کند؛ `exception_flagged` ثبت می‌شود |
| `resolve_exception()` | permission مستقل `bank.reconcile.exception.resolve`، MFA معتبر، status=`exception` و reviewer مستقل از flagger | فقط contra line مجاز تغییر می‌کند؛ status=`matched`؛ `matched` ثبت می‌شود |
| self-resolution | `mapping.reconciled_by_user_id == principal.user_id` در status exception | `sod_denied` با outcome=`denied` ثبت و **commit** می‌شود، سپس `BankReconciliationError` raise می‌شود |
| mutation نامعتبر | pending، removed، non-posted، locked period، account نادرست یا ساختار چند-contra | `BankReconciliationError`؛ mutation موفق ایجاد نمی‌شود |

> `sod_denied` عمداً پیش از raise با `session.commit()` پایدار می‌شود، زیرا context manager دیتابیس در وقوع exception عملیات جاری را rollback می‌کند. این commit فقط evidence denial را حفظ می‌کند؛ تغییر حسابداری موفق ایجاد نمی‌کند.[2]

## ۳. نمونه کامل تست‌های منفی SoD و استثنا

کد زیر بر fixture واقعی موجود در `tests/test_bank_reconciliation_v27.py` بنا شده است. آن را در همان class یا در subclass مبتنی بر همان fixture قرار دهید. این نمونه، ledger snapshot، status، audit event و `verify_chain()` را با هم بررسی می‌کند؛ صرفاً انتظار یک exception کافی نیست.[3]

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from core.audit import AuditLog
from core.bank_reconciliation import BankReconciliationError
from core.identity import AuthenticatedPrincipal
from core.models import BankReconciliationStatus, JournalEntry
from tests.test_bank_reconciliation_v27 import BankReconciliationV27Tests


class BankReconciliationNegativeControlTests(BankReconciliationV27Tests):
    """Negative UAT/regression controls using the existing v2.7.0 fixture."""

    def _ledger_snapshot(self) -> tuple[tuple[int, int, str, str], ...]:
        with self.database.get_session() as session:
            mapping = self._mapping(session)
            entry = session.get(JournalEntry, mapping.journal_entry_id)
            return tuple(sorted(
                (line.id, line.account_id, str(line.debit), str(line.credit))
                for line in entry.transactions
            ))

    def _stale_mfa_principal(self) -> AuthenticatedPrincipal:
        now = datetime.now(timezone.utc)
        return AuthenticatedPrincipal(
            user_id=self.manager_id,
            session_id="reconciliation-stale-mfa",
            provider_code="test",
            issuer="https://issuer.example.test",
            subject="subject-stale-mfa",
            authenticated_at=now - timedelta(hours=2),
            expires_at=now + timedelta(hours=1),
            mfa_at=now - timedelta(minutes=16),  # one minute beyond the service limit
        )

    def test_self_resolution_is_denied_and_preserves_ledger_and_audit(self) -> None:
        before = self._ledger_snapshot()
        self.service.mark_exception(
            self.company_id,
            "reconciliation-tx-001",
            "Invoice evidence is incomplete",
            self.manager,
        )

        with self.assertRaisesRegex(BankReconciliationError, "independent reviewer"):
            self.service.resolve_exception(
                self.company_id,
                "reconciliation-tx-001",
                self.expense_account_id,
                self.manager,
                "Attempted self-resolution must fail",
            )

        self.assertEqual(self._ledger_snapshot(), before)
        with self.database.get_session() as session:
            mapping = self._mapping(session)
            denied = session.scalar(select(AuditLog).where(
                AuditLog.action == "bank.reconciliation.sod_denied"
            ))
            self.assertEqual(mapping.reconciliation_status, BankReconciliationStatus.EXCEPTION)
            self.assertIsNotNone(denied)
            self.assertEqual(denied.outcome, "denied")
            self.assertEqual(denied.user_id, self.manager_id)
            self.assertEqual(denied.company_id, self.company_id)
            self.assertTrue(self.audit_logger.verify_chain(session).valid)

    def test_independent_reviewer_resolves_same_exception_after_denial(self) -> None:
        self.service.mark_exception(
            self.company_id,
            "reconciliation-tx-001",
            "Controller review is required",
            self.manager,
        )
        with self.assertRaises(BankReconciliationError):
            self.service.resolve_exception(
                self.company_id,
                "reconciliation-tx-001",
                self.expense_account_id,
                self.manager,
                "Rejected self-resolution",
            )

        self.service.resolve_exception(
            self.company_id,
            "reconciliation-tx-001",
            self.expense_account_id,
            self.controller,
            "Independent controller verified the evidence",
        )
        with self.database.get_session() as session:
            mapping = self._mapping(session)
            self.assertEqual(mapping.reconciliation_status, BankReconciliationStatus.MATCHED)
            self.assertEqual(mapping.reconciled_by_user_id, self.controller_id)
            self.assertTrue(self.audit_logger.verify_chain(session).valid)

    def test_stale_mfa_cannot_flag_exception_or_change_status(self) -> None:
        with self.assertRaises(Exception):  # refine to actual authorization exception after API contract is fixed
            self.service.mark_exception(
                self.company_id,
                "reconciliation-tx-001",
                "A stale MFA session must be denied",
                self._stale_mfa_principal(),
            )
        with self.database.get_session() as session:
            mapping = self._mapping(session)
            self.assertEqual(mapping.reconciliation_status, BankReconciliationStatus.NEEDS_REVIEW)
            self.assertTrue(self.audit_logger.verify_chain(session).valid)
```

برای production suite، `assertRaises(Exception)` در تست MFA باید پس از تثبیت public exception contract به exception دقیق Authorization/Identity تبدیل شود. این احتیاط مانع از پنهان‌شدن `AttributeError`، fixture failure یا خطای غیرکنترلی در پوشش ظاهری test می‌شود. سناریوهای company-scope، pending، removed، locked period و contra-structure نامعتبر نیز باید جداگانه با assertion «بدون mutation + chain معتبر» پوشش داده شوند.[2] [3]

### آزمون دستکاری audit فقط در محیط test

این تست، اثر دستکاری مستقیم database را در یک fixture محلی نشان می‌دهد. هرگز چنین mutationی را در محیط partner یا production اجرا نکنید.

```python
def test_audit_chain_detects_tampered_details(self) -> None:
    self.service.mark_exception(
        self.company_id,
        "reconciliation-tx-001",
        "Audit tamper test fixture",
        self.manager,
    )
    with self.database.get_session() as session:
        event = session.scalar(select(AuditLog).where(
            AuditLog.action == "bank.reconciliation.exception_flagged"
        ))
        event.details = '{"reason_length":999}'  # intentional test-only tamper

    with self.database.get_session() as session:
        result = self.audit_logger.verify_chain(session)
        self.assertFalse(result.valid)
        self.assertEqual(result.first_invalid_sequence, event.sequence)
        self.assertIn("HMAC", result.message)
```

## ۴. اسلایدهای کامل Go-to-Market و گیت‌های کنترل v2.8.0-a

### Cover — FinAnalyzer: Go-to-Market کنترل‌محور

**متن روی اسلاید**

FinAnalyzer Enterprise

Go-to-Market برای Evidence-First Close Control

*یک workflow، یک معیار مشترک، یک تصمیم مبتنی بر evidence*

**اسکریپت سخنران**

«مسیر ورود ما به بازار، رقابت برای ساختن ERP دیگر نیست. ما از یک مسئله محدود اما پرریسک شروع می‌کنیم: چگونه reconciliation تا Close به تصمیمی policy-bound، قابل پیگیری و قابل دفاع تبدیل شود. Design Partner برای فروش roadmap نیست؛ برای سنجش یک workflow واقعی، با داده حداقلی و معیار موفقیت مشترک است.»

### اسلاید ۱ — Beachhead: Controller-led Close

**متن روی اسلاید**

- Controller یا practice lead با Close ماهانه واقعی
- ۲ تا ۱۰ entity، چند حساب بانکی یا exception backlog
- نیاز به owner، reviewer مستقل و evidence
- Control Layer در کنار سیستم حسابداری موجود

**اسکریپت سخنران**

«Beachhead ما controllerهای نزدیک به درد Close هستند، نه هر کسب‌وکاری که به AI علاقه دارد. بهترین fit، شرکتی چندentity یا practiceی است که exception backlog، rework یا evidence gap دارد. ما در کنار ledger و ERP موجود قرار می‌گیریم و سؤال controller را جواب می‌دهیم: چه چیزی هنوز Close را متوقف کرده و چه evidenceی پشت هر تصمیم است؟»

### اسلاید ۲ — v2.8.0-a: ابتدا correctness

**متن روی اسلاید**

`CSV Import → Provenance → Exact Match → Immutable Decision → Idempotency → CAS`

بدون fuzzy match، بدون auto-posting، بدون silent retry

**اسکریپت سخنران**

«موج a عمداً جذابیت ظاهری AI را عقب می‌اندازد. اول باید import، provenance و matching قطعی درست باشند. تصمیم تغییرناپذیر است، retry اثر مضاعف نمی‌سازد و دو reviewer نمی‌توانند یک case را پنهانی overwrite کنند. تا زمانی که این موارد در UAT مالی پاس نشوند، Split Matching و explanation به موج بعد منتقل می‌شوند.»

### اسلاید ۳ — Go فقط با چهار evidence صادر می‌شود

**متن روی اسلاید**

| فنی | امنیت | مالی | بازیابی |
|---|---|---|---|
| import/match/CAS درست | MFA/SoD/HMAC معتبر | controller UAT | rollback owner و incident path |

**اسکریپت سخنران**

«Go از یک dashboard یا یک owner صادر نمی‌شود. evidence فنی نشان می‌دهد workflow درست عمل می‌کند؛ evidence امنیتی نشان می‌دهد identity، scope و audit قابل اتکا هستند؛ evidence مالی یعنی controller outcome را پذیرفته است؛ و evidence بازیابی یعنی اگر چیزی شکست بخورد، owner و مسیر rollback روشن‌اند. نبود هر یک از این چهار مورد، No-Go یا remediation است.»

### اسلاید ۴ — تست منفی، نقطه اثبات کنترل است

**متن روی اسلاید**

1. MFA قدیمی / permission ناکافی → deny
2. company scope نادرست → no exposure
3. self-resolution exception → SoD denial + HMAC
4. period locked / pending / removed → no mutation
5. CAS conflict / retry → یک نتیجه یا conflict، نه overwrite

**اسکریپت سخنران**

«Happy path ارزش عملیاتی را نشان می‌دهد، اما مسیر منفی نشان می‌دهد کنترل واقعاً در service layer اجرا می‌شود. self-resolution باید رد شود و denial حفظ شود؛ period locked نباید reclassification داشته باشد؛ و conflict نباید با retry پنهان یا overwrite حل شود. برای partner، این‌ها فقط test نیستند؛ evidence قابل دفاع برای اعتماد به workflow هستند.»

### اسلاید ۵ — Pilot Operating Model: Stop before Scale

**متن روی اسلاید**

`Discovery → Charter → Fixture → Technical Gate → Financial UAT → Limited Workflow → Day-90 Decision`

**اسکریپت سخنران**

«ما از scale شروع نمی‌کنیم. ابتدا discovery و charter، بعد fixture کنترل‌شده، گیت فنی و UAT مالی. تنها پس از evidence کامل، یک workflow محدود وارد استفاده می‌شود. در روز نود، Convert، Extend، Pivot یا Stop را انتخاب می‌کنیم. توقف در زمان درست، شکست نیست؛ راهی برای جلوگیری از ساخت محصول بر پایه فرض غلط است.»

### اسلاید ۶ — معیار تبدیل، رفتار متعهد است

**متن روی اسلاید**

| Product evidence | Control evidence | Commercial evidence |
|---|---|---|
| زمان تا اولین ارزش کنترل‌شده | SoD بدون bypass و HMAC معتبر | champion، buyer و procurement path |
| owner/aging exception | no unintended ledger mutation | paid pilot behavior |
| completeness evidence | UAT sign-off | retention در هفته ۸ |

**اسکریپت سخنران**

«ما conversion را با تعریف کلی رضایت نمی‌سنجیم. Partner باید یک workflow را واقعاً دنبال کند، controller باید evidence را قابل استفاده بداند و buyer باید مسیر تجاری داشته باشد. اگر تنها مورد اول وجود دارد، محصول شاید مفید باشد اما بازار هنوز تأیید نشده است. اگر تنها مورد سوم وجود دارد، خطر فروش چیزی وجود دارد که کنترل آن اثبات نشده است.»

### اسلاید ۷ — CTA: سه تا پنج شریک، نه rollout گسترده

**متن روی اسلاید**

۳–۵ Design Partners

یک workflow محدود · داده حداقلی · معیار مشترک · تصمیم ۹۰روزه

**اسکریپت سخنران**

«درخواست ما rollout گسترده نیست. سه تا پنج شریک با workflow واقعی، champion عملیاتی، حداقل آمادگی داده و مسیر buyer کافی‌اند. در مقابل، ما ERP replacement یا automation بی‌ضابطه وعده نمی‌دهیم. مسیر ما از import کنترل‌شده تا evidence و Close Readiness است؛ اگر evidence ارزش نساخت، توقف می‌کنیم، و اگر ساخت، قرارداد و توسعه مرحله‌ای را با هم پیش می‌بریم.»

## منابع

[1]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/audit.py "AuditLogger و AuditSigningKeyStore"

[2]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/bank_reconciliation.py "BankReconciliationService v2.7.0"

[3]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/tests/test_bank_reconciliation_v27.py "آزمون‌های Bank Reconciliation v2.7.0"

[4]: /home/ubuntu/FinAnalyzer_User/docs/FINANALYZER_V28A_CAS_CONCURRENCY_LOCAL_CI_AND_GTM_CONTROL_SCRIPT_FA.md "CAS، CI/CD محلی و GTM v2.8.0-a"
