#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$MonitorRepo = "",
    [string]$PythonExe = "python",
    [string]$NodeExe = "node",
    [switch]$ValidateOnly,
    [switch]$Unregister
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$taskName = "BeeKeeper3000-Station"
if ($env:OS -ne "Windows_NT") { throw "This script is for Windows PowerShell only." }

if ($Unregister) {
    if ($ValidateOnly) {
        Write-Host "Would remove the current-user scheduled task: $taskName"
        exit 0
    }
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Removed logon startup task: $taskName"
    } else { Write-Host "Logon startup task is not registered." }
    exit 0
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($MonitorRepo)) {
    $sibling = Join-Path (Split-Path -Parent $repoRoot) "Beekeeper-Monitor"
    if (Test-Path (Join-Path $sibling "integrations\local_ingest.py")) {
        $MonitorRepo = $sibling
    } elseif ($env:BEEKEEPER_MONITOR_REPO) {
        $MonitorRepo = $env:BEEKEEPER_MONITOR_REPO
    } else { throw "Set -MonitorRepo to the local Beekeeper-Monitor checkout path." }
}
$MonitorRepo = (Resolve-Path $MonitorRepo).Path
$startScript = Join-Path $PSScriptRoot "Start-BeeKeeperStation.ps1"
if (-not (Test-Path $startScript -PathType Leaf)) { throw "Station launcher is missing: $startScript" }

$powerShellPath = Join-Path $PSHOME "powershell.exe"
$validationArguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -MonitorRepo "{1}" -PythonExe "{2}" -NodeExe "{3}" -ValidateOnly' -f $startScript, $MonitorRepo, $PythonExe, $NodeExe
$validation = Start-Process -FilePath $powerShellPath -ArgumentList $validationArguments -Wait -PassThru -NoNewWindow
if ($validation.ExitCode -ne 0) { throw "Station prerequisites did not pass validation (exit $($validation.ExitCode))." }
if ($ValidateOnly) {
    Write-Host "Logon startup task plan validated; no scheduled task was created."
    Write-Host "Task: $taskName (current user, interactive logon, 30-second delay)"
    exit 0
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$quotedStart = '"' + $startScript + '"'
$quotedMonitor = '"' + $MonitorRepo + '"'
$quotedPython = '"' + $PythonExe + '"'
$quotedNode = '"' + $NodeExe + '"'
$arguments = "-NoProfile -ExecutionPolicy Bypass -File $quotedStart -MonitorRepo $quotedMonitor -PythonExe $quotedPython -NodeExe $quotedNode"
$action = New-ScheduledTaskAction -Execute $powerShellPath -Argument $arguments -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$trigger.Delay = "PT30S"
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Starts the current user's local BeeKeeper3000 and Beekeeper-Monitor stack after interactive logon." -Force | Out-Null
Write-Host "Registered optional logon startup task: $taskName"
Write-Host "Runs as $identity after interactive logon; no admin rights or stored password are used."
Write-Host "It starts only the three base services. It does not start camera AI or MeshCore radio."
Write-Host "Remove with: .\scripts\Register-BeeKeeperStationStartup.ps1 -Unregister"
Write-Host "This task starts the stack at logon; it is not a Windows service or crash-restarting watchdog."
