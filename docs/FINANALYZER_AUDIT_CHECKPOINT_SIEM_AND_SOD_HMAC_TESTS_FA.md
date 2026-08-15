# Audit Log Checkpoint، اتصال SIEM و آزمون‌های ترکیبی SoD/HMAC

**تاریخ مرجع:** ۱۴ اوت ۲۰۲۶
**وضعیت:** شرح پیاده‌سازی AuditLogger و BankReconciliationService موجود در v2.7.0، به‌همراه معماری پیشنهادی برای صادرات SIEM. SIEM exporter، outbox و external anchor در کد فعلی پیاده‌سازی نشده‌اند و باید پس از design review، threat model و آزمون integration ساخته شوند.[1] [2]

> **مرز اعتماد:** زنجیره HMAC داخلی تغییر در محتوای event، ترتیب و حذف آن را قابل تشخیص می‌کند، اما اگر مهاجم هم‌زمان کنترل database و context کلید DPAPI را داشته باشد، تنها یک مقصد خارجی immutable یا SIEM مورد تأیید سازمان می‌تواند anchor مستقل فراهم کند.[1]

## ۱. Checkpoint کنونی Audit Log

`AuditChainState` با `scope="global"` یک checkpoint تک‌نویس برای همه eventهای v2.4+ نگه می‌دارد: `last_sequence`، `last_hash`، `key_id` و `updated_at`. `AuditLog.sequence` و `AuditLog.event_id` یکتا هستند. `AuditLogger.record()` event جدید را با `previous_hash=state.last_hash` ثبت می‌کند، HMAC آن را می‌سازد و سپس checkpoint را به event جدید پیش می‌برد.[1] [3]

```text
AuditChainState قبل از ثبت: (last_sequence=n-1, last_hash=h_(n-1), key_id=k)

payload_n = CanonicalJSON(
  event_id, sequence=n, actor/company/session/request,
  action/category/outcome/severity/source/target,
  redacted_details, timestamp_utc, previous_hash=h_(n-1), key_id=k
)
h_n = HMAC-SHA256(key, payload_n)

AuditLog_n: (sequence=n, previous_hash=h_(n-1), event_hash=h_n)
AuditChainState بعد از ثبت: (last_sequence=n, last_hash=h_n, key_id=k)
```

| جزء | نقش | کنترل موجود |
|---|---|---|
| `AuditLog` | evidence رخداد ساختارمند | `event_id` و `sequence` یکتا؛ payload شامل actor، company، target و outcome است. |
| `previous_hash` | پیوند با event پیشین | حذف یا reorder شدن event میانی را قابل تشخیص می‌کند. |
| `event_hash` | HMAC-SHA256 payload canonical | تغییر action/details/outcome/target/timestamp را قابل تشخیص می‌کند. |
| `AuditChainState` | checkpoint آخرین head | حذف head یا تغییر checkpoint را در پایان verification آشکار می‌کند. |
| `key_id` | شناسه کوتاه SHA-256 کلید | تغییر خاموش کلید را پیش از ثبت event جدید متوقف می‌کند. |
| DPAPI | حفاظت کلید روی Windows | raw key محلی را به context Windows وابسته می‌کند؛ جایگزین SIEM/WORM نیست. |

### ۱.۱. `verify_chain()` به‌ترتیب

`verify_chain()` همه eventهای دارای sequence را به ترتیب صعودی می‌خواند، eventهای legacy بدون sequence را جداگانه گزارش می‌کند و از genesis (`64` صفر) شروع می‌شود. برای هر event، sequence، `previous_hash` و HMAC مجدداً محاسبه می‌شود. سپس head حاصل با checkpoint مقایسه می‌گردد.[1]

| حالت کشف‌شده | پیام نتیجه موجود |
|---|---|
| sequence یا previous hash ناهمخوان | `Sequence or previous hash mismatch.` |
| HMAC بازساخته‌شده ناهمخوان | `HMAC verification failed.` |
| state head با آخرین event ناهمخوان | `Chain state checkpoint does not match the event chain.` |
| همه کنترل‌ها معتبر | `Audit chain verified.` |

### ۱.۲. محدودیت هم‌زمانی و سخت‌سازی پیشنهادی

مدل فعلی checkpoint را **single-writer** توصیف می‌کند؛ `record()` پس از `session.get(AuditChainState, "global")` مقدار head را محاسبه و flush می‌کند. برای scale-out یا database چندنویس، طراحی v2.8+ باید atomicity head را صریح‌تر enforce کند؛ در PostgreSQL، ردیف checkpoint با `SELECT ... FOR UPDATE` یا update شرطی versioned قفل شود و `(scope, sequence)` نیز به‌صورت unique enforce گردد. این hardening پیشنهادی است و نباید به کد فعلی نسبت داده شود.[3]

