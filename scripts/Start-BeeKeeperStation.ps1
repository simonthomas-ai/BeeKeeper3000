#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$MonitorRepo = "",
    [string]$PythonExe = "python",
    [string]$NodeExe = "node",
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "BeeKeeper3000"),
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "This launcher is for Windows PowerShell. Use the documented Linux service setup on Linux."
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

$requiredFiles = @(
    (Join-Path $repoRoot "network\source_api.py"),
    (Join-Path $repoRoot "monitor-bridge\bridge.mjs"),
    (Join-Path $MonitorRepo "integrations\local_ingest.py")
)
foreach ($file in $requiredFiles) {
    if (-not (Test-Path $file -PathType Leaf)) { throw "Required module is missing: $file" }
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
    $pythonMinor = [int]$Matches[1]
} else {
    throw "Could not read Python version: $pythonVersionText"
}
if ($pythonMinor -lt 11) { throw "Python 3.11 or newer is required; found $pythonVersionText" }
$nodeVersionText = (& $nodePath --version 2>&1 | Select-Object -First 1).ToString()
if ($nodeVersionText -match "^v(\d+)\.") {
    $nodeMajor = [int]$Matches[1]
} else {
    throw "Could not read Node.js version: $nodeVersionText"
}
if ($nodeMajor -lt 20) { throw "Node.js 20 or newer is required; found $nodeVersionText" }

if ($ValidateOnly) {
    Write-Host "Prerequisite validation passed."
    Write-Host "BeeKeeper3000: $repoRoot"
    Write-Host "Beekeeper-Monitor: $MonitorRepo"
    Write-Host "$pythonVersionText; Node $nodeVersionText"
    Write-Host "No secrets were created and no services were started."
    exit 0
}

# All persistent local data and logs are restricted to the current Windows
# user and SYSTEM. SecureString values exported by Windows PowerShell are
# protected with current-user DPAPI rather than stored as plaintext.
New-Item -ItemType Directory -Path $StateRoot -Force | Out-Null
$StateRoot = (Resolve-Path $StateRoot).Path
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
New-Item -ItemType Directory -Path $dataRoot,$logsRoot,$processRoot -Force | Out-Null

$secretPath = Join-Path $StateRoot "station-secrets.clixml"
function New-RandomSecret {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($bytes)
}
function ConvertTo-PlainText([Security.SecureString]$Value) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}
if (-not (Test-Path $secretPath)) {
    $secrets = [pscustomobject]@{
        SourceApiKey = ConvertTo-SecureString (New-RandomSecret) -AsPlainText -Force
        CursorSecret = ConvertTo-SecureString (New-RandomSecret) -AsPlainText -Force
        MonitorToken = ConvertTo-SecureString (New-RandomSecret) -AsPlainText -Force
    }
    $secrets | Export-Clixml -LiteralPath $secretPath
}
$secrets = Import-Clixml -LiteralPath $secretPath
foreach ($name in @("SourceApiKey","CursorSecret","MonitorToken")) {
    if (-not ($secrets.PSObject.Properties.Name -contains $name) -or
        -not ($secrets.$name -is [Security.SecureString])) {
        throw "DPAPI secret file is invalid. Do not delete it while a bridge cursor checkpoint is in use."
    }
}
$sourceApiKey = ConvertTo-PlainText $secrets.SourceApiKey
$cursorSecret = ConvertTo-PlainText $secrets.CursorSecret
$monitorToken = ConvertTo-PlainText $secrets.MonitorToken

function Start-StationProcess {
    param(
        [string]$Name,
        [string]$Executable,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [string]$CommandMarker
    )
    $metadataPath = Join-Path $processRoot ($Name + ".json")
    if (Test-Path $metadataPath) {
        try {
            $old = Get-Content -Raw -LiteralPath $metadataPath | ConvertFrom-Json
            $existing = Get-CimInstance Win32_Process -Filter ("ProcessId = " + [int]$old.pid) -ErrorAction SilentlyContinue
            if ($existing -and $existing.ExecutablePath -and
                [string]::Equals($existing.ExecutablePath, $old.executable, [StringComparison]::OrdinalIgnoreCase) -and
                $existing.CommandLine -like ("*" + [string]$old.marker + "*")) {
                throw "$Name is already running (PID $($old.pid)). Use Stop-BeeKeeperStation.ps1 first."
            }
        } catch {
            if ($_.Exception.Message -like "$Name is already running*") { throw }
        }
        Remove-Item -LiteralPath $metadataPath -Force
    }

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $stdout = Join-Path $logsRoot ($Name + "-" + $stamp + ".stdout.log")
    $stderr = Join-Path $logsRoot ($Name + "-" + $stamp + ".stderr.log")
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    Start-Sleep -Milliseconds 700
    if ($process.HasExited) {
        $tail = ""
        if (Test-Path $stderr) { $tail = (Get-Content -Tail 20 -LiteralPath $stderr -ErrorAction SilentlyContinue) -join [Environment]::NewLine }
        throw "$Name exited immediately (code $($process.ExitCode)). Inspect $stderr. $tail"
    }
    [pscustomobject]@{
        name = $Name
        pid = $process.Id
        executable = $Executable
        marker = $CommandMarker
        started_utc = [DateTime]::UtcNow.ToString("o")
        stdout = $stdout
        stderr = $stderr
    } | ConvertTo-Json | Set-Content -LiteralPath $metadataPath -Encoding UTF8
    return [pscustomobject]@{ Name = $Name; Process = $process }
}

