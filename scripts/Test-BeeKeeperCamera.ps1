#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$PythonExe = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$doctor = Join-Path $repoRoot "scripts\station_doctor.py"
if (-not (Test-Path -LiteralPath $doctor -PathType Leaf)) {
    throw "Station doctor not found in this checkout."
}

$pythonCommand = Get-Command -Name $PythonExe -CommandType Application -ErrorAction Stop |
    Select-Object -First 1
if (-not $pythonCommand) {
    throw "Python executable not found: $PythonExe"
}

Write-Host "Enter camera index (for example 0) or the complete local RTSP(S)/HTTP(S) URL."
Write-Host "Input is hidden. The source is passed only as a temporary process environment variable."
$secureSource = Read-Host -Prompt "Camera source" -AsSecureString
$pointer = [IntPtr]::Zero
$source = $null
$exitCode = 2
$locationPushed = $false

try {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureSource)
    $source = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($source)) {
        throw "Camera source cannot be empty."
    }

    [Environment]::SetEnvironmentVariable("BEEKEEPER_CAMERA_SOURCE", $source, "Process")
    Push-Location $repoRoot
    $locationPushed = $true

    & $pythonCommand.Path $doctor --test-camera --json
    $exitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable("BEEKEEPER_CAMERA_SOURCE", $null, "Process")
    $source = $null
    if ($pointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
    if ($secureSource) {
        $secureSource.Dispose()
    }
    if ($locationPushed) {
        Pop-Location
    }
}

if ($exitCode -ne 0) {
    Write-Warning "Station doctor reported at least one failed check. Read the 'Live camera test' row separately; other local service checks may also fail."
}
exit $exitCode
