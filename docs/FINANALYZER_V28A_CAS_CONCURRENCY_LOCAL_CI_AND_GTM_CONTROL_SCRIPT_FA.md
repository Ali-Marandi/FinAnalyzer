# تست هم‌زمانی CAS، اجرای محلی CI/CD و اسکریپت GTM / گیت‌های v2.8.0-a

**تاریخ مرجع:** ۱۴ اوت ۲۰۲۶
**وضعیت:** specification فنی و راهنمای اجرایی. کنترل‌های تطبیق بانکی v2.7.0 موجودند؛ APIها و مدل‌های CAS/statement reconciliation v2.8.0-a تا زمان پیاده‌سازی، آزمون و UAT، پیشنهادی‌اند.[1] [2]

## ۱. تست هم‌زمانی و مدیریت خطاهای CAS

### ۱.۱. قرارداد رفتار مورد انتظار

در v2.8.0-a، یک `ReconciliationCase` باید یک `version` mutable داشته باشد، در حالی که `ReconciliationDecision` و allocationها append-only باقی می‌مانند. هر command approval، `expected_case_version`، identity actor، policy/snapshot version و idempotency key را حمل می‌کند. transition تنها با conditional update معتبر است:

```sql
UPDATE reconciliation_cases
SET state = :next_state,
    version = :expected_version + 1,
    current_decision_id = :decision_id
WHERE id = :case_id
  AND company_id = :company_id
  AND version = :expected_version
  AND state = :expected_state;
```

اگر `rowcount != 1` باشد، service باید `ConcurrentDecisionConflict` برگرداند؛ نباید request را به‌صورت silent retry یا merge خودکار اجرا کند. UI باید evidence جدید را reload کرده و user را به review دوباره برگرداند. Decision اول immutable می‌ماند و transition موفق دوم هرگز نباید آن را overwrite کند.[2]

| کلاس خطا | علت محتمل | رفتار سرویس | رفتار UX / پایلوت |
|---|---|---|---|
| `ConcurrentDecisionConflict` | expected version یا state قدیمی است | transaction rollback؛ هیچ decision/allocation نیمه‌کاره نماند | evidence reload؛ user دوباره review کند |
| `ActiveAllocationConflict` | resource در case فعال دیگر reserve شده است | rollback و بازگشت target conflict | item را نشان دهید؛ merge خودکار ممنوع |
| Idempotent replay | همان key و همان fingerprint دوباره ارسال شده است | همان result قبلی بازگردد | response ایمن؛ decision دوم ساخته نشود |
| Key reuse mismatch | همان idempotency key با payload دیگر استفاده شده | `IdempotencyKeyReuseError`؛ audit denial/error | client bug یا رفتار مشکوک بررسی شود |
| `40001` / `40P01` | serialization/deadlock در database | کل transaction با session تازه و همان idempotency key، retry محدود شود | در پایان retry budget، conflict قابل‌فهم نمایش دهید |
| authorization/MFA/policy | actor نامعتبر، MFA قدیمی یا policy fail | retry ممنوع؛ deny/error با audit مناسب | user باید identity/policy را اصلاح کند |

### ۱.۲. اصل آزمون هم‌زمانی

تست concurrency واقعی باید از **دو session مستقل روی یک database مشترک** استفاده کند. objectهای cache‌شده در یک SQLAlchemy session، race واقعی را نمی‌سازند. SQLite file-based می‌تواند برای smoke test مفید باشد، اما behavior قفل آن با production-grade PostgreSQL یکسان نیست؛ گیت اصلی v2.8.0-a باید در integration test با engine هدف اجرا شود.[3]