```python
# پیشنهادی برای PostgreSQL multi-writer؛ جایگزین مستقیم کد موجود نیست.
state = session.execute(
    select(AuditChainState)
    .where(AuditChainState.scope == "global")
    .with_for_update()
).scalar_one()

sequence = state.last_sequence + 1
previous_hash = state.last_hash
# canonical payload + HMAC + AuditLog insert
state.last_sequence = sequence
state.last_hash = event_hash
```

transaction باید کوتاه باشد، call شبکه‌ای در آن انجام نشود و rollback باعث orphan event یا checkpoint جلوتر از eventها نگردد.

## ۲. اتصال SIEM: الگوی توصیه‌شده

دو رویکرد عملی وجود دارد؛ انتخاب نهایی باید با تیم امنیت و زیرساخت Design Partner انجام شود.

| رویکرد | نحوه کار | مزیت | محدودیت / کنترل لازم |
|---|---|---|---|
| Agent/Collector محلی | برنامه event ساختارمند redact‌شده را به file امن یا Windows Event Log می‌نویسد؛ collector سازمان آن را دریافت، normalize و به SIEM می‌فرستد. | تغییر کم در برنامه؛ destination credential داخل FinAnalyzer نیست؛ مدل Collector برای parse/enrich/export مناسب است. | schema ثابت، rotation، ACL فایل و تأیید loss/lag ضروری است. |
| Exporter outbox به collector یا endpoint سازمان | در همان commit event، رکورد outbox ایجاد می‌شود؛ worker جداگانه با mTLS/OAuth سازمانی batch را می‌فرستد و فقط بعد از acknowledgment checkpoint صادرات را پیش می‌برد. | delivery قابل retry و visibility وضعیت export؛ مناسب برای eventهای امنیتی با اولویت بالا. | service پایدار، credential governance، backpressure، replay control و integration test لازم دارد. |

OpenTelemetry برای logهای production schema ساختارمند و Collector را برای دریافت، transform، enrich و export پیشنهاد می‌کند. Collector می‌تواند logهای file را بخواند و logها را به backendهای vendor یا formatهای دیگر صادر کند.[4] [5]

### ۲.۱. قرارداد داده کمینه برای SIEM

SIEM باید **evidence redacted** دریافت کند، نه raw bank payload یا credential. schema پیشنهادی، نام fieldها و انواع داده را ثابت نگه می‌دارد:

```json
{
  "schema_version": "finanalyzer.audit.v1",
  "event_id": "uuid",
  "chain_scope": "global",
  "sequence": 418,
  "timestamp": "2026-08-14T12:00:00+00:00",
  "action": "bank.reconciliation.sod_denied",
  "category": "banking",
  "outcome": "denied",
  "severity": "warning",
  "company_id": 42,
  "actor_id": 17,
  "session_id": "opaque-session-id",
  "request_id": "opaque-request-id",
  "target_type": "plaid_transaction_mapping",
  "target_id": "opaque-or-pseudonymized-provider-id",
  "previous_hash": "…",
  "event_hash": "…",
  "key_id": "…",
  "details": {"reason": "exception_flagger_cannot_resolve"}
}
```

`access_token`، password، cookie، `client_secret`، raw provider payload و PII غیرلازم نباید صادر شوند. `AuditLogger._redact()` بخشی از حفاظت است، اما قرارداد SIEM باید allowlist field داشته باشد؛ به redaction مبتنی بر denylist به‌تنهایی تکیه نکنید.[1]

### ۲.۲. Outbox، acknowledgement و external anchor

برای اینکه failure شبکه سبب loss یا دوباره‌فرستی نامطمئن نشود، event و outbox باید **در همان transaction database** ایجاد شوند. outbox پیشنهادی فیلدهای `event_id`، `sequence`، `event_hash`، `destination_id`، `delivery_state`، `attempt_count`، `next_attempt_at` و `accepted_at` دارد. unique key روی `(destination_id, event_id)` از duplicate delivery محلی جلوگیری می‌کند.

```text
۱. AuditLogger.record() event و head محلی را در transaction ثبت می‌کند.
۲. همان transaction یک OutboxRecord(PENDING, event_id, sequence, event_hash) می‌سازد.
۳. worker خارج از transaction مالی، eventهای PENDING را به‌ترتیب sequence batch می‌کند.
۴. collector/SIEM با TLS سازمانی دریافت و پاسخ acceptance ثبت می‌کند.
۵. worker فقط بعد از پذیرش، outbox را DELIVERED و external checkpoint را تا آخرین sequence پیوسته پیش می‌برد.
۶. lag، شکست دائمی، sequence gap یا hash mismatch alert با owner مشخص ایجاد می‌کند.
```

