#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "BeeKeeper3000")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "This helper is for Windows PowerShell."
}

$secretPath = Join-Path $StateRoot "station-secrets.clixml"
if (-not (Test-Path $secretPath -PathType Leaf)) {
    throw "Station secrets not found. Start the BeeKeeper station first."
}

$secrets = Import-Clixml -LiteralPath $secretPath
if (-not ($secrets.PSObject.Properties.Name -contains "MonitorToken") -or
    -not ($secrets.MonitorToken -is [Security.SecureString])) {
    throw "Monitor token is missing or invalid in the DPAPI-protected secret file."
}

$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secrets.MonitorToken)
try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($token) -or $token.Length -lt 24 -or
        $token -notmatch '^[A-Za-z0-9+/=]+$') {
        throw "Stored Monitor token is not a valid generated token."
    }

    Set-Clipboard -Value $token
    Write-Host "Monitor session key copied to the Windows clipboard."
    Write-Host "Paste it only into http://127.0.0.1:8765/ on this station."
    Write-Host "After submitting the PWA form, clear the clipboard with: Set-Clipboard -Value ''"
    Write-Warning "Do not paste this secret into chat, tickets, logs or another website."
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    Remove-Variable token -ErrorAction SilentlyContinue
}
