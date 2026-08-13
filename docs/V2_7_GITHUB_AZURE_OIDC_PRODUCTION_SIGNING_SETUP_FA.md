# راه‌اندازی گام‌به‌گام GitHub OIDC و محیط `production-signing` — FinAnalyzer v2.7.0

این راهنما workflow موجود در `.github/workflows/release-sign.yml` را به Azure Artifact Signing و Microsoft Entra متصل می‌کند. پس از تکمیل، اجرای release از یک tag نسخه‌دار، EXE را روی Windows hosted runner می‌سازد، با SHA-256 امضا می‌کند، timestamp RFC 3161 می‌گیرد، signature را verify می‌کند و artifact، hash و evidence را به GitHub Release اضافه می‌کند.

> **امنیت پایه:** از PFX، private key یا password گواهی در GitHub Secret استفاده نکنید. الگوی OIDC، JWT کوتاه‌عمر GitHub را با access token کوتاه‌عمر Entra مبادله می‌کند و نیاز به credential بلندعمر برای CI را برمی‌دارد.[1] [2]

## انتخاب مسیر امضا

| مسیر | محل کلید امضا | مناسب برای | پیچیدگی راه‌اندازی | نکته امنیتی |
|---|---|---|---|---|
| Azure Artifact Signing + GitHub-hosted Windows | سرویس امضای Azure؛ خارج از repository و runner | انتشار عمومی FinAnalyzer | متوسط | **الگوی فعال در workflow فعلی**؛ بدون PFX در CI |
| Signing VM اختصاصی + HSM/certificate store | HSM یا Windows certificate store سازمانی | الزام PKI داخلی یا شبکه ایزوله | زیاد | فقط repository خصوصی، runner group محدود و approval مستقل |

GitHub درباره self-hosted runner هشدار می‌دهد که ممکن است persistent باشد و کد غیرقابل‌اعتماد آن را compromise کند؛ برای repository عمومی تقریباً نباید از آن استفاده شود.[3] مراحل بعدی مسیر اول را راه‌اندازی می‌کنند. مسیر دوم در runbook ایزوله Windows پروژه توضیح داده شده است.

## بخش A — آماده‌سازی Azure Artifact Signing

### گام ۱: ایجاد سرویس امضا

Azure administrator در Azure portal یک **Artifact Signing Account** در region منتخب ایجاد می‌کند، identity validation مورد نیاز را تکمیل می‌کند و یک **Certificate Profile** برای Code Signing می‌سازد. نام account، نام profile و endpoint region را ثبت کنید. endpoint باید دقیقاً با region همان account و profile یکسان باشد؛ ناسازگاری region می‌تواند failure یا 403 ایجاد کند.[4]

| مقدار مورد نیاز | محل ثبت بعدی | نمونه ساختار |
|---|---|---|
| Endpoint | GitHub variable | `https://<region>.codesigning.azure.net/` |
| Signing account name | GitHub variable | `finanalyzer-signing` |
| Certificate profile name | GitHub variable | `finanalyzer-public-release` |
| Timestamp URL | GitHub variable | `http://timestamp.acs.microsoft.com` |

Action رسمی Azure، timestamp RFC 3161 و SHA-256 را پشتیبانی می‌کند. Microsoft برای Artifact Signing مقدار `http://timestamp.acs.microsoft.com` و `SHA256` را پیشنهاد می‌دهد؛ timestamp برای معتبرماندن signature بعد از اعتبار کوتاه certificate profile ضروری است.[4] [5]

### گام ۲: ایجاد identity مخصوص CI

در Microsoft Entra admin center به **App registrations → New registration** بروید. نام پیشنهادی `FinAnalyzer-GitHub-Release-Signing` است. یک tenant کافی است و redirect URI لازم نیست. پس از ایجاد، این سه شناسه را کپی کنید: **Application (client) ID**، **Directory (tenant) ID** و **Subscription ID**.

سپس از **Enterprise applications**، service principal متناظر را پیدا کنید. در scope Certificate Profile، فقط role حداقلی **Artifact Signing Certificate Profile Signer** را به این identity واگذار کنید. به workflow نقش Owner، Contributor یا نقش گسترده Subscription ندهید.[4]

### گام ۳: افزودن Federated Credential

در App Registration به **Certificates & secrets → Federated credentials → Add credential** بروید و provider را **GitHub Actions deploying Azure resources** انتخاب کنید. مقادیر زیر را دقیق وارد کنید.

| فیلد | مقدار |
|---|---|
| Organization | `Ali-Marandi` |
| Repository | `FinAnalyzer` |
| Entity type | `Environment` |
| Environment name | `production-signing` |
| Audience | `api://AzureADTokenExchange` |
| Credential name | `finanalyzer-production-signing` |

Azure باید به subject زیر اعتماد کند:

```text
repo:Ali-Marandi/FinAnalyzer:environment:production-signing
```

`issuer`، `subject` و `audience` در federation باید به‌صورت case-sensitive با claimهای token ارسالی GitHub مطابقت داشته باشند.[2] `id-token: write` در workflow فقط اجازه دریافت OIDC token می‌دهد و به‌تنهایی permission برای تغییر منابع Azure ایجاد نمی‌کند.[1]

## بخش B — سخت‌سازی GitHub Environment

### گام ۴: ایجاد `production-signing`

در repository به **Settings → Environments → New environment** بروید، نام دقیق `production-signing` را وارد و تنظیمات زیر را ذخیره کنید.

