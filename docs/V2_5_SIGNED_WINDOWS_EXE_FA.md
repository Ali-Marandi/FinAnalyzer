# راهنمای عملیاتی ساخت EXE امضاشده FinAnalyzer v2.5.0 در محیط ایزوله Windows

این راهنما مسیر تکرارپذیر ساخت، امضای دیجیتال، timestamp و راستی‌آزمایی فایل اجرایی **FinAnalyzer Enterprise v2.5.0** را در یک ماشین مجازی ویندوز ایزوله شرح می‌دهد. اجرای build باید زیر حساب انتشار مستقل انجام شود و تا پایان کنترل‌ها، فایل EXE نباید منتشر شود.

> **اصل امنیتی:** کلید خصوصی گواهی Code Signing نباید در repository، فایل `.env`، آرگومان خط فرمان، history ترمینال یا PFX بدون محافظت قرار بگیرد. اسکریپت پروژه از thumbprint گواهی موجود در `Cert:\CurrentUser\My` استفاده می‌کند و از دریافت رمز PFX خودداری می‌کند.

## پیش‌نیازها

| مورد | الزام | هدف |
|---|---|---|
| محیط اجرا | Windows 10/11 یا Windows Server ایزوله و به‌روز | جداسازی محیط release از توسعه روزمره |
| Python | Python 3.12 x64 | یکسان‌سازی محیط build |
| ابزار امضا | Windows SDK با `signtool.exe` | Authenticode signing و verification |
| گواهی | گواهی معتبر با EKU `Code Signing` و کلید خصوصی قابل‌استفاده | شناسایی ناشر و تمامیت binary |
| زمان‌سنجی | RFC 3161 timestamp endpoint مورد تأیید سازمان | تداوم اعتبار امضا پس از پایان اعتبار certificate |
| کد منبع | clone تمیز از repository و commit/tag تأییدشده | جلوگیری از انتشار تغییرات محلی یا ناشناخته |

Microsoft، `SignTool` را ابزار رسمی امضا، timestamp و verification معرفی می‌کند و آن را بخشی از Windows SDK می‌داند.[1] برای buildهای جدید باید `SHA256` را برای `/fd` و `/td` مشخص کرد؛ Microsoft استفاده از RFC 3161 با `/tr` و `/td SHA256` را نیز توصیه می‌کند.[1] [2]

## مرحله ۱: آماده‌سازی VM انتشار

۱. یک VM جدید بسازید، snapshot اولیه را ثبت کنید و آن را فقط برای release استفاده کنید. حساب کاربری release نباید حساب توسعه روزمره یا حساب ادمین عمومی باشد.

۲. Python 3.12 x64 و Windows SDK را نصب کنید. سپس در PowerShell بررسی کنید که ابزار امضا پیدا می‌شود:

```powershell
Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe |
  Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' }
```

۳. repository را از منبع مورد اعتماد دریافت کنید و روی commit تأییدشده قرار دهید. برای release فعلی می‌توانید tag موجود را checkout کنید؛ برای build دارای قابلیت‌های جدید باید commit تصویب‌شده release manager را checkout کنید.

```powershell
git clone https://github.com/Ali-Marandi/FinAnalyzer.git
Set-Location FinAnalyzer
git fetch --tags
git checkout v2.5.0
```

## مرحله ۲: آماده‌سازی گواهی امضا

گواهی Code Signing باید از مسیر سازمانی مورد تأیید، HSM، token سخت‌افزاری یا certificate store کاربر release فراهم شود. کلید خصوصی را در repository کپی نکنید. اگر سازمان از certificate store ویندوز استفاده می‌کند، thumbprint را به‌دست آورید:

```powershell
Get-ChildItem Cert:\CurrentUser\My |
  Where-Object { $_.EnhancedKeyUsageList.ObjectId.Value -contains '1.3.6.1.5.5.7.3.3' } |
  Select-Object Subject, Thumbprint, NotAfter, HasPrivateKey
```

خروجی باید نشان دهد `HasPrivateKey=True` و تاریخ `NotAfter` هنوز معتبر است. اسکریپت build نیز هر دو شرط و وجود Code Signing EKU را مجدداً کنترل می‌کند.

> اگر کلید با HSM یا smart card محافظت می‌شود، provider مربوطه باید گواهی را در store قابل‌دسترسی همان حساب release نشان دهد. رمز یا کلید را به script اضافه نکنید.

## مرحله ۳: ساخت ایزوله، کنترل وابستگی و امضا

اسکریپت زیر یک virtual environment تازه می‌سازد، `requirements-windows-build.txt` را نصب می‌کند، دروازه `pip-audit` را اجرا می‌کند، EXE را می‌سازد، آن را امضا و RFC 3161 timestamp می‌کند و سرانجام signature را verify می‌کند.

```powershell
Set-Location C:\Path\To\FinAnalyzer
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

.\scripts\build_signed_windows_release.ps1 `
  -CertificateThumbprint '<THUMBPRINT_40_HEX>' `
  -TimestampUrl 'https://timestamp.digicert.com' `
  -ReleaseUrl 'https://github.com/Ali-Marandi/FinAnalyzer/releases/tag/v2.5.0'
