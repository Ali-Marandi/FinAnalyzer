# Runbook تفصیلی ساخت و امضای EXE در محیط ایزوله Windows — FinAnalyzer v2.5.0

این runbook یک فرایند عملیاتی قابل‌تکرار برای تولید **FinAnalyzer_Enterprise_v2_5.exe** ارائه می‌کند. هدف آن کاهش ریسک آلودگی محیط build، افشای کلید Code Signing، جایگزینی artifact و انتشار فایل بدون timestamp معتبر است.

> **قانون انتشار:** فایل EXE تا زمانی که dependency gate، تست‌ها، امضا، RFC 3161 timestamp، verification مستقل و تطبیق SHA-256 را پشت سر نگذاشته است، release asset نیست.

## ۱. انتخاب مدل جداسازی

برای release رسمی، مدل **دو محیطی** توصیه می‌شود: محیط build فاقد کلید امضا باشد و محیط signing به کلید سازمانی دسترسی محدود داشته باشد. Windows Sandbox برای test یا build disposable بسیار مناسب است، اما به‌دلیل موقتی بودن و حذف فایل‌ها/نرم‌افزارها در زمان بسته‌شدن، معمولاً محل مناسب نگهداری کلید امضای سازمانی نیست.[1]

| مدل | کاربرد مناسب | کلید امضا | نکته مهم |
|---|---|---|---|
| Windows Sandbox | smoke test، build disposable و بررسی artifact | **خیر** | هر بار clean است و هنگام بسته‌شدن state را حذف می‌کند.[1] |
| Build VM با snapshot | build رسمی، تست کامل و تولید evidence وابستگی | **خیر** | پس از release به snapshot پاک بازگردد |
| Signing VM / HSM workstation | امضا، timestamp و verify | فقط از certificate store یا HSM | شبکه و دسترسی کاربر باید حداقل باشد |

Windows Sandbox یک محیط desktop سبک و hypervisor-isolated است؛ نصب‌های داخل آن از host جدا می‌مانند و هر شروع، instance تازه‌ای ایجاد می‌کند.[1] به‌صورت پیش‌فرض networking در Sandbox فعال است؛ برای اجرای فایل‌های ناشناخته باید آن را در فایل `.wsb` غیرفعال و پوشه میزبان را read-only map کرد.[1] **برای نصب وابستگی یا clone repository، networking لازم است؛ بنابراین فقط source تأییدشده را در Sandbox build اجرا کنید.**

## ۲. نقش‌ها و تفکیک وظایف release

| نقش | مسئولیت | نباید داشته باشد |
|---|---|---|
| Release Manager | تأیید tag/commit، تصمیم publish و آرشیو evidence | private key امضا |
| Build Operator | ساخت از source تأییدشده، اجرای تست و dependency gate | دسترسی به Code Signing certificate |
| Signing Operator | امضا، timestamp و verification | امکان تغییر source بعد از approval |
| Independent Verifier | تطبیق hash، signature، timestamp و evidence | امکان جایگزینی artifact |

در سازمان کوچک، یک نفر ممکن است چند نقش را بر عهده بگیرد؛ بااین‌حال **Build Operator نباید به private key دسترسی داشته باشد** و Independent Verifier باید دست‌کم hash و signature را خارج از session ساخت بررسی کند.

## ۳. پیش‌نیازهای host یا VM

Windows Sandbox برای نسخه‌های Pro، Enterprise و Education پشتیبانی می‌شود و روی Home در دسترس نیست.[1] پیش‌نیازهای رسمی شامل AMD64 یا Arm64 پشتیبانی‌شده، فعال بودن virtualization، دست‌کم ۴GB RAM (۸GB پیشنهادشده)، ۱GB فضای آزاد و دست‌کم دو core CPU است.[2]

| پیش‌نیاز | کنترل پیشنهادی |
|---|---|
| OS | Windows 10 نسخه 1903 یا جدیدتر، یا Windows 11؛ برای Sandbox از edition پشتیبانی‌شده استفاده کنید.[2] |
| virtualization | در BIOS/UEFI فعال باشد؛ در VM از nested virtualization استفاده شود.[2] |
| زمان سیستم | با time source سازمانی sync باشد؛ timestamp جایگزین clock سیستم نیست ولی خطای زمان تحلیل را دشوار می‌کند |
| Windows SDK | `signtool.exe` x64 موجود باشد؛ SignTool بخشی از Windows SDK است.[3] |
| Python | Python 3.12 x64، همان baseline پروژه |
| source | clone تازه و tag/commit مورد تأیید؛ directory کپی‌شده از workstation توسعه استفاده نشود |
| گواهی | Code Signing EKU، private key قابل‌استفاده و ترجیحاً HSM/token یا certificate store controlled |

