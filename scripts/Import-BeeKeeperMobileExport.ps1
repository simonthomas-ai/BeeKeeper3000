#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ExportFile,
    [string]$PythonExe = "python",
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "BeeKeeper3000")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") { throw "Dieser DPAPI-Importer ist für Windows PowerShell vorgesehen." }
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$exportPath = (Resolve-Path -LiteralPath $ExportFile -ErrorAction Stop).Path
$secretPath = Join-Path $StateRoot "station-secrets.clixml"
if (-not (Test-Path -LiteralPath $secretPath -PathType Leaf)) {
    throw "DPAPI-Stationsschlüssel nicht gefunden. Starte die BeeKeeper-Station zuerst unter diesem Windows-Benutzer."
}
$pythonCommand = Get-Command -Name $PythonExe -CommandType Application -ErrorAction Stop | Select-Object -First 1
if (-not $pythonCommand) { throw "Python wurde nicht gefunden: $PythonExe" }
$pythonPath = $pythonCommand.Path
$secrets = Import-Clixml -LiteralPath $secretPath
if (-not ($secrets.PSObject.Properties.Name -contains "SourceApiKey") -or
    -not ($secrets.SourceApiKey -is [Security.SecureString])) {
    throw "DPAPI-SourceApiKey fehlt oder ist ungültig."
}

$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secrets.SourceApiKey)
$previous = [Environment]::GetEnvironmentVariable("HORNET3000_API_KEY", "Process")
$exitCode = 1
try {
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    [Environment]::SetEnvironmentVariable("HORNET3000_API_KEY", $apiKey, "Process")
    & $pythonPath (Join-Path $repoRoot "scripts/import_mobile_export.py") $exportPath
    $exitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable("HORNET3000_API_KEY", $previous, "Process")
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $apiKey = $null
    $secrets = $null
}
if ($exitCode -ne 0) { throw "Mobilexport wurde nicht vollständig importiert (Exitcode $exitCode)." }
