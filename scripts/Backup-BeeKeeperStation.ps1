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
$stateItem = Get-Item -LiteralPath $StateRoot -Force
if ($stateItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw "StateRoot must not be a symbolic link or reparse point."
}
$StateRoot = $stateItem.FullName
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

function Assert-RestrictedDirectoryAcl([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Backup directory must not be a symbolic link or reparse point."
    }
    $acl = Get-Acl -LiteralPath $Path
    $currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $systemSid = "S-1-5-18"
    $administratorsSid = "S-1-5-32-544"
    $ownerSid = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($ownerSid -ne $currentSid) {
        throw "Backup directory ACL owner must be the current Windows user."
    }
    $allowedSids = @($currentSid, $systemSid, $administratorsSid)
    $rightsBySid = @{}
    $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
    if ($rules.Count -eq 0) { throw "Backup directory ACL contains no access rules." }
    foreach ($rule in $rules) {
        $sid = $rule.IdentityReference.Value
        if (($allowedSids -notcontains $sid) -or $rule.AccessControlType.ToString() -ne "Allow") {
            throw "Backup directory ACL contains an unexpected principal or deny rule."
        }
        $rights = [int]$rule.FileSystemRights
        if ($rights -lt 0 -or (($rights -band 0x1F01FF) -ne $rights)) {
            throw "Backup directory ACL contains unexpected filesystem rights."
        }
        if (-not $rightsBySid.ContainsKey($sid)) { $rightsBySid[$sid] = 0 }
        $rightsBySid[$sid] = $rightsBySid[$sid] -bor $rights
    }
    foreach ($sid in @($currentSid, $systemSid)) {
        if (-not $rightsBySid.ContainsKey($sid) -or
            (($rightsBySid[$sid] -band 0x1F01FF) -ne 0x1F01FF)) {
            throw "Current user and SYSTEM must have FullControl on backup directories."
        }
    }
    if ($rightsBySid.ContainsKey($administratorsSid) -and
        (($rightsBySid[$administratorsSid] -band 0x1F01FF) -ne 0x1F01FF)) {
        throw "Administrators ACL must be FullControl when present."
    }
}

# Verify the actual NTFS DACL before creating any snapshot or staging file.
$statePrefix = [IO.Path]::GetFullPath($StateRoot).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$backupCandidate = [IO.Path]::GetFullPath($BackupRoot)
if (-not $backupCandidate.StartsWith($statePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "BackupRoot must be inside the protected StateRoot directory."
}
Assert-RestrictedDirectoryAcl -Path $StateRoot
if (Test-Path -LiteralPath $backupCandidate) {
    $existingBackupRoot = Get-Item -LiteralPath $backupCandidate -Force
    if ($existingBackupRoot.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "BackupRoot must not be a symbolic link or reparse point."
    }
}
New-Item -ItemType Directory -Path $backupCandidate -Force | Out-Null
$BackupRoot = (Resolve-Path -LiteralPath $backupCandidate).Path
if (-not [string]::Equals($BackupRoot, $backupCandidate, [StringComparison]::OrdinalIgnoreCase)) {
    throw "BackupRoot resolved through a symbolic link or reparse point."
}
Assert-RestrictedDirectoryAcl -Path $BackupRoot

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
    Assert-RestrictedDirectoryAcl -Path $stagingDir
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
    Assert-RestrictedDirectoryAcl -Path $backupDir

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