```python
# tests/integration/test_statement_concurrency_v28a.py
# Contract scaffold: پس از پیاده‌سازی service/modelهای v2.8.0-a فعال شود.

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Barrier

import pytest


@dataclass(frozen=True)
class Attempt:
    actor_id: int
    outcome: str
    decision_id: int | None = None
    error_type: str | None = None


def test_only_one_reviewer_can_approve_same_case_version(
    session_factory,
    reconciliation_service,
    seeded_case,
    reviewer_a,
    reviewer_b,
):
    """Exactly one CAS transition may succeed for expected_case_version=7."""
    barrier = Barrier(2)

    def submit(reviewer) -> Attempt:
        # Critical: session lifetime is unique to the thread.
        with session_factory() as session:
            command = seeded_case.command(
                expected_case_version=7,
                idempotency_key=f"case-{seeded_case.id}-{reviewer.user_id}",
            )
            barrier.wait(timeout=10)  # both threads race from the same version
            try:
                outcome = reconciliation_service.approve(
                    session=session,
                    command=command,
                    principal=reviewer,
                )
                session.commit()
                return Attempt(reviewer.user_id, "approved", decision_id=outcome.decision_id)
            except ConcurrentDecisionConflict:
                session.rollback()
                return Attempt(reviewer.user_id, "conflict", error_type="ConcurrentDecisionConflict")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(submit, reviewer_a), executor.submit(submit, reviewer_b)]
        # Submit both calls before waiting. Calling result immediately would serialize the test.
        results = [future.result(timeout=20) for future in futures]

    assert sum(item.outcome == "approved" for item in results) == 1
    assert sum(item.error_type == "ConcurrentDecisionConflict" for item in results) == 1

    with session_factory() as verification_session:
        case = reconciliation_service.get_case(verification_session, seeded_case.id)
        assert case.version == 8
        assert case.current_decision_id is not None
        assert reconciliation_service.active_decision_count(verification_session, case.id) == 1
        assert reconciliation_service.verify_case_audit(verification_session, case.id).valid
```

آزمون بالا باید با سناریوهای تکمیلی پوشش داده شود: replay همان idempotency key؛ policy version تغییرکرده بین load و CAS؛ reservation فعال برای ledger entry مشترک؛ failure injection پس از reservation و پیش از commit؛ و stale statement snapshot پس از provider revision. در هر مورد، assertion باید هم state business، هم audit integrity، هم absence of duplicate decision/allocation و هم no unintended ledger mutation را بررسی کند.

### ۱.۳. الگوی pseudo-code سرویس

```python
def approve(self, *, session, command, principal):
    # 1. Context: principal, MFA freshness, permission and company scope.
    context = self._authorization_context(principal, command.company_id)
    self._require_approval_permission(context)

    # 2. Load fresh state inside the transaction; do not trust UI snapshots.
    case = self._load_case_for_company(session, command.case_id, command.company_id)
    self._assert_command_fingerprint(command)
    self._assert_policy_snapshot(case, command)
    self._assert_business_invariants(session, case, command)

    # 3. Idempotency precedes a new mutation; same key+fingerprint returns prior result.
    replay = self._idempotency_lookup(session, command)
    if replay is not None:
        return replay.result

    # 4. Create immutable candidate decision / allocation in the same transaction.
    decision = self._append_decision(session, case, command, principal)
    self._reserve_active_resources(session, command)  # unique constraints back-stop this

    # 5. Compare-and-swap is the single mutable head transition.
    changed = self._cas_update_case(
        session,
        case_id=case.id,
        expected_version=command.expected_case_version,
        expected_state=case.state,
        next_state="approved",
        decision_id=decision.id,
    )
    if changed != 1:
        raise ConcurrentDecisionConflict(case.id, command.expected_case_version)

    self._audit_success(session, case, decision, principal)
    self._idempotency_complete(session, command, decision)
    return decision
```

در سطح outer transaction، تنها `40001` یا `40P01` retry محدود و با jitter می‌شوند. `ConcurrentDecisionConflict` و `ActiveAllocationConflict` خطاهای business هستند و retry خودکار ندارند. retry هرگز نباید فقط `UPDATE` را تکرار کند؛ باید کل transaction با session جدید و re-read کردن authorization/policy/snapshot از ابتدا اجرا شود.[4]