$environmentNames = @(
    "VESPAGUARD_INGEST_TOKEN","VESPAGUARD_INGEST_DB","VESPAGUARD_RETENTION_DAYS",
    "HORNET3000_API_KEY","HORNET3000_CURSOR_SECRET","HORNET3000_EVENT_DB",
    "HORNET3000_EVENT_RETENTION_DAYS","HORNET3000_EVENT_MAX_ROWS","HORNET3000_URL",
    "BEEKEEPER_MONITOR_INGEST_URL","BEEKEEPER_MONITOR_INGEST_TOKEN",
    "POLL_INTERVAL_MS","BRIDGE_REQUIRE_CURSOR","BRIDGE_STATE_FILE"
)
$previousEnvironment = @{}
foreach ($name in $environmentNames) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}
$started = @()
try {
    [Environment]::SetEnvironmentVariable("VESPAGUARD_INGEST_TOKEN", $monitorToken, "Process")
    [Environment]::SetEnvironmentVariable("VESPAGUARD_INGEST_DB", (Join-Path $dataRoot "monitor-events.sqlite3"), "Process")
    [Environment]::SetEnvironmentVariable("VESPAGUARD_RETENTION_DAYS", "90", "Process")
    $started += Start-StationProcess -Name "monitor" -Executable $pythonPath -Arguments @("-m","integrations.local_ingest") -WorkingDirectory $MonitorRepo -CommandMarker "integrations.local_ingest"

    [Environment]::SetEnvironmentVariable("HORNET3000_API_KEY", $sourceApiKey, "Process")
    [Environment]::SetEnvironmentVariable("HORNET3000_CURSOR_SECRET", $cursorSecret, "Process")
    [Environment]::SetEnvironmentVariable("HORNET3000_EVENT_DB", (Join-Path $dataRoot "source-events.sqlite3"), "Process")
    [Environment]::SetEnvironmentVariable("HORNET3000_EVENT_RETENTION_DAYS", "30", "Process")
    [Environment]::SetEnvironmentVariable("HORNET3000_EVENT_MAX_ROWS", "250000", "Process")
    $started += Start-StationProcess -Name "source-api" -Executable $pythonPath -Arguments @("-m","network.source_api") -WorkingDirectory $repoRoot -CommandMarker "network.source_api"

    [Environment]::SetEnvironmentVariable("HORNET3000_URL", "http://127.0.0.1:8787", "Process")
    [Environment]::SetEnvironmentVariable("BEEKEEPER_MONITOR_INGEST_URL", "http://127.0.0.1:8765/api/v1/events", "Process")
    [Environment]::SetEnvironmentVariable("BEEKEEPER_MONITOR_INGEST_TOKEN", $monitorToken, "Process")
    [Environment]::SetEnvironmentVariable("POLL_INTERVAL_MS", "10000", "Process")
    [Environment]::SetEnvironmentVariable("BRIDGE_REQUIRE_CURSOR", "true", "Process")
    [Environment]::SetEnvironmentVariable("BRIDGE_STATE_FILE", (Join-Path $dataRoot "bridge-state.json"), "Process")
    $started += Start-StationProcess -Name "bridge" -Executable $nodePath -Arguments @("monitor-bridge/bridge.mjs") -WorkingDirectory $repoRoot -CommandMarker "monitor-bridge/bridge.mjs"

    $ready = $false
    for ($attempt = 1; $attempt -le 20; $attempt++) {
        try {
            $source = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8787/api/events?limit=1&cursor=start" -Headers @{ "X-API-Key" = $sourceApiKey } -TimeoutSec 3
            if (-not ($source.PSObject.Properties.Name -contains "events") -or
                -not ($source.PSObject.Properties.Name -contains "next_cursor") -or
                -not ($source.PSObject.Properties.Name -contains "has_more")) {
                throw "Source API did not return a cursor page."
            }
            $null = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8765/" -TimeoutSec 3
            $null = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8765/api/v1/events?limit=1" -Headers @{ Authorization = "Bearer $monitorToken" } -TimeoutSec 3
            $ready = $true
            break
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $ready) { throw "Local health checks failed. Inspect the restricted logs under $logsRoot." }

    Write-Host "BeeKeeper local services started and health-checked."
    Write-Host "Monitor PWA: http://127.0.0.1:8765/"
    Write-Host "Source API:  http://127.0.0.1:8787/ (loopback only)"
    Write-Host "Bridge:      running with cursor mode required."
    Write-Host "Private data: $dataRoot"
    Write-Host "Restricted logs: $logsRoot"
    Write-Host "Stop with: .\scripts\Stop-BeeKeeperStation.ps1"
    Write-Host "No camera/AI producer or radio hardware is started by this launcher."
} catch {
    foreach ($service in ($started | Select-Object -Reverse)) {
        try { Stop-Process -Id $service.Process.Id -Force -ErrorAction SilentlyContinue } catch {}
        $metadataPath = Join-Path $processRoot ($service.Name + ".json")
        if (Test-Path $metadataPath) { Remove-Item -LiteralPath $metadataPath -Force -ErrorAction SilentlyContinue }
    }
    throw
} finally {
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], "Process")
    }
}