### فعال‌سازی Windows Sandbox

در PowerShell با دسترسی Administrator روی host یا VM پشتیبانی‌شده اجرا کنید و بعد restart کنید:

```powershell
Enable-WindowsOptionalFeature -FeatureName "Containers-DisposableClientVM" -All -Online
Restart-Computer
```

این command همان feature رسمی Windows Sandbox را فعال می‌کند.[2] در محیط Hyper-V nested، virtualization extensions باید روی host برای VM مربوطه expose شوند؛ برای نمونه، Microsoft از `Set-VMProcessor -ExposeVirtualizationExtensions $true` استفاده می‌کند.[2]

## ۴. ساخت workspace کنترل‌شده

روی Build VM دو مسیر ایجاد کنید. `ReleaseDrop` فقط برای خروجی‌های build استفاده می‌شود و باید بعد از build read-only شود. هیچ PFX، key file یا credential در این مسیر قرار ندهید.

```powershell
New-Item -ItemType Directory -Force C:\FinAnalyzer\Source | Out-Null
New-Item -ItemType Directory -Force C:\FinAnalyzer\ReleaseDrop | Out-Null
New-Item -ItemType Directory -Force C:\FinAnalyzer\Evidence | Out-Null

icacls C:\FinAnalyzer\ReleaseDrop /inheritance:r
icacls C:\FinAnalyzer\ReleaseDrop /grant:r "$env:USERNAME:(OI)(CI)M"
```

در Build VM، repository را clone و فقط tag مورد تأیید را checkout کنید. پیش از build باید working tree تمیز باشد و `HEAD` دقیقاً به tag مورد نظر اشاره کند.

```powershell
Set-Location C:\FinAnalyzer\Source
git clone https://github.com/Ali-Marandi/FinAnalyzer.git FinAnalyzer
Set-Location .\FinAnalyzer
git fetch --tags --force
git checkout --detach v2.5.0
git status --short
git rev-parse HEAD
git describe --tags --exact-match HEAD
```

سه دستور پایانی باید به‌ترتیب خروجی خالی، یک commit ID ثبت‌شده و `v2.5.0` بدهند. Release Manager باید commit ID را در ticket انتشار یا evidence ثبت کند.

## ۵. الگوی Windows Sandbox برای smoke build

فایل زیر را روی host به نام `C:\FinAnalyzer\FinAnalyzer-Build.wsb` ذخیره کنید. این مثال source را **read-only** map می‌کند؛ sandbox باید ابتدا source را به `C:\work\FinAnalyzer` کپی کند تا بتواند `.venv-build`، `build` و `dist` را بدون تغییر host ایجاد کند. پوشه ReleaseDrop عمداً writable است تا artifact بیرون منتقل شود؛ تنها source تأییدشده را در این Sandbox اجرا کنید.

```xml
<Configuration>
  <VGpu>Disable</VGpu>
  <Networking>Enable</Networking>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>C:\FinAnalyzer\Source</HostFolder>
      <SandboxFolder>C:\mounted-source</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>C:\FinAnalyzer\ReleaseDrop</HostFolder>
      <SandboxFolder>C:\release-drop</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
  </MappedFolders>
</Configuration>
```

Microsoft نمونه‌های رسمی folder mapping، read-only access، خاموش‌کردن network و LogonCommand را مستند کرده است.[5] اگر قصد فقط **verify** یک EXE ناشناخته را دارید، `Networking` را `Disable` کنید و فقط پوشه حاوی artifact را read-only map نمایید.[1] [5]

در Sandbox، Python 3.12 و Windows SDK را فقط از کانال داخلی یا vendor مورد تأیید نصب کنید. سپس source را کپی کرده و build verification را اجرا کنید:

```powershell
Copy-Item -Recurse -Force C:\mounted-source\FinAnalyzer C:\work\FinAnalyzer
Set-Location C:\work\FinAnalyzer

py -3.12 -m venv .venv-build
.\.venv-build\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-windows-build.txt
python scripts\verify_windows_release.py
python -m unittest discover -s tests -v
python build_exe.py

Copy-Item .\dist\FinAnalyzer_Enterprise_v2_5.exe C:\release-drop\
Get-FileHash C:\release-drop\FinAnalyzer_Enterprise_v2_5.exe -Algorithm SHA256 |
  Format-List | Out-File C:\release-drop\FinAnalyzer_Enterprise_v2_5.sha256.txt -Encoding utf8
```

