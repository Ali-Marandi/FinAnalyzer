# پیکربندی RFC 3161 Timestamping و امضای خودکار EXE در CI/CD — FinAnalyzer v2.5.0

این راهنما پیکربندی workflow افزوده‌شده در `.github/workflows/release-sign.yml` را توضیح می‌دهد. هدف، ساخت artifact از tag تأییدشده، امضای Authenticode با SHA-256، دریافت timestamp RFC 3161، verify مستقل در همان job و انتشار EXE به‌همراه hash و evidence است.

> **اصل طراحی:** private key Code Signing نباید در repository، GitHub Secret، محیط build یا فایل PFX قابل‌دانلود قرار بگیرد. الگوی پیش‌فرض این پروژه از GitHub-hosted Windows runner، Azure Artifact Signing و GitHub OIDC استفاده می‌کند تا CI فقط یک access token کوتاه‌عمر بگیرد.[1] [2]

## معماری‌ها و انتخاب پیشنهادی

| رویکرد | نحوه حفاظت از کلید | مزیت | محدودیت | انتخاب برای FinAnalyzer |
|---|---|---|---|---|
| GitHub-hosted Windows + Azure Artifact Signing + OIDC | کلید در سرویس امضای Azure؛ job فقط token کوتاه‌عمر می‌گیرد | runner clean، بدون PFX، راه‌اندازی و scale ساده | نیازمند Azure Artifact Signing و آماده‌سازی Entra | **پیشنهادی برای release عمومی** |
| self-hosted Windows signing runner + HSM/certificate store | کلید در HSM/token یا store کنترل‌شده | مناسب PKI داخلی یا الزام حاکمیتی | runner در معرض compromise پایدار است؛ عملیات و هزینه نگهداری بیشتر | فقط برای repo خصوصی با runner اختصاصی و دسترسی بسیار محدود |

GitHub هشدار می‌دهد که self-hosted runnerها تضمین VM clean و ephemeral ندارند و workflow یا کد غیرقابل‌اعتماد می‌تواند محیط آن‌ها را compromise کند.[3] بنابراین workflow فعلی عمداً روی `windows-2022` میزبانی‌شده اجرا می‌شود و از certificate محلی یا PFX استفاده نمی‌کند.

## پیش‌نیازهای Azure Artifact Signing

Azure administrator باید پیش از اجرای workflow، یک Artifact Signing Account، identity validation و Certificate Profile معتبر ایجاد کند. سپس Microsoft Entra application یا user-assigned managed identity باید نقش حداقلی **Artifact Signing Certificate Profile Signer** را روی profile مورد استفاده دریافت کند.[4]

> Endpoint Artifact Signing باید با region ساخت account و certificate profile منطبق باشد؛ عدم تطابق region معمولاً به خطای 403 یا failure در signing منجر می‌شود.[4]

| نام | محل نگهداری | مثال یا توضیح |
|---|---|---|
| `AZURE_CLIENT_ID` | GitHub Environment Secret | Client ID اپلیکیشن Entra؛ secret است، اما private key نیست |
| `AZURE_TENANT_ID` | GitHub Environment Secret | Directory/Tenant ID |
| `AZURE_SUBSCRIPTION_ID` | GitHub Environment Secret | Subscription مورد استفاده سرویس Azure |
| `AZURE_ARTIFACT_SIGNING_ENDPOINT` | GitHub Environment Variable | مانند `https://<region>.codesigning.azure.net/` |
| `AZURE_ARTIFACT_SIGNING_ACCOUNT` | GitHub Environment Variable | نام Artifact Signing Account |
| `AZURE_ARTIFACT_SIGNING_PROFILE` | GitHub Environment Variable | نام Certificate Profile |
| `RFC3161_TIMESTAMP_URL` | GitHub Environment Variable | `http://timestamp.acs.microsoft.com` |

Action رسمی Azure روی runner ویندوز اجرا می‌شود و ورودی‌های `file-digest`، `timestamp-rfc3161` و `timestamp-digest` را می‌پذیرد.[5] Microsoft برای Artifact Signing استفاده از `http://timestamp.acs.microsoft.com` با `SHA256` را توصیه می‌کند؛ گواهی‌های این سرویس سه‌روزه‌اند و timestamp برای اعتبارسنجی پایدار signature بعد از آن بازه حیاتی است.[4] [5]

## ایجاد trust مبتنی بر OIDC در Microsoft Entra