```

اسکریپت خروجی نهایی را در مسیر زیر می‌سازد:

```text
dist\FinAnalyzer_Enterprise_v2_5.exe
```

و شواهد قابل‌بازبینی را در این فایل‌ها نگه می‌دارد:

| فایل | محتوا |
|---|---|
| `security-reports/windows-build-dependencies.json` | snapshot بسته‌های محیط build |
| `security-reports/pip-audit.json` | خروجی ممیزی وابستگی‌ها |
| `security-reports/signed-release-evidence.json` | SHA-256 فایل، thumbprint، subject گواهی، timestamp URL و مسیر SignTool |

اگر هر مرحله خطا بدهد، PowerShell با `ErrorActionPreference=Stop` اجرا را متوقف می‌کند. فایل EXE فقط پس از عبور همه مراحل قابل انتشار است.

## مرحله ۴: راستی‌آزمایی مستقل پیش از انتشار

پس از اتمام script، در همان VM و ترجیحاً در یک VM clean دوم، این کنترل‌ها را اجرا کنید:

```powershell
$Exe = '.\dist\FinAnalyzer_Enterprise_v2_5.exe'
$SignTool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe |
  Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
  Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName

& $SignTool verify /pa /all /v /tw $Exe
Get-AuthenticodeSignature $Exe | Format-List Status, StatusMessage, SignerCertificate, TimeStamperCertificate
Get-FileHash $Exe -Algorithm SHA256
```

`SignTool verify` اعتبار زنجیره گواهی و وضعیت signature را بررسی می‌کند و `/tw` در نبود timestamp هشدار می‌دهد.[1] timestamp به verifier اجازه می‌دهد اعتبار امضا را پس از پایان اعتبار گواهی نیز بررسی کند؛ بدون timestamp، Windows پس از انقضای certificate binary را unsigned در نظر می‌گیرد.[2]

## مرحله ۵: انتشار و نگهداری شواهد

Release manager باید تنها فایل‌های زیر را به release نهایی اضافه کند: EXE امضاشده، SHA-256 منتشرشده، و در صورت نیاز فایل evidence. قبل از upload، SHA-256 محاسبه‌شده در VM دوم باید با مقدار `signed-release-evidence.json` برابر باشد. خروجی gate، log تست، evidence signature و شناسه commit/tag باید به پرونده کنترل تغییر سازمان اضافه شوند.

| کنترل انتشار | معیار قبولی |
|---|---|
| وابستگی‌ها | `verify_windows_release.py` با exit code صفر پایان یابد |
| تست‌ها | `python -m unittest discover -s tests -v` موفق باشد |
| امضا | `signtool verify /pa /all /v /tw` موفق باشد |
| timestamp | certificate زمان‌سنج و timestamp در verification دیده شود |
| هش artifact | SHA-256 فایل انتشار با evidence برابر باشد |
| پاکیزگی محیط | هیچ PFX، secret، database محلی یا key audit در release asset نباشد |

## رفع خطاهای رایج

| نشانه | علت محتمل | اقدام ایمن |
|---|---|---|
| `signtool.exe was not found` | Windows SDK یا component امضا نصب نیست | Windows SDK را نصب کنید؛ مسیر hard-code نکنید |
| گواهی یافت نشد | گواهی در store حساب دیگر یا HSM دیگر است | با همان حساب release، store و مجوز HSM را بررسی کنید |
| `HasPrivateKey=False` | فقط public certificate وارد شده است | private key را با فرایند سازمانی/HSM provision کنید؛ PFX خام نسازید |
| timestamp ناموفق است | endpoint یا شبکه مورد تأیید نیست | انتشار را متوقف کنید؛ endpoint RFC 3161 مورد تأیید سازمان را بررسی کنید |
| dependency gate شکست خورد | محیط آلوده یا نسخه آسیب‌پذیر | `.venv-build` را حذف و script را از ابتدا اجرا کنید |
| verification هشدار می‌دهد | signature یا timestamp ناقص است | artifact را منتشر نکنید؛ علت را برطرف و مجدداً build کنید |

## چرا `/fd SHA256 /tr … /td SHA256`؟

> Microsoft توصیه می‌کند برای Authenticode از digest `SHA-256` استفاده شود و timestamp RFC 3161 با `/tr` و `/td SHA256` اعمال شود؛ SHA-1 برای امضاهای جدید قابل اتکا نیست.[2]

`/fd SHA256` هش فایل را برای signature تعیین می‌کند. `/tr` درخواست timestamp استاندارد RFC 3161 می‌فرستد و `/td SHA256` الگوریتم digest timestamp را تعیین می‌کند. timestamp باید در همان دستور signing انجام شود تا artifact بدون شکاف عملیاتی امضا و زمان‌سنجی شود.

## مراجع

[1] [Microsoft Learn — SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool)
[2] [Microsoft Learn — Time Stamping Authenticode Signatures](https://learn.microsoft.com/en-us/windows/win32/seccrypto/time-stamping-authenticode-signatures)
[3] [Microsoft Learn — SignTool.exe reference](https://learn.microsoft.com/en-us/dotnet/framework/tools/signtool-exe)