> اگر Python installer، SDK installer یا وابستگی‌ها از اینترنت دانلود می‌شوند، شبکه Sandbox صرفاً باید برای منابع مورد تأیید باز باشد. برای release production، Build VM با snapshot، proxy allow-list و mirror داخلی dependencyها کنترل‌پذیرتر از Sandbox است.

## ۶. کنترل dependency و تست در Build VM

`requirements-windows-build.txt` و `constraints-windows.txt` baseline ساخت را تعیین می‌کنند. gate پروژه `scripts/verify_windows_release.py` باید قبل از build اجرا شود؛ اگر vulnerability یا نسخه نامنطبق تشخیص دهد، build باید متوقف شود.

```powershell
Set-Location C:\FinAnalyzer\Source\FinAnalyzer
py -3.12 -m venv .venv-build
.\.venv-build\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-windows-build.txt
python scripts\verify_windows_release.py
python -m unittest discover -s tests -v
python build_exe.py
```

خروجی مورد انتظار شامل `dist\FinAnalyzer_Enterprise_v2_5.exe` و گزارش‌های `security-reports\windows-build-dependencies.json` و `security-reports\pip-audit.json` است. بدون موفقیت همه commandها، artifact را به Signing VM منتقل نکنید.

## ۷. انتقال کنترل‌شده artifact به Signing VM

۱. Build Operator مقدار SHA-256 را از Build VM استخراج و در ticket release ثبت می‌کند.

۲. artifact و evidence فقط از کانال سازمانی کنترل‌شده منتقل می‌شوند. Signing Operator باید hash را **پیش از امضا** محاسبه و با مقدار ثبت‌شده برابر کند.

```powershell
Get-FileHash C:\ReleaseInbox\FinAnalyzer_Enterprise_v2_5.exe -Algorithm SHA256
Get-Content C:\ReleaseInbox\FinAnalyzer_Enterprise_v2_5.sha256.txt
```

۳. اگر hash متفاوت بود، artifact را حذف کنید، incident ثبت کنید و build را از workspace clean تکرار نمایید. artifact جایگزین یا hash دوباره‌نویسی‌شده را «اصلاح عملیاتی» تلقی نکنید.

## ۸. آماده‌سازی Signing VM و گواهی

Signing VM باید حساب release اختصاصی، Windows SDK و تنها ابزارهای لازم برای verify/sign داشته باشد. private key ترجیحاً در HSM یا token سخت‌افزاری نگهداری شود. هرگز PFX و رمز آن را در repository، `.env`، PowerShell history یا folder map مشترک قرار ندهید.

گواهی موجود در Personal store حساب release را بررسی کنید:

```powershell
Get-ChildItem Cert:\CurrentUser\My |
  Where-Object {
    $_.HasPrivateKey -and
    $_.EnhancedKeyUsageList.ObjectId.Value -contains '1.3.6.1.5.5.7.3.3'
  } |
  Select-Object Subject, Thumbprint, NotBefore, NotAfter, HasPrivateKey
```

OID `1.3.6.1.5.5.7.3.3` همان EKU **Code Signing** است و SignTool نیز به‌صورت پیش‌فرض آن را برای signing certificate بررسی می‌کند.[3] thumbprint دقیق ۴۰ کاراکتری را از این خروجی در متغیر امن session وارد کنید؛ آن را در script یا repository hard-code نکنید.

## ۹. امضا و RFC 3161 timestamp

SignTool باید با `/fd SHA256` برای digest فایل و `/tr … /td SHA256` برای timestamp RFC 3161 اجرا شود. Microsoft تصریح می‌کند که نسخه‌های جدید SDK به تعیین `/fd` و `/td` نیاز دارند و SHA-256 توصیه‌شده است.[3] Microsoft همچنین timestamp را ضروری می‌داند؛ بدون timestamp، پس از انقضای certificate Windows فایل را unsigned تلقی می‌کند.[4]

ابتدا SignTool x64 را بیابید:

```powershell
$SignTool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe |
  Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
  Sort-Object FullName -Descending |
  Select-Object -First 1 -ExpandProperty FullName

if (-not $SignTool) { throw 'signtool.exe x64 was not found.' }
```

سپس فایل ورودی را امضا کنید. URL timestamp باید از provider یا policy سازمانی مورد تأیید باشد.

