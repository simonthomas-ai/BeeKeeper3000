import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from network.backup_permissions import assert_private_directory


class BackupPermissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_windows_acl_accepts_current_user_system_and_optional_admin(self):
        current = "S-1-5-21-111-222-333-1001"
        full = 0x1F01FF
        payload = {
            "owner_sid": current,
            "current_user_sid": current,
            "rules": [
                {"sid": current, "type": "Allow", "rights": full},
                {"sid": "S-1-5-18", "type": "Allow", "rights": full},
                {"sid": "S-1-5-32-544", "type": "Allow", "rights": full},
            ],
        }
        result = CompletedProcess([], 0, json.dumps(payload), "")
        with patch("network.backup_permissions.os.name", "nt"):
            with patch("network.backup_permissions.subprocess.run", return_value=result) as run:
                assert_private_directory(self.directory)
        self.assertEqual(
            run.call_args.kwargs["env"]["BEEKEEPER_BACKUP_ACL_PATH"],
            str(self.directory),
        )

    def test_windows_acl_rejects_broad_group_and_deny_aces(self):
        current = "S-1-5-21-111-222-333-1001"
        full = 0x1F01FF
        for unsafe in (
            {"sid": "S-1-5-32-545", "type": "Allow", "rights": 1179817},
            {"sid": "S-1-5-11", "type": "Deny", "rights": full},
        ):
            payload = {
                "owner_sid": current,
                "current_user_sid": current,
                "rules": [
                    {"sid": current, "type": "Allow", "rights": full},
                    {"sid": "S-1-5-18", "type": "Allow", "rights": full},
                    unsafe,
                ],
            }
            result = CompletedProcess([], 0, json.dumps(payload), "")
            with patch("network.backup_permissions.os.name", "nt"):
                with patch("network.backup_permissions.subprocess.run", return_value=result):
                    with self.assertRaises(PermissionError):
                        assert_private_directory(self.directory)

    def test_windows_acl_fails_closed_without_powershell(self):
        with patch("network.backup_permissions.os.name", "nt"):
            with patch("network.backup_permissions.subprocess.run", side_effect=FileNotFoundError):
                with self.assertRaises(PermissionError):
                    assert_private_directory(self.directory)


if __name__ == "__main__":
    unittest.main()
