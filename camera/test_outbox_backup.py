import os
import subprocess
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from camera.outbox import SQLiteOutbox
from camera.outbox_backup import backup, verify, restore, OutboxBackupError


def _restrict_windows_test_directory(path: Path) -> None:
    if os.name != "nt":
        return
    script = r"""
$ErrorActionPreference = 'Stop'
$path = $env:BEEKEEPER_TEST_BACKUP_PATH
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
Set-Acl -LiteralPath $path -AclObject $acl
"""
    environment = os.environ.copy()
    environment["BEEKEEPER_TEST_BACKUP_PATH"] = str(path)
    system_root = environment.get("SystemRoot", r"C:\Windows")
    program_files = environment.get("ProgramFiles", r"C:\Program Files")
    environment["PSModulePath"] = os.pathsep.join((
        os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "Modules"),
        os.path.join(program_files, "WindowsPowerShell", "Modules"),
    ))
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
    )


class OutboxBackupTests(unittest.TestCase):
    def test_backup_verify_restore_to_new_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _restrict_windows_test_directory(root)
            source = root / "source.sqlite3"
            box = SQLiteOutbox(str(source))
            event = {"id":"evt-1","observed_at":"2026-11-20T00:00:00Z","station_id":"station-1","species":"vespa_candidate","confidence":0.8,"prey_detected":False}
            box.enqueue(event)
            backup_path = backup(source, root / "backup.sqlite3")
            verify(backup_path)
            restored = restore(backup_path, root / "restore.sqlite3")
            self.assertEqual(SQLiteOutbox(str(restored)).pending(10), [event])
            with self.assertRaises(OutboxBackupError):
                restore(backup_path, restored)

    def test_backup_restore_preserves_detection_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _restrict_windows_test_directory(root)
            source = root / "source.sqlite3"
            box = SQLiteOutbox(str(source))
            first = {"id":"first","observed_at":"2026-11-20T00:00:00Z","station_id":"station-1","species":"vespa_velutina_candidate","confidence":0.8,"prey_detected":False}
            box.enqueue_if_due(first, cooldown_seconds=30, now_epoch=1000)

            saved = backup(source, root / "camera-backup.sqlite3")
            restored_path = restore(saved, root / "camera-restored.sqlite3")
            restored = SQLiteOutbox(str(restored_path))

            during_cooldown = dict(first, id="second")
            self.assertFalse(restored.enqueue_if_due(
                during_cooldown, cooldown_seconds=30, now_epoch=1029
            ))
            after_cooldown = dict(first, id="third")
            self.assertTrue(restored.enqueue_if_due(
                after_cooldown, cooldown_seconds=30, now_epoch=1030
            ))
            self.assertEqual(
                [item["id"] for item in restored.pending(10)],
                ["first", "third"],
            )

    def test_refuses_wrong_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            wrong = Path(tmp) / "wrong.sqlite3"
            import sqlite3
            with closing(sqlite3.connect(wrong)) as db:
                with db:
                    db.execute("CREATE TABLE not_outbox(value TEXT)")
            with self.assertRaises(OutboxBackupError):
                verify(wrong)


if __name__ == "__main__":
    unittest.main()