```powershell
$Exe = 'C:\ReleaseInbox\FinAnalyzer_Enterprise_v2_5.exe'
$Thumbprint = '<THUMBPRINT_40_HEX>'
$TimestampUrl = 'https://timestamp.digicert.com'

& $SignTool sign /v /fd SHA256 /sha1 $Thumbprint /tr $TimestampUrl /td SHA256 `
  /d 'FinAnalyzer Enterprise v2.5.0' $Exe
if ($LASTEXITCODE -ne 0) { throw "Signing failed with exit code $LASTEXITCODE." }
```

استفاده از `/sha1` در این command برای **انتخاب thumbprint گواهی** است، نه انتخاب الگوریتم امضای فایل؛ الگوریتم امضای فایل به‌صراحت `/fd SHA256` است.[3]

## ۱۰. verification در Signing VM و VM مستقل

پس از امضا، بلافاصله signature و timestamp را verify کنید:

```powershell
& $SignTool verify /pa /all /v /tw $Exe
if ($LASTEXITCODE -ne 0) { throw "Signature verification failed with exit code $LASTEXITCODE." }

Get-AuthenticodeSignature $Exe |
  Format-List Status, StatusMessage, SignerCertificate, TimeStamperCertificate

Get-FileHash $Exe -Algorithm SHA256
```

`/pa` سیاست Default Authentication Verification را اعمال می‌کند، `/all` همه signatureها را بررسی می‌کند، `/v` جزئیات signer را نشان می‌دهد و `/tw` نبود timestamp را به warning تبدیل می‌کند.[3] [4] Microsoft خروجی `0` را موفق، `1` را failure و `2` را completion همراه warning اعلام می‌کند؛ policy انتشار باید خروجی غیرصفر را مسدودکننده تلقی کند.[3]

یک Independent Verifier باید همین سه command را در VM clean دوم اجرا کند و hash نهایی را در release evidence تطبیق دهد. برای این مرحله، فقط EXE و فایل hash لازم است؛ به گواهی خصوصی نیاز نیست.

## ۱۱. evidence و publish

اسکریپت پروژه `scripts/build_signed_windows_release.ps1` در حالت یک‌محیطی، build، sign، timestamp، verify و ثبت evidence را انجام می‌دهد. برای release سازمانی، evidence زیر را به پرونده change-control اضافه کنید:

| evidence | تولیدکننده | کنترل بازبینی |
|---|---|---|
| commit/tag و source hash | Release Manager | tag با commit approved برابر است |
| `windows-build-dependencies.json` | Build VM | snapshot با baseline هماهنگ است |
| `pip-audit.json` | Build VM | vulnerability مسدودکننده باقی نمانده است |
| log تست | Build VM | همه تست‌ها موفق‌اند |
| SHA-256 قبل از امضا | Build VM / Signing VM | در انتقال artifact برابر است |
| `signed-release-evidence.json` | Signing VM | subject، thumbprint، timestamp و SHA-256 ثبت شده‌اند |
| SHA-256 پس از امضا | Independent Verifier | با مقدار منتشرشده در release برابر است |

تنها پس از تأیید evidence، EXE امضاشده و فایل `SHA256` را به GitHub Release یا کانال distribution سازمانی اضافه کنید. `.pfx`، کلید audit، database واقعی، report حاوی داده مشتری و log شامل secret هرگز release asset نیستند.

## ۱۲. پاک‌سازی و بازگشت به baseline

پس از انتشار، credentialهای موقتی، `.venv-build`، source clone، downloaded installers و artifactهای امضانشده را از Build VM پاک کنید یا VM را به snapshot clean بازگردانید. در Signing VM، تنها evidence لازم را طبق retention policy نگه دارید و private key را از certificate store/HSM حذف نکنید؛ lifecycle گواهی باید زیر کنترل PKI سازمان باشد.

Windows Sandbox با بسته‌شدن، state داخلی را حذف می‌کند؛ بااین‌حال این ویژگی، جایگزین پاک‌سازی مسیرهای writable map‌شده روی host نیست.[1] ReleaseDrop، evidence و هر folder map‌شده را جداگانه بازبینی و پاک‌سازی کنید.

## مراجع

[1] [Microsoft Learn — Windows Sandbox](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/)
[2] [Microsoft Learn — Install Windows Sandbox](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-install)
[3] [Microsoft Learn — SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool)
[4] [Microsoft Learn — Time Stamping Authenticode Signatures](https://learn.microsoft.com/en-us/windows/win32/seccrypto/time-stamping-authenticode-signatures)
[5] [Microsoft Learn — Windows Sandbox Sample Configuration Files](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-sample-configuration)
