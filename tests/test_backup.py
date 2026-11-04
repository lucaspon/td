from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from td import backup, config


class BackupTests(unittest.TestCase):
    def test_encrypt_round_trip_hides_plaintext(self) -> None:
        source = json.dumps({"tasks": [{"text": "secret task"}]})

        encrypted = backup.encrypt_backup(source, "backup-password")

        self.assertNotIn("secret task", encrypted)
        self.assertEqual(backup.decrypt_backup(encrypted, "backup-password"), source)

    def test_wrong_password_fails(self) -> None:
        encrypted = backup.encrypt_backup('{"secret": true}', "backup-password")

        with self.assertRaisesRegex(ValueError, "Invalid backup password"):
            backup.decrypt_backup(encrypted, "wrong-password")

    def test_plain_backup_decodes_without_password(self) -> None:
        source = '{"tasks": [{"text": "visible task"}]}'

        self.assertFalse(backup.is_encrypted_backup(source))
        self.assertEqual(backup.decode_backup(source), source)

    def test_auto_sync_can_use_plaintext_config_mode(self) -> None:
        config_file = self._write_config(
            '[github_backup]\nauto_sync = true\nrepo = "alice/td-backup"\nencrypt = false\n'
        )
        source = '{"tasks": [{"text": "visible task"}]}'
        with (
            patch.dict(os.environ, {"TD_CONFIG_PATH": str(config_file)}),
            patch.object(backup, "upload_backup", return_value="alice/td-backup") as upload,
        ):
            result = backup.sync_if_configured(source)

        self.assertEqual(result, "alice/td-backup")
        self.assertEqual(upload.call_args.args, ("alice/td-backup", source))

    def test_auto_sync_skips_unchanged_export(self) -> None:
        source = '{"tasks": [{"text": "unchanged"}]}'
        digest = backup.backup_digest(source, encrypted=False)
        config_file = self._write_config(
            f'[github_backup]\nauto_sync = true\nrepo = "alice/td-backup"\nencrypt = false\nlast_sync_digest = "{digest}"\n'
        )
        with (
            patch.dict(os.environ, {"TD_CONFIG_PATH": str(config_file)}),
            patch.object(backup, "upload_backup") as upload,
        ):
            result = backup.sync_if_configured(source)

        self.assertIsNone(result)
        upload.assert_not_called()

    def _write_config(self, contents: str):
        import tempfile
        from pathlib import Path

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "config.toml"
        path.write_text(contents, encoding="utf-8")
        return path

    def test_upload_creates_private_repo_and_updates_file(self) -> None:
        responses = [
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 1, "", "not found"),
            subprocess.CompletedProcess([], 0, "https://github.com/alice/td-backup\n", ""),
            subprocess.CompletedProcess([], 0, '{"nameWithOwner":"alice/td-backup","isPrivate":true}', ""),
            subprocess.CompletedProcess([], 1, "", "HTTP 404: Not Found"),
            subprocess.CompletedProcess([], 0, '{"content":{"name":"td-backup.tdenc"}}', ""),
        ]
        with patch.object(backup, "_run_gh", side_effect=responses) as run_gh:
            repo = backup.upload_backup("alice/td-backup", '{"ciphertext":"x"}')

        self.assertEqual(repo, "alice/td-backup")
        upload_call = run_gh.call_args_list[-1]
        self.assertEqual(upload_call.args[0][-4:], ["--method", "PUT", "--input", "-"])
        body = json.loads(upload_call.kwargs["input_text"])
        self.assertEqual(body["message"], "Update encrypted td backup")
        self.assertNotIn("ciphertext", body["content"])

    def test_public_repo_is_rejected(self) -> None:
        responses = [
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, '{"nameWithOwner":"alice/public","isPrivate":false}', ""),
        ]
        with patch.object(backup, "_run_gh", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "must be private"):
                backup.upload_backup("alice/public", "encrypted")

    def test_upload_initializes_existing_empty_repo(self) -> None:
        gh_responses = iter([
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, '{"nameWithOwner":"alice/empty","isPrivate":true,"isEmpty":true}', ""),
            subprocess.CompletedProcess([], 0, "", ""),
        ])
        git_responses = iter([
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, "", ""),
        ])

        def run_gh(args: list[str], **kwargs):
            if args[:2] == ["repo", "clone"]:
                Path(args[-1]).mkdir()
            return next(gh_responses)

        with (
            patch.object(backup, "_run_gh", side_effect=run_gh),
            patch.object(backup, "_run_git", side_effect=lambda *args, **kwargs: next(git_responses)) as run_git,
        ):
            repo = backup.upload_backup("alice/empty", "encrypted")

        self.assertEqual(repo, "alice/empty")
        self.assertEqual(run_git.call_args_list[-1].args[0], ["push", "-u", "origin", "HEAD:main"])


if __name__ == "__main__":
    unittest.main()
