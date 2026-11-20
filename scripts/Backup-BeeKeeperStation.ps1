#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$MonitorRepo = "",
    [string]$PythonExe = "python",
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "BeeKeeper3000"),
    [string]$BackupRoot = (Join-Path $env:LOCALAPPDATA "BeeKeeper3000\backups")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "This backup runner is for Windows PowerShell. Use the Python backup modules on other platforms."
}
if (-not (Test-Path $StateRoot -PathType Container)) {
    throw "Station state directory not found: $StateRoot. Start BeeKeeper3000 once before backing it up."
}
$StateRoot = (Resolve-Path $StateRoot).Path
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ([string]::IsNullOrWhiteSpace($MonitorRepo)) {
    $sibling = Join-Path (Split-Path -Parent $repoRoot) "Beekeeper-Monitor"
    if (Test-Path (Join-Path $sibling "integrations\store_backup.py")) {
        $MonitorRepo = $sibling
    } elseif ($env:BEEKEEPER_MONITOR_REPO) {
        $MonitorRepo = $env:BEEKEEPER_MONITOR_REPO
    } else {
        throw "Set -MonitorRepo to the local Beekeeper-Monitor checkout path."
    }
}
$MonitorRepo = (Resolve-Path $MonitorRepo).Path
$pythonCommand = Get-Command -Name $PythonExe -CommandType Application -ErrorAction Stop | Select-Object -First 1
if (-not $pythonCommand) { throw "Python executable not found: $PythonExe" }
$pythonPath = $pythonCommand.Path

# Keep backups inside the installer's restricted state directory so the
# current-user/SYSTEM NTFS ACL is inherited rather than silently weakened.
New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
$BackupRoot = (Resolve-Path $BackupRoot).Path
$statePrefix = $StateRoot.TrimEnd('\') + '\'
if (-not $BackupRoot.StartsWith($statePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "BackupRoot must be inside the protected StateRoot directory."
}

$dataRoot = Join-Path $StateRoot "data"
$sourceDb = Join-Path $dataRoot "source-events.sqlite3"
$monitorDb = Join-Path $dataRoot "monitor-events.sqlite3"
$bridgeState = Join-Path $dataRoot "bridge-state.json"
$cameraOutbox = Join-Path $dataRoot "camera-outbox.sqlite3"
if (-not (Test-Path $sourceDb -PathType Leaf)) { throw "BeeKeeper source database not found: $sourceDb" }
if (-not (Test-Path $monitorDb -PathType Leaf)) { throw "Monitor database not found: $monitorDb" }
if (-not (Test-Path (Join-Path $MonitorRepo "integrations\store_backup.py") -PathType Leaf)) {
    throw "Monitor backup module is missing from $MonitorRepo"
}

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$stagingDir = Join-Path $BackupRoot (".$stamp.partial")
$backupDir = Join-Path $BackupRoot $stamp
if (Test-Path $backupDir) { throw "Backup destination already exists: $backupDir" }
New-Item -ItemType Directory -Path $stagingDir -ErrorAction Stop | Out-Null

try {
    $sourceBackup = Join-Path $stagingDir "source-events.sqlite3"
    $monitorBackup = Join-Path $stagingDir "monitor-events.sqlite3"
    $bridgeBackup = Join-Path $stagingDir "bridge-state.json"
    $cameraBackup = Join-Path $stagingDir "camera-outbox.sqlite3"

    Push-Location $repoRoot
    try {
        & $pythonPath -m network.source_backup backup --source $sourceDb --destination $sourceBackup
        if ($LASTEXITCODE -ne 0) { throw "BeeKeeper source-journal backup failed with exit code $LASTEXITCODE." }
    } finally {
        Pop-Location
    }

    Push-Location $MonitorRepo
    try {
        & $pythonPath -m integrations.store_backup backup --source $monitorDb --destination $monitorBackup
        if ($LASTEXITCODE -ne 0) { throw "Monitor database backup failed with exit code $LASTEXITCODE." }
    } finally {
        Pop-Location
    }

    if (Test-Path $cameraOutbox -PathType Leaf) {
        Push-Location $repoRoot
        try {
            & $pythonPath -m camera.outbox_backup backup --source $cameraOutbox --destination $cameraBackup
            if ($LASTEXITCODE -ne 0) { throw "Camera outbox backup failed with exit code $LASTEXITCODE." }
        } finally {
            Pop-Location
        }
    }

    $files = @(
        [pscustomobject]@{ name = "source-events.sqlite3"; path = $sourceBackup },
        [pscustomobject]@{ name = "monitor-events.sqlite3"; path = $monitorBackup }
    )
    if (Test-Path $cameraBackup -PathType Leaf) {
        $files += [pscustomobject]@{ name = "camera-outbox.sqlite3"; path = $cameraBackup }
    }
    if (Test-Path $bridgeState -PathType Leaf) {
        # Bridge state is published with write+fsync+atomic rename; copy a complete
        # old or new version and validate the copied JSON before including it.
        Copy-Item -LiteralPath $bridgeState -Destination $bridgeBackup -ErrorAction Stop
        $state = Get-Content -Raw -LiteralPath $bridgeBackup | ConvertFrom-Json
        if ($state.version -ne 2 -or $state.forwardedIds -isnot [System.Array] -or
            ($null -ne $state.cursor -and $state.cursor -isnot [string])) {
            throw "Copied bridge checkpoint is invalid; backup set is not complete."
        }
        $files += [pscustomobject]@{ name = "bridge-state.json"; path = $bridgeBackup }
    } else {
        Write-Warning "Bridge checkpoint does not exist yet; this backup set contains databases only."
    }

    $manifest = [ordered]@{
        format = 1
        created_utc = [DateTime]::UtcNow.ToString("o")
        contents = @($files | ForEach-Object {
            [ordered]@{
                file = $_.name
                sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.path).Hash.ToLowerInvariant()
                bytes = (Get-Item -LiteralPath $_.path).Length
            }
        })
        notes = @(
            "Database snapshots were created with SQLite online backup APIs and integrity checks.",
            "Bridge checkpoint is copied only when present and schema-valid.",
            "Camera outbox is copied only when present and schema-valid.",
            "DPAPI station secrets are not included and are not portable to another Windows user or host.",
            "Backups contain sensitive station metadata; protect this directory with NTFS ACLs and BitLocker."
        )
    }
    $manifestPath = Join-Path $stagingDir "manifest.json"
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8 -NoNewline
    Move-Item -LiteralPath $stagingDir -Destination $backupDir -ErrorAction Stop

    Write-Host "BeeKeeper station backup completed and verified."
    Write-Host "Backup directory: $backupDir"
    Write-Host "Included: $($files.name -join ', ')"
    Write-Host "Manifest: $(Join-Path $backupDir 'manifest.json')"
    Write-Host "No live database, service, bridge checkpoint or secret was modified."
} catch {
    if (Test-Path $stagingDir) {
        Remove-Item -LiteralPath $stagingDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    throw
}
