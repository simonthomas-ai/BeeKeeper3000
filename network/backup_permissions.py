"""Fail-closed filesystem access checks for sensitive station backups."""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path

_WINDOWS_FULL_CONTROL_MASK = 0x1F01FF
_WINDOWS_ACL_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$path = $env:BEEKEEPER_BACKUP_ACL_PATH
if ([string]::IsNullOrWhiteSpace($path)) { throw 'Backup ACL path is missing.' }
$acl = Get-Acl -LiteralPath $path
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if ($null -eq $identity.User) { throw 'Current Windows user SID is unavailable.' }
$rules = @(
    $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]) |
    ForEach-Object {
        [pscustomobject]@{
            sid = $_.IdentityReference.Value
            type = $_.AccessControlType.ToString()
            rights = [int]$_.FileSystemRights
        }
    }
)
[pscustomobject]@{
    owner_sid = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    current_user_sid = $identity.User.Value
    rules = $rules
} | ConvertTo-Json -Compress -Depth 4
"""


def _check_windows_private_directory(directory: Path) -> None:
    """Reject broad/deny NTFS ACEs and require current-user plus SYSTEM FullControl."""
    environment = os.environ.copy()
    environment["BEEKEEPER_BACKUP_ACL_PATH"] = str(directory)
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _WINDOWS_ACL_SCRIPT],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PermissionError("cannot verify Windows backup-directory ACL; refusing backup") from exc
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        summary = detail[-1][:200] if detail else "PowerShell returned an error"
        summary = re.sub(r"[A-Za-z]:\\[^\s]+", "<path>", summary)
        raise PermissionError(
            f"Windows backup-directory ACL verification failed (exit {result.returncode}): {summary}"
        )
    try:
        payload = json.loads(result.stdout.lstrip("\ufeff"))
        owner_sid = payload["owner_sid"]
        current_sid = payload["current_user_sid"]
        rules = payload["rules"]
        if isinstance(rules, dict):
            rules = [rules]
        allowed_sids = {current_sid, "S-1-5-18", "S-1-5-32-544"}
        if not isinstance(rules, list) or not rules or owner_sid not in allowed_sids:
            raise ValueError("invalid owner or ACL rules")
        rights_by_sid = {}
        for rule in rules:
            sid = rule["sid"]
            if sid not in allowed_sids or rule["type"] != "Allow":
                raise ValueError("unexpected Windows ACL principal or deny rule")
            rights = int(rule["rights"])
            if rights < 0 or rights & ~_WINDOWS_FULL_CONTROL_MASK:
                raise ValueError("unexpected Windows filesystem rights")
            rights_by_sid[sid] = rights_by_sid.get(sid, 0) | rights
        for sid in (current_sid, "S-1-5-18"):
            if rights_by_sid.get(sid, 0) & _WINDOWS_FULL_CONTROL_MASK != _WINDOWS_FULL_CONTROL_MASK:
                raise ValueError("current user and SYSTEM must have FullControl")
        if "S-1-5-32-544" in rights_by_sid and (
            rights_by_sid["S-1-5-32-544"] & _WINDOWS_FULL_CONTROL_MASK
        ) != _WINDOWS_FULL_CONTROL_MASK:
            raise ValueError("Administrators ACL must be FullControl when present")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PermissionError("Windows backup-directory ACL is not restricted to trusted principals") from exc


def assert_private_directory(path: str | os.PathLike) -> None:
    """Require a private, current-user-owned directory on supported OS families."""
    directory = path if isinstance(path, Path) else Path(path)
    if not directory.is_dir():
        raise NotADirectoryError(f"backup directory does not exist: {directory}")
    if os.name == "posix":
        info = directory.stat()
        if info.st_uid != os.getuid():
            raise PermissionError("backup directory must belong to the current service account")
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise PermissionError("backup directory must be private (POSIX mode 0700)")
        return
    if os.name == "nt":
        _check_windows_private_directory(directory)
        return
    raise PermissionError("unsupported platform; refusing an unverified backup")
