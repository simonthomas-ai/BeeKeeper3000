#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ModelManifest,
    [Parameter(Mandatory = $true)][string]$CameraSource,
    [Parameter(Mandatory = $true)][string]$StationId,
    [string]$PythonExe = "python",
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "BeeKeeper3000"),
    [string]$SourceApiUrl = "http://127.0.0.1:8787",
    [ValidateRange(0.1,15)][double]$MaxFps = 5,
    [ValidateRange(0,86400)][double]$CooldownSeconds = 30,
    [ValidateRange(1,8)][int]$OnnxThreads = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "Use python -m camera.runtime with protected environment variables on Linux."
}
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$secretPath = Join-Path $StateRoot "station-secrets.clixml"
if (-not (Test-Path $secretPath -PathType Leaf)) {
    throw "Station DPAPI secrets not found. Start the base station once first."
}
if (-not (Test-Path $ModelManifest -PathType Leaf)) {
    throw "Model manifest not found: $ModelManifest"
}
$manifestPath = (Resolve-Path $ModelManifest).Path
if ([string]::IsNullOrWhiteSpace($CameraSource)) { throw "CameraSource is required." }
if ([string]::IsNullOrWhiteSpace($StationId) -or $StationId -notmatch '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$') {
    throw "StationId must be a short technical ID."
}

$pythonCommand = Get-Command -Name $PythonExe -CommandType Application -ErrorAction Stop | Select-Object -First 1
if (-not $pythonCommand) { throw "Python executable not found: $PythonExe" }
$pythonPath = $pythonCommand.Path
$secrets = Import-Clixml -LiteralPath $secretPath
if (-not ($secrets.SourceApiKey -is [Security.SecureString])) {
    throw "DPAPI SourceApiKey is missing or invalid."
}
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secrets.SourceApiKey)
try {
    $sourceApiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
}

$names = @(
    "HORNET3000_API_KEY","HORNET3000_STATION_ID","HORNET3000_URL",
    "BEEKEEPER_MODEL_MANIFEST","BEEKEEPER_CAMERA_SOURCE","BEEKEEPER_CAMERA_OUTBOX",
    "BEEKEEPER_CAMERA_MAX_FPS","BEEKEEPER_CAMERA_COOLDOWN_SECONDS","BEEKEEPER_ONNX_THREADS"
)
$previous = @{}
foreach ($name in $names) { $previous[$name] = [Environment]::GetEnvironmentVariable($name, "Process") }
try {
    [Environment]::SetEnvironmentVariable("HORNET3000_API_KEY", $sourceApiKey, "Process")
    [Environment]::SetEnvironmentVariable("HORNET3000_STATION_ID", $StationId, "Process")
    [Environment]::SetEnvironmentVariable("HORNET3000_URL", $SourceApiUrl, "Process")
    [Environment]::SetEnvironmentVariable("BEEKEEPER_MODEL_MANIFEST", $manifestPath, "Process")
    [Environment]::SetEnvironmentVariable("BEEKEEPER_CAMERA_SOURCE", $CameraSource, "Process")
    [Environment]::SetEnvironmentVariable("BEEKEEPER_CAMERA_OUTBOX", (Join-Path $StateRoot "datacamera-outbox.sqlite3"), "Process")
    [Environment]::SetEnvironmentVariable("BEEKEEPER_CAMERA_MAX_FPS", [string]$MaxFps, "Process")
    [Environment]::SetEnvironmentVariable("BEEKEEPER_CAMERA_COOLDOWN_SECONDS", [string]$CooldownSeconds, "Process")
    [Environment]::SetEnvironmentVariable("BEEKEEPER_ONNX_THREADS", [string]$OnnxThreads, "Process")

    Push-Location $repoRoot
    try {
        & $pythonPath -c "import cv2, onnxruntime"
        if ($LASTEXITCODE -ne 0) {
            throw "Camera dependencies are missing. Install cameraequirements.txt into this Python environment."
        }
        & $pythonPath -m camera.runtime
        if ($LASTEXITCODE -ne 0) { throw "Camera runtime exited with code $LASTEXITCODE." }
    } finally {
        Pop-Location
    }
} finally {
    foreach ($name in $names) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], "Process")
    }
    $sourceApiKey = $null
    $secrets = $null
}