external checkpoint پیشنهادی برابر `(destination_id, accepted_sequence, accepted_hash, accepted_at, receipt_id)` است. دلیل ذخیره هر دو sequence و hash این است که receipt صرفاً «دریافت شد» را از «دریافت زنجیره درست تا head مشخص» جدا می‌کند. اگر مقصد API دارای receipt قابل اعتماد ندارد، anchor را به write-once evidence store یا collector داخلی منتقل کنید؛ برنامه desktop نباید با retry بی‌پایان تجربه کاربر یا transaction مالی را مسدود کند.

### ۲.۳. حفاظت انتقال و عملیات

| کنترل | الزام پیشنهادی |
|---|---|
| انتقال | TLS با اعتبارسنجی certificate؛ mTLS در صورت پشتیبانی collector سازمانی. |
| credential | secret در DPAPI/secret manager سازمانی؛ scope محدود به ingest؛ rotation و revocation runbook. |
| جداسازی | worker export بیرون از transaction reconciliation؛ failure SIEM نباید تصمیم مالی commit شده را rollback کند. |
| ترتیب | زنجیره global فعلی باید per-scope ترتیبی صادر شود؛ parallel export فقط بین chain scopeهای مستقل مجاز است. |
| retry | bounded exponential backoff با jitter؛ response 4xx policy error به quarantine/alert، نه retry بی‌پایان. |
| مشاهده‌پذیری | delivery lag، oldest pending sequence، failure rate، hash/sequence gap و checkpoint age. |
| retention | retention و residency بر مبنای قرارداد partner و counsel سازمان؛ export صرفاً پس از Data Map approval. |
| incident | outbox backlog، key mismatch یا external checkpoint gap، security incident با owner و escalation path باشد. |

> **انتخاب مسیر:** برای نخستین Design Partner، Agent/Collector محلی کم‌ریسک‌تر است؛ برای rollout enterprise چندtenant یا نیاز به acknowledgement قابل‌ممیزی، outbox/exporter لازم است. هیچ‌کدام نباید بدون threat model، schema review و integration test production-like فعال شوند.

## ۳. تست‌های ترکیبی SoD و HMAC

کلاس `BankReconciliationV27Tests` هم‌اکنون independent resolver و `verify_chain()` را پوشش می‌دهد. نمونه‌های زیر coverage را به «denial پایدار، بدون mutation و زنجیره قابل‌اعتماد» گسترش می‌دهند. آن‌ها از fixture موجود استفاده می‌کنند؛ فایل را به `tests/test_bank_reconciliation_security_v27.py` منتقل کنید یا در همان class قرار دهید.[2] [6]

