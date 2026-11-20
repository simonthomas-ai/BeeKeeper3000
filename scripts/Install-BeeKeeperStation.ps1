#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$MonitorRepo = "",
    [string]$PythonExe = "python",
    [string]$NodeExe = "node",
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "BeeKeeper3000"),
    [switch]$WithCamera,
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "This installer targets Windows 10/11. Use the documented Linux setup on Linux."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($MonitorRepo)) {
    $sibling = Join-Path (Split-Path -Parent $repoRoot) "Beekeeper-Monitor"
    if (Test-Path (Join-Path $sibling "integrations\local_ingest.py")) {
        $MonitorRepo = $sibling
    } elseif ($env:BEEKEEPER_MONITOR_REPO) {
        $MonitorRepo = $env:BEEKEEPER_MONITOR_REPO
    } else {
        throw "Set -MonitorRepo to the local Beekeeper-Monitor checkout path."
    }
}
$MonitorRepo = (Resolve-Path $MonitorRepo).Path
foreach ($file in @(
    (Join-Path $repoRoot "network\source_api.py"),
    (Join-Path $repoRoot "monitor-bridge\bridge.mjs"),
    (Join-Path $MonitorRepo "integrations\local_ingest.py"),
    (Join-Path $repoRoot "camera\requirements.txt")
)) {
    if (-not (Test-Path $file -PathType Leaf)) { throw "Required project file is missing: $file" }
}

function Resolve-Executable([string]$Name) {
    $command = Get-Command -Name $Name -CommandType Application -ErrorAction Stop | Select-Object -First 1
    if (-not $command) { throw "Executable not found: $Name" }
    return $command.Path
}

$pythonPath = Resolve-Executable $PythonExe
$nodePath = Resolve-Executable $NodeExe
$pythonVersionText = (& $pythonPath --version 2>&1 | Select-Object -First 1).ToString()
if ($pythonVersionText -match "Python 3\.(\d+)") {
    if ([int]$Matches[1] -lt 11) { throw "Python 3.11 or newer is required; found $pythonVersionText" }
} else { throw "Could not read Python version: $pythonVersionText" }
$nodeVersionText = (& $nodePath --version 2>&1 | Select-Object -First 1).ToString()
if ($nodeVersionText -match "^v(\d+)\.") {
    if ([int]$Matches[1] -lt 20) { throw "Node.js 20 or newer is required; found $nodeVersionText" }
} else { throw "Could not read Node.js version: $nodeVersionText" }

if ($ValidateOnly) {
    Write-Host "Installer prerequisite validation passed."
    Write-Host "BeeKeeper3000: $repoRoot"
    Write-Host "Beekeeper-Monitor: $MonitorRepo"
    Write-Host "$pythonVersionText; Node $nodeVersionText"
    Write-Host "No files, secrets, virtual environments or services were created."
    exit 0
}

New-Item -ItemType Directory -Path $StateRoot -Force | Out-Null
$StateRoot = (Resolve-Path $StateRoot).Path

# Restrict the persistent station state to the current user and SYSTEM.
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetOwner($identity)
$acl.SetAccessRuleProtection($true, $false)
$userRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    $identity, "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow"
)
$systemSid = New-Object System.Security.Principal.SecurityIdentifier("S-1-5-18")
$systemRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    $systemSid, "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow"
)
$acl.SetAccessRule($userRule)
$acl.AddAccessRule($systemRule)
Set-Acl -LiteralPath $StateRoot -AclObject $acl

$dataRoot = Join-Path $StateRoot "data"
$logsRoot = Join-Path $StateRoot "logs"
$processRoot = Join-Path $StateRoot "processes"
$venvRoot = Join-Path $StateRoot "venv"
New-Item -ItemType Directory -Path $dataRoot,$logsRoot,$processRoot -Force | Out-Null

$venvPython = Join-Path $venvRoot "Scripts\python.exe"
if (-not (Test-Path $venvPython -PathType Leaf)) {
    & $pythonPath -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) { throw "Could not create the private station Python virtual environment." }
}
if (-not (Test-Path $venvPython -PathType Leaf)) {
    throw "Virtual environment was not created at $venvPython"
}

& $venvPython -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
    & $venvPython -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) { throw "pip is not available in the station virtual environment." }
}

if ($WithCamera) {
    Push-Location $repoRoot
    try {
        & $venvPython -m pip install --disable-pip-version-check --no-input --only-binary=:all: -r "camera\requirements.txt"
        if ($LASTEXITCODE -ne 0) { throw "Could not install pinned camera direct dependencies." }
        & $venvPython -c "import cv2, onnxruntime; print('OpenCV', cv2.__version__, 'ONNX Runtime', onnxruntime.__version__, 'providers', onnxruntime.get_available_providers())"
        if ($LASTEXITCODE -ne 0) { throw "Camera runtime dependency verification failed." }
    } finally { Pop-Location }
}

& $venvPython -m pip check
if ($LASTEXITCODE -ne 0) { throw "Python dependency consistency check failed." }

Write-Host ""
Write-Host "BeeKeeper station environment installed."
Write-Host "Python environment: $venvPython"
Write-Host "Node.js runtime: $nodePath"
Write-Host "Protected station data: $StateRoot"
Write-Host ""
Write-Host "Start the local services:"
Write-Host ('.\scripts\Start-BeeKeeperStation.ps1 -MonitorRepo "' + $MonitorRepo + '" -PythonExe "' + $venvPython + '" -NodeExe "' + $nodePath + '"')
if ($WithCamera) {
    Write-Host ""
    Write-Host "Camera dependencies installed. Start camera separately after the base station and an independently rights-reviewed model are ready:"
    Write-Host ('.\scripts\Start-BeeKeeperCamera.ps1 -ModelManifest "<private-manifest.json>" -CameraSource "<camera-index-or-URL>" -StationId "station-01" -PythonExe "' + $venvPython + '"')
} else {
    Write-Host "Camera is optional. Re-run with -WithCamera to install its CPU inference dependencies."
}
Write-Host "No camera, radio, model or service was started by this installer."