## ۲. دستورالعمل اجرای محلی CI/CD و گیت‌های امنیتی

### ۲.۱. محیط Windows ایزوله

Build رسمی Windows و DPAPI/signing باید در Windows 11 یا Windows Server ایزوله و با Python 3.12 اجرا شود. PowerShell زیر یک محیط build محلی clean می‌سازد:

```powershell
# از ریشه مخزن FinAnalyzer
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-windows-build.txt
```

اگر execution policy جلوی activate را می‌گیرد، برای همان PowerShell process از `Set-ExecutionPolicy -Scope Process Bypass` استفاده کنید؛ policy سازمانی را دور نزنید. محیط build باید جدا از محیط توسعه روزمره باشد تا dependency snapshot و pip-audit معنی‌دار بمانند.[5] [6]

### ۲.۲. ترتیب اجرای گیت‌های محلی

| مرحله | دستور | evidence / نتیجه مورد انتظار |
|---:|---|---|
| ۱ | `git status --short` | تغییرات آگاهانه و branch صحیح قبل از test |
| ۲ | `python scripts/verify_windows_release.py` | `security-reports/windows-build-dependencies.json` و `pip-audit.json`؛ هیچ dependency blocked یا نسخه پایین‌تر از حد امن وجود ندارد |
| ۳ | `python -m unittest discover -s tests -v` | همه آزمون‌های قابل اجرا Pass؛ skippedها به‌صورت جدا بررسی می‌شوند |
| ۴ | `python build_exe.py` | build_exe گیت dependency را دوباره روی Windows اجرا و `dist/FinAnalyzer_Enterprise_v2_7_0.exe` می‌سازد |
| ۵ | `Get-AuthenticodeSignature .\dist\FinAnalyzer_Enterprise_v2_7_0.exe` | build محلی ممکن است `NotSigned` باشد؛ امضای release فقط در جریان OIDC/Azure production-signing انجام می‌شود |
| ۶ | `git diff --check` و commit/push | whitespace error یا تغییر تصادفی پیش از Pull Request کشف می‌شود |

نمونه کامل PowerShell:

```powershell
# 1) در branch feature کار کنید
 git switch -c feature/v28a-control-gates

# 2) preflight امنیت و test
 python scripts/verify_windows_release.py
 python -m unittest discover -s tests -v

# 3) ساخت EXE؛ روی Windows گیت dependency را خودکار دوباره اجرا می‌کند
 python build_exe.py

# 4) مرور evidence و وضعیت Git
 Get-Content .\security-reports\pip-audit.json
 Get-FileHash .\dist\FinAnalyzer_Enterprise_v2_7_0.exe -Algorithm SHA256
 git diff --check
 git status --short

# 5) Pull Request؛ tag release را فقط پس از عبور گیت CI ایجاد کنید
 git add <files>
 git commit -m "test: add controlled reconciliation gate"
 git push -u origin feature/v28a-control-gates
```

`verify_windows_release.py` در وضعیت فعلی، snapshot وابستگی را تولید می‌کند، حداقل نسخه `wheel` و `pypdf` را enforce می‌کند، `xhtml2pdf` را block می‌کند و `pip-audit --local` را به JSON تبدیل می‌کند. failure این اسکریپت باید release/build را متوقف کند؛ پاک‌کردن گزارش یا skip کردن آن راه‌حل نیست.[6]

### ۲.۳. گیت‌های security و release