این فرایند یک‌بار توسط Azure/Entra administrator انجام می‌شود. OIDC باعث می‌شود GitHub workflow یک JWT کوتاه‌عمر دریافت و آن را با access token کوتاه‌عمر Azure مبادله کند؛ در نتیجه application secret یا certificate بلندعمر برای احراز هویت CI نگهداری نمی‌شود.[1] [6]

۱. در Microsoft Entra یک App Registration اختصاصی، مثلاً `FinAnalyzer-GitHub-Release-Signing`، ایجاد کنید و service principal آن را بسازید.

۲. روی Artifact Signing Certificate Profile، فقط نقش `Artifact Signing Certificate Profile Signer` را به همان service principal اختصاص دهید. نقش Owner یا Contributor subscription برای workflow لازم نیست و نباید داده شود.[4]

۳. در App Registration، یک **Federated Credential** بسازید. مقدار issuer باید GitHub Actions OIDC issuer باشد و audience برای Azure public cloud برابر `api://AzureADTokenExchange` انتخاب شود.[1]

۴. subject را فقط به environment release همین repository محدود کنید:

```text
repo:Ali-Marandi/FinAnalyzer:environment:production-signing
```

Issuer، subject و audience در federation باید case-sensitive با token واقعی GitHub منطبق باشند.[6] اگر subject از branch یا tag استفاده می‌کند، همان claim را در policy و workflow دقیقاً هم‌راستا نگه دارید. استفاده از environment subject، approval و branch/tag protection را به بخشی از trust boundary تبدیل می‌کند.[1]

## تنظیم GitHub Environment

در repository به مسیر **Settings → Environments → New environment** بروید و environment با نام دقیق `production-signing` بسازید. این نام باید با مقدار `environment:` در workflow یکسان باشد.

| تنظیم | مقدار پیشنهادی | علت |
|---|---|---|
| Required reviewers | حداقل یک Release Manager مستقل | بررسی انسانی پیش از دسترسی signing job به secrets |
| Prevent self-review | فعال | creator release نتواند job خودش را تأیید کند |
| Allow administrators to bypass | غیرفعال | مسیر bypass خارج از کنترل release نباشد |
| Deployment branches and tags | فقط tagهای `v*.*.*` | امضا فقط برای release versioned رخ دهد |
| Environment secrets | سه شناسه Azure بالا | secrets تنها بعد از approval در دسترس job قرار می‌گیرند |
| Environment variables | endpoint، account، profile و timestamp URL | configuration غیرمحرمانه از YAML جدا می‌ماند |

GitHub Environment می‌تواند reviewer اجباری، منع self-review و branch/tag policy اعمال کند. secretهای environment فقط پس از عبور job از protection rules قابل دسترسی‌اند.[7]

## مسیر اجرای workflow

Workflow `Signed Windows Release` فقط در این دو حالت اجرا می‌شود: push tag با الگوی `v*.*.*` یا اجرای دستی روی یک tag موجود. پیش از build، workflow tag را با الگوی semantic version بررسی می‌کند، commit checkout شده را با commit tag تطبیق می‌دهد و پس از آن dependency gate و همه testها را اجرا می‌کند.

| گام | کنترل |
|---|---|
| Checkout | source دقیق tag را دریافت می‌کند، نه branch متحرک |
| Dependency gate | `verify_windows_release.py` baseline وابستگی امن را fail-closed اعمال می‌کند |
| Test suite | تمام آزمون‌های پروژه اجرا می‌شوند |
| Build | `build_exe.py` artifact مشخص `FinAnalyzer_Enterprise_v2_5.exe` را تولید می‌کند |
| OIDC login | `id-token: write` اجازه دریافت token OIDC می‌دهد؛ permission جداگانه‌ای برای تغییر Azure ایجاد نمی‌کند.[1] |
| Signing | action Azure از profile سازمانی با `file-digest: SHA256` استفاده می‌کند |
| Timestamp | `timestamp-rfc3161: ${{ vars.RFC3161_TIMESTAMP_URL }}` و `timestamp-digest: SHA256` اعمال می‌شود |
| Verify | `signtool verify /pa /all /v /tw`، `Get-AuthenticodeSignature` و SHA-256 اجرا می‌شود |
| Publish | EXE، فایل `.sha256` و `signed-release-evidence.json` به release همان tag اضافه می‌شوند |

### بخش timestamp در workflow

