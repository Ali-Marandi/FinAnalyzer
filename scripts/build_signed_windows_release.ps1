<#
.SYNOPSIS
Builds, signs, time-stamps, and verifies a FinAnalyzer Windows release in an isolated virtual environment.

.DESCRIPTION
The code-signing private key must remain in the current user's Windows certificate store,
HSM, or an approved cloud-signing provider. This script never accepts a PFX password or
private key on the command line. It stops on dependency-gate, build, signature, or
verification failures and stores reproducible release evidence under security-reports.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Fa-f0-9]{40}$')]
    [string]$CertificateThumbprint,

    [Parameter()]
    [ValidatePattern('^https://')]
    [string]$TimestampUrl = 'https://timestamp.digicert.com',

    [Parameter()]
    [string]$PythonLauncher = 'py',

    [Parameter()]
    [string]$ReleaseUrl = 'https://github.com/Ali-Marandi/FinAnalyzer/releases/tag/v2.7.0'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if ($env:OS -ne 'Windows_NT') {
    throw 'This release script must run on Windows.'
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ProjectRoot
$VenvPath = Join-Path $ProjectRoot '.venv-build'
$ReportPath = Join-Path $ProjectRoot 'security-reports'
$ExpectedExe = Join-Path $ProjectRoot 'dist\\FinAnalyzer_Enterprise_v2_7_0.exe'
New-Item -ItemType Directory -Force -Path $ReportPath | Out-Null

function Find-SignTool {
    $sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
    $candidate = Get-ChildItem -Path $sdkRoot -Filter 'signtool.exe' -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    if ($null -eq $candidate) {
        throw 'signtool.exe was not found. Install the Windows SDK (Desktop C++ signing tools) and retry.'
    }
    return $candidate.FullName
}

function Test-CodeSigningCertificate {
    param([string]$Thumbprint)
    $normalized = $Thumbprint.Replace(' ', '').ToUpperInvariant()
    $certificate = Get-ChildItem -Path "Cert:\CurrentUser\My\$normalized" -ErrorAction SilentlyContinue
    if ($null -eq $certificate) {
        throw 'The requested certificate is not present in Cert:\CurrentUser\My. Import/provision it through the approved HSM or certificate workflow.'
    }
    if (-not $certificate.HasPrivateKey) {
        throw 'The selected certificate has no private key available to this Windows user.'
    }
    $codeSigningOid = '1.3.6.1.5.5.7.3.3'
    $hasCodeSigningEku = $certificate.EnhancedKeyUsageList.ObjectId.Value -contains $codeSigningOid
    if (-not $hasCodeSigningEku) {
        throw 'The selected certificate does not contain the Code Signing EKU.'
    }
    if ($certificate.NotAfter -le (Get-Date)) {
        throw 'The selected code-signing certificate is expired.'
    }
    return $certificate
}

Write-Host 'Creating a clean isolated Python build environment...'
if (Test-Path $VenvPath) {
    Remove-Item -Recurse -Force $VenvPath
}
& $PythonLauncher '-3.12' '-m' 'venv' $VenvPath
$Python = Join-Path $VenvPath 'Scripts\python.exe'
& $Python '-m' 'pip' 'install' '--upgrade' 'pip'
& $Python '-m' 'pip' 'install' '-r' 'requirements-windows-build.txt'
& $Python 'scripts\verify_windows_release.py'

Write-Host 'Building FinAnalyzer EXE...'
& $Python 'build_exe.py'
if (-not (Test-Path $ExpectedExe)) {
    throw "Expected executable was not created: $ExpectedExe"
}

$certificate = Test-CodeSigningCertificate -Thumbprint $CertificateThumbprint
$SignTool = Find-SignTool
Write-Host "Signing $ExpectedExe with certificate subject $($certificate.Subject)..."
& $SignTool 'sign' '/sha1' $CertificateThumbprint '/fd' 'SHA256' '/tr' $TimestampUrl '/td' 'SHA256' '/d' 'FinAnalyzer Enterprise' '/du' $ReleaseUrl $ExpectedExe
if ($LASTEXITCODE -ne 0) {
    throw "SignTool sign failed with exit code $LASTEXITCODE."
}

Write-Host 'Verifying Authenticode signature and RFC 3161 timestamp...'
& $SignTool 'verify' '/pa' '/all' '/v' '/tw' $ExpectedExe
if ($LASTEXITCODE -ne 0) {
    throw "SignTool verification failed with exit code $LASTEXITCODE. Do not publish this EXE."
}

$hash = Get-FileHash -Path $ExpectedExe -Algorithm SHA256
$evidence = [ordered]@{
    product = 'FinAnalyzer Enterprise'
    version = '2.7.0'
    executable = (Resolve-Path $ExpectedExe).Path
    sha256 = $hash.Hash
    certificate_subject = $certificate.Subject
    certificate_thumbprint = $certificate.Thumbprint
    timestamp_url = $TimestampUrl
    release_url = $ReleaseUrl
    built_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    sign_tool = $SignTool
}
$evidencePath = Join-Path $ReportPath 'signed-release-evidence.json'
$evidence | ConvertTo-Json | Set-Content -Path $evidencePath -Encoding UTF8
Write-Host "SUCCESS: signed and verified EXE created at $ExpectedExe"
Write-Host "Evidence: $evidencePath"