```python
from __future__ import annotations

from sqlalchemy import select

from core.audit import AuditChainState, AuditLog
from core.bank_reconciliation import BankReconciliationError
from core.models import BankReconciliationStatus, JournalEntry
from tests.test_bank_reconciliation_v27 import BankReconciliationV27Tests


class BankReconciliationSoDAndAuditTests(BankReconciliationV27Tests):
    """Control regression tests; requires the same Plaid test dependency as the v2.7 fixture."""

    def _ledger_snapshot(self):
        with self.database.get_session() as session:
            mapping = self._mapping(session)
            entry = session.get(JournalEntry, mapping.journal_entry_id)
            return tuple(sorted(
                (line.id, line.account_id, str(line.debit), str(line.credit))
                for line in entry.transactions
            ))

    def test_self_resolution_denial_is_committed_and_hmac_linked(self):
        before = self._ledger_snapshot()
        self.service.mark_exception(
            self.company_id,
            "reconciliation-tx-001",
            "Invoice needs independent review",
            self.manager,
        )

        with self.assertRaisesRegex(BankReconciliationError, "independent reviewer"):
            self.service.resolve_exception(
                self.company_id,
                "reconciliation-tx-001",
                self.expense_account_id,
                self.manager,
                "Self-resolution must never be accepted",
            )

        # Evidence commit must survive the business exception; ledger remains unchanged.
        self.assertEqual(before, self._ledger_snapshot())
        with self.database.get_session() as session:
            mapping = self._mapping(session)
            denied = session.scalar(select(AuditLog).where(
                AuditLog.action == "bank.reconciliation.sod_denied"
            ))
            chain = self.audit_logger.verify_chain(session)
            state = session.get(AuditChainState, "global")

            self.assertEqual(mapping.reconciliation_status, BankReconciliationStatus.EXCEPTION)
            self.assertIsNotNone(denied)
            self.assertEqual(denied.outcome, "denied")
            self.assertEqual(denied.user_id, self.manager_id)
            self.assertEqual(denied.company_id, self.company_id)
            self.assertTrue(chain.valid, chain.message)
            self.assertEqual(state.last_sequence, denied.sequence)
            self.assertEqual(state.last_hash, denied.event_hash)

    def test_independent_resolution_extends_same_valid_chain_after_sod_denial(self):
        self.service.mark_exception(
            self.company_id, "reconciliation-tx-001", "Controller review required", self.manager
        )
        with self.assertRaises(BankReconciliationError):
            self.service.resolve_exception(
                self.company_id, "reconciliation-tx-001", self.expense_account_id,
                self.manager, "Rejected self-resolution"
            )

        # Independent reviewer, different actor, continues the audit chain.
        self.service.resolve_exception(
            self.company_id, "reconciliation-tx-001", self.expense_account_id,
            self.controller, "Controller completed independent review"
        )
        with self.database.get_session() as session:
            events = list(session.scalars(select(AuditLog).where(
                AuditLog.action.in_([
                    "bank.reconciliation.exception_flagged",
                    "bank.reconciliation.sod_denied",
                    "bank.reconciliation.matched",
                ])
            ).order_by(AuditLog.sequence)))
            self.assertEqual([event.outcome for event in events], ["success", "denied", "success"])
            self.assertEqual(events[1].user_id, self.manager_id)
            self.assertEqual(events[2].user_id, self.controller_id)
            self.assertEqual(events[1].previous_hash, events[0].event_hash)
            self.assertEqual(events[2].previous_hash, events[1].event_hash)
            self.assertTrue(self.audit_logger.verify_chain(session).valid)

    def test_verify_chain_detects_test_only_event_tamper(self):
        self.service.mark_exception(
            self.company_id, "reconciliation-tx-001", "Tamper-test fixture", self.manager
        )
        with self.database.get_session() as session:
            event = session.scalar(select(AuditLog).where(
                AuditLog.action == "bank.reconciliation.exception_flagged"
            ))
            sequence = event.sequence
            event.details = '{"reason_length":999}'  # Intentional test-only direct database tamper.

        with self.database.get_session() as session:
            result = self.audit_logger.verify_chain(session)
            self.assertFalse(result.valid)
            self.assertEqual(result.first_invalid_sequence, sequence)
            self.assertIn("HMAC", result.message)

    def test_verify_chain_detects_checkpoint_tamper(self):
        self.service.mark_exception(
            self.company_id, "reconciliation-tx-001", "Checkpoint tamper fixture", self.manager
        )
        with self.database.get_session() as session:
            state = session.get(AuditChainState, "global")
            state.last_hash = "f" * 64  # Intentional test-only checkpoint tamper.

        with self.database.get_session() as session:
            result = self.audit_logger.verify_chain(session)
            self.assertFalse(result.valid)
            self.assertIn("checkpoint", result.message.lower())
```

### ۳.۱. CI acceptance matrix

| آزمون | اثبات می‌کند | gate |
|---|---|---|
| self-resolution denial | SoD در service layer، no ledger mutation، denial persistence و checkpoint head | PR/reconciliation regression |
| independent resolution | actor independence و تداوم chain بعد از denial | PR/reconciliation regression |
| event details tamper | HMAC canonical payload integrity | security integration |
| checkpoint tamper | head consistency و failure detection | security integration |
| SIEM outbox loss/retry (آینده) | no event loss، idempotent delivery و external checkpoint monotonicity | staging/integration only |

## ۴. برنامه پیشنهادی پیاده‌سازی SIEM

| مرحله | خروجی | معیار پذیرش |
|---:|---|---|
| ۰ | Data Map، retention/residency، schema allowlist، threat model و destination owner | Design Partner Security approval |
| ۱ | structured file/Windows Event Log emitter و Collector mapping | eventهای SoD/HMAC در SIEM با schema پایدار و بدون secret |
| ۲ | dashboard/alert برای denial، verify failure و export lag | owner و escalation test‌شده |
| ۳ | transactional outbox، receipt و external checkpoint | replay idempotent، gap alert و delivery evidence |
| ۴ | key rotation/anchor drill و incident playbook | exercise موفق بدون خاموش‌کردن integrity gate |

## منابع

[1]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/audit.py "AuditLogger و AuditSigningKeyStore"

[2]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/bank_reconciliation.py "BankReconciliationService v2.7.0"

[3]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/core/models.py "AuditLog و AuditChainState"

[4]: https://opentelemetry.io/docs/concepts/signals/logs/ "OpenTelemetry Logs"

[5]: https://opentelemetry.io/docs/specs/otel/logs/ "OpenTelemetry Logging Specification"

[6]: https://github.com/Ali-Marandi/FinAnalyzer/blob/main/tests/test_bank_reconciliation_v27.py "آزمون‌های Bank Reconciliation v2.7.0"