```yaml
- name: Sign EXE and request RFC 3161 timestamp
  uses: azure/artifact-signing-action@v2
  with:
    endpoint: ${{ vars.AZURE_ARTIFACT_SIGNING_ENDPOINT }}
    signing-account-name: ${{ vars.AZURE_ARTIFACT_SIGNING_ACCOUNT }}
    certificate-profile-name: ${{ vars.AZURE_ARTIFACT_SIGNING_PROFILE }}
    files: ${{ github.workspace }}\dist\FinAnalyzer_Enterprise_v2_5.exe
    file-digest: SHA256
    timestamp-rfc3161: ${{ vars.RFC3161_TIMESTAMP_URL }}
    timestamp-digest: SHA256
    correlation-id: ${{ github.run_id }}-${{ github.run_attempt }}
```

`/tr` در SignTool برای RFC 3161 و `/td SHA256` برای digest timestamp به کار می‌رود. در صورت استفاده از Signing VM به جای Azure action، معادل مستقیم آن چنین است:[8]

```powershell
& $SignTool sign /fd SHA256 /sha1 $Thumbprint `
  /tr 'http://timestamp.acs.microsoft.com' /td SHA256 `
  /d 'FinAnalyzer Enterprise' C:\ReleaseInbox\FinAnalyzer_Enterprise_v2_5.exe

& $SignTool verify /pa /all /v /tw C:\ReleaseInbox\FinAnalyzer_Enterprise_v2_5.exe
if ($LASTEXITCODE -ne 0) { throw 'Signature or timestamp verification failed.' }
```

> `/sha1` در command بالا صرفاً thumbprint گواهی را برای انتخاب certificate local مشخص می‌کند. digest artifact همچنان با `/fd SHA256` تعیین می‌شود.[8]

## اجرای اول و کنترل انتشار

۱. ابتدا environment و federation را ایجاد کنید، اما secret یا URL را در YAML hard-code نکنید.

۲. یک tag آزمایشی داخلی، مانند `v2.5.1-rc.1`، در workflow production استفاده نکنید مگر آن‌که policy tag به‌صورت هدفمند آن را مجاز کرده باشد. برای تست signing، یک Certificate Profile غیرproduction و environment جدا مانند `staging-signing` بسازید.

۳. برای release واقعی، tag immutable `v2.5.1` یا نسخه بعدی را ایجاد کنید. workflow پس از approval environment اجرا می‌شود.

۴. در GitHub Release این سه asset را بررسی کنید: EXE، فایل SHA-256 و `signed-release-evidence.json`.

۵. Independent Verifier باید EXE را در یک Windows VM clean دانلود و دستورات زیر را اجرا کند:

```powershell
Get-FileHash .\FinAnalyzer_Enterprise_v2_5.exe -Algorithm SHA256
Get-AuthenticodeSignature .\FinAnalyzer_Enterprise_v2_5.exe |
  Format-List Status, SignerCertificate, TimeStamperCertificate
```

SHA-256 باید با asset منتشرشده برابر باشد، `Status` باید `Valid` باشد و `TimeStamperCertificate` نباید خالی باشد.

## کنترل‌های نگهداری و واکنش به خطا

| وضعیت | واکنش صحیح |
|---|---|
| timestamp response نامعتبر یا غایب | job fail شود؛ artifact منتشر نشود |
| `signtool verify` non-zero | release upload انجام نشود؛ evidence failure نگهداری شود |
| 403 در Artifact Signing | region endpoint، role profile signer و subject/audience federation را بررسی کنید؛ endpoint را حدس نزنید |
| runner/checkout مشکوک | workflow را متوقف، credential federation را موقتاً حذف یا محدود و artifact را باطل کنید |
| compromise یا تعویض certificate | profile قدیمی را revoke/disable، evidence affected releaseها را بررسی و artifactها را با certificate جدید امضا کنید |
| تغییر YAML امضا | CODEOWNERS و branch protection برای `.github/workflows/release-sign.yml` اعمال کنید؛ تغییر باید بازبینی مستقل داشته باشد |

## مراجع

[1] [GitHub Docs — Configuring OpenID Connect in Azure](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-azure)

[2] [Microsoft Learn — Use the Azure Login action with OpenID Connect](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect)

[3] [GitHub Docs — Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)

[4] [Microsoft Learn — Set up signing integrations to use Artifact Signing](https://learn.microsoft.com/en-us/azure/artifact-signing/how-to-signing-integrations)

[5] [Azure Artifact Signing Action — README](https://github.com/Azure/artifact-signing-action)

[6] [Microsoft Learn — Workload identity federation concepts](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation)

[7] [GitHub Docs — Managing environments for deployment](https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment)

[8] [Microsoft Learn — SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool)