| تنظیم | مقدار الزامی | علت |
|---|---|---|
| Required reviewers | حداقل یک Release Manager مستقل | approval انسانی پیش از استفاده از identity امضا |
| Prevent self-review | فعال | شخص آغازکننده release نتواند خودش job را approve کند |
| Allow administrators to bypass | غیرفعال | bypass خارج از فرآیند انتشار نباشد |
| Deployment branches and tags | Selected tags: `v*.*.*` | فقط release tagهای semantic بتوانند امضا شوند |
| Environment URL | آدرس release repository، اختیاری | traceability deployment |

Environment secrets تنها بعد از گذر job از protection rules قابل دسترس می‌شوند.[6] تغییر YAML workflow یا policy environment باید تحت branch protection و review مستقل باشد.

### گام ۵: واردکردن secrets و variables

در همان environment به بخش **Environment secrets** بروید و موارد زیر را وارد کنید. این‌ها identifier هستند، اما برای جلوگیری از enumeration یا misuse به‌صورت secret نگهداری می‌شوند.[7]

| Secret name | مقدار |
|---|---|
| `AZURE_CLIENT_ID` | Application (client) ID از Entra app registration |
| `AZURE_TENANT_ID` | Directory (tenant) ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |

در بخش **Environment variables** موارد زیر را وارد کنید.

| Variable name | مقدار |
|---|---|
| `AZURE_ARTIFACT_SIGNING_ENDPOINT` | endpoint region صحیح account |
| `AZURE_ARTIFACT_SIGNING_ACCOUNT` | نام Artifact Signing Account |
| `AZURE_ARTIFACT_SIGNING_PROFILE` | نام Certificate Profile |
| `RFC3161_TIMESTAMP_URL` | `http://timestamp.acs.microsoft.com` |

هرگز `AZURE_CLIENT_SECRET`، PFX، certificate password یا token بلندعمر را اضافه نکنید. Workflow فقط از OIDC استفاده می‌کند.

## بخش C — اطمینان از تطابق workflow

فایل `.github/workflows/release-sign.yml` پیشاپیش این کنترل‌ها را دارد.

```yaml
permissions:
  contents: write
  id-token: write

jobs:
  build-sign-and-publish:
    runs-on: windows-2022
    environment: production-signing
```

در گام Azure login، workflow سه شناسه Environment secret را به `azure/login` می‌دهد. سپس Azure Artifact Signing action با `file-digest: SHA256` و `timestamp-digest: SHA256` امضا می‌کند. گام verify هم `signtool verify /pa /all /v /tw` و `Get-AuthenticodeSignature` را اجرا می‌کند و نبود timestamp یا signature نامعتبر را fail می‌کند.

> `workflow_dispatch` فقط برای **tag موجود** مجاز است. workflow commit checkout‌شده را با tag مقایسه و فقط tagهای منطبق با `v<major>.<minor>.<patch>` را قبول می‌کند.

## بخش D — نخستین اجرای کنترل‌شده

۱. ابتدا یک profile و environment جداگانه مانند `staging-signing` با certificate profile آزمایشی بسازید؛ environment production را برای آزمون‌های تکراری استفاده نکنید.

۲. پس از عبور تست staging، یک tag immutable واقعی ایجاد کنید؛ مانند `v2.7.0`. این کار باید پس از review تغییرات و build evidence انجام شود.

۳. در repository به **Actions → Signed Windows Release → Run workflow** بروید، tag واقعی را وارد کنید و اجرا را شروع کنید. job در انتظار approval محیط `production-signing` می‌ماند.

۴. Release Manager مستقل workflow را approve می‌کند. پس از پایان موفق، GitHub Release باید این سه asset را داشته باشد: EXE، فایل `.sha256` و `signed-release-evidence.json`.

۵. یک verifier مستقل، فایل را در Windows clean دانلود می‌کند و دستورهای زیر را اجرا می‌کند.

```powershell
Get-FileHash .\FinAnalyzer_Enterprise_v2_7_0.exe -Algorithm SHA256
Get-AuthenticodeSignature .\FinAnalyzer_Enterprise_v2_7_0.exe |
  Format-List Status, SignerCertificate, TimeStamperCertificate
```

hash باید با `.sha256` منتشرشده برابر باشد، `Status` باید `Valid` باشد و `TimeStamperCertificate` نباید خالی باشد.

## بخش E — رفع خطاهای پرتکرار

| علامت | بررسی مرحله‌ای |
|---|---|
| Azure Login failure | سه Environment secret، tenant درست و وجود federated credential را بررسی کنید |
| 403 از Artifact Signing | region endpoint، role `Artifact Signing Certificate Profile Signer` و subject environment را بررسی کنید |
| job قبل از Azure login اجرا می‌شود اما secret خالی است | نام environment باید دقیقاً `production-signing` باشد و approval آن انجام شده باشد |
| OIDC subject mismatch | Organization/repository/environment و حروف بزرگ/کوچک را در Federated Credential کنترل کنید |
| timestamp خالی | مقدار `RFC3161_TIMESTAMP_URL`، خروجی artifact action و `signtool verify /tw` را بررسی کنید؛ artifact fail شده را منتشر نکنید |
| release asset تکراری | workflow از `gh release upload --clobber` استفاده می‌کند؛ hash/evidence جدید را بازبینی و علت اجرای مجدد را ثبت کنید |

## مراجع

[1] [GitHub Docs — Configuring OpenID Connect in Azure](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-azure)

[2] [Microsoft Learn — Workload identity federation concepts](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation)

[3] [GitHub Docs — Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)

[4] [Microsoft Learn — Set up signing integrations to use Artifact Signing](https://learn.microsoft.com/en-us/azure/artifact-signing/how-to-signing-integrations)

[5] [Azure Artifact Signing Action](https://github.com/Azure/artifact-signing-action)

[6] [GitHub Docs — Managing environments for deployment](https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment)

[7] [Microsoft Learn — Azure Login with OpenID Connect](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect)
