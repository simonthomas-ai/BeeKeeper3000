#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "BeeKeeper3000")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "This stop script is for Windows PowerShell."
}

$processRoot = Join-Path $StateRoot "processes"
if (-not (Test-Path $processRoot)) {
    Write-Host "No BeeKeeper station process directory found."
    exit 0
}

foreach ($name in @("bridge","source-api","monitor")) {
    $metadataPath = Join-Path $processRoot ($name + ".json")
    if (-not (Test-Path $metadataPath)) { continue }

    $metadata = Get-Content -Raw -LiteralPath $metadataPath | ConvertFrom-Json
    $processId = [int]$metadata.pid
    $process = Get-CimInstance Win32_Process -Filter ("ProcessId = " + $processId) -ErrorAction SilentlyContinue

    if (-not $process) {
        Write-Host "$name already stopped (PID $processId no longer exists)."
        Remove-Item -LiteralPath $metadataPath -Force
        continue
    }

    $sameExecutable = $process.ExecutablePath -and
        [string]::Equals($process.ExecutablePath, [string]$metadata.executable, [StringComparison]::OrdinalIgnoreCase)
    $sameCommand = $process.CommandLine -and
        $process.CommandLine.Contains([string]$metadata.marker)

    if (-not ($sameExecutable -and $sameCommand)) {
        Write-Warning "Not stopping PID $processId: process identity does not match the recorded BeeKeeper service. Check $metadataPath manually."
        continue
    }

    Stop-Process -Id $processId -Force
    try { Wait-Process -Id $processId -Timeout 10 -ErrorAction Stop } catch {}
    Remove-Item -LiteralPath $metadataPath -Force
    Write-Host "$name stopped."
}