| گیت | اجرای محلی | اجرای CI/release | عدم پذیرش |
|---|---|---|---|
| Dependency hygiene | verify script + گزارش pip-audit | پیش از build ویندوز | version ناامن یا package blocked |
| Unit / regression | unittest discover | pre-build signed release | test failure یا skip بدون بررسی کنترل لازم |
| Audit integrity | success/denial/failure و `verify_chain()` | suite کنترل reconciliation | HMAC/sequence/checkpoint نامعتبر |
| SoD / MFA / scope | negative tests با principalهای test | PR control gate و release suite | bypass موفق یا mutation پس از denial |
| Build integrity | build_exe در Windows | PyInstaller build | artifact مورد انتظار وجود ندارد |
| Signing / timestamp | قابل شبیه‌سازی کامل محلی نیست | OIDC/Azure، Authenticode و RFC 3161 verify | signature/timestamp نامعتبر |

برای v2.8.0-a، یک workflow PR جدا باید testهای control را قبل از release tag اجرا کند. release workflow فعلی suite کامل را اجرا می‌کند، اما release tag نباید نخستین محل کشف defect باشد. تنها پس از اینکه testهای v2.8.0-a واقعاً پیاده‌سازی شدند و environment آن‌ها از skip مصون شد، باید به PR gate اجباری افزوده شوند.[5]

## ۳. متن و اسکریپت کامل اسلایدهای Go-to-Market و گیت‌های کنترل v2.8.0-a

### Cover — FinAnalyzer: Go-to-Market کنترل‌محور

**متن روی اسلاید**

FinAnalyzer Enterprise

Go-to-Market برای Evidence-First Close Control

*یک workflow، یک معیار مشترک، یک تصمیم مبتنی بر evidence*

**اسکریپت سخنران**

«مسیر ورود ما به بازار، رقابت برای ساختن یک ERP دیگر نیست. ما از یک مسئله محدود اما پرریسک شروع می‌کنیم: چگونه reconciliation تا Close به تصمیمی policy-bound، قابل پیگیری و قابل دفاع تبدیل شود. Design Partner برای فروش roadmap نیست؛ برای سنجش یک workflow واقعی، با داده حداقلی و معیار موفقیت مشترک است.»

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

```text
CSV Import → Provenance → Exact Match → Immutable Decision → Idempotency → CAS
```

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

Discovery → Charter → Fixture → Technical Gate → Financial UAT → Limited Workflow → Day-90 Decision

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

### اسلاید ۷ — CTA: سه تا پنج شریک، نه یک rollout گسترده

**متن روی اسلاید**

۳–۵ Design Partners

یک workflow محدود · داده حداقلی · معیار مشترک · تصمیم ۹۰روزه

**اسکریپت سخنران**

«درخواست ما rollout گسترده نیست. سه تا پنج شریک با workflow واقعی، champion عملیاتی، حداقل آمادگی داده و مسیر buyer کافی‌اند. در مقابل، ما ERP replacement یا automation بی‌ضابطه وعده نمی‌دهیم. مسیر ما از import کنترل‌شده تا evidence و Close Readiness است؛ اگر evidence ارزش نساخت، توقف می‌کنیم، و اگر ساخت، قرارداد و توسعه مرحله‌ای را با هم پیش می‌بریم.»

## منابع

[1]: /home/ubuntu/FinAnalyzer_User/docs/V2_8_HMAC_AUDIT_RELEASE_GATES_FA.md "HMAC Audit، SoD و گیت‌های کیفیت v2.8.0"

[2]: /home/ubuntu/FinAnalyzer_User/docs/FINANALYZER_V28A_PILOT_GO_NO_GO_UAT_CI_AND_SECURITY_SLIDES_FA.md "پایلوت، UAT/CI و اسلایدهای امنیت v2.8.0-a"

[3]: /home/ubuntu/FinAnalyzer_User/tests/test_bank_reconciliation_v27.py "آزمون‌های Bank Reconciliation v2.7.0"

[4]: https://www.postgresql.org/docs/current/mvcc-serialization-failure-handling.html "PostgreSQL Serialization Failure Handling"

[5]: /home/ubuntu/FinAnalyzer_User/.github/workflows/release-sign.yml "Signed Windows Release workflow"

[6]: /home/ubuntu/FinAnalyzer_User/scripts/verify_windows_release.py "Windows release dependency gate"
