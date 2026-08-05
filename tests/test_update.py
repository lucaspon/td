from __future__ import annotations

import io
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from td.__main__ import _run_update, _source_checkout, _source_version


def _completed(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


class SourceCheckoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.checkout = self.root / "src-checkout"
        (self.checkout / ".git").mkdir(parents=True)
        self.tool_dir = self.root / "tools"
        (self.tool_dir / "td-task").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_receipt(self, body: str) -> None:
        (self.tool_dir / "td-task" / "uv-receipt.toml").write_text(body, encoding="utf-8")

    def _tool_dir_call(self, *args, **kwargs):
        return _completed(args, stdout=f"{self.tool_dir}\n")

    def test_detects_directory_install(self) -> None:
        self._write_receipt(
            f'[tool]\nrequirements = [{{ name = "td-task", directory = "{self.checkout}" }}]\n'
        )
        with patch("subprocess.run", side_effect=self._tool_dir_call):
            self.assertEqual(_source_checkout(), str(self.checkout))

    def test_pypi_install_has_no_checkout(self) -> None:
        self._write_receipt('[tool]\nrequirements = [{ name = "td-task" }]\n')
        with patch("subprocess.run", side_effect=self._tool_dir_call):
            self.assertIsNone(_source_checkout())

    def test_directory_without_git_is_ignored(self) -> None:
        plain = self.root / "not-a-repo"
        plain.mkdir()
        self._write_receipt(
            f'[tool]\nrequirements = [{{ name = "td-task", directory = "{plain}" }}]\n'
        )
        with patch("subprocess.run", side_effect=self._tool_dir_call):
            self.assertIsNone(_source_checkout())

    def test_missing_receipt_returns_none(self) -> None:
        with patch("subprocess.run", side_effect=self._tool_dir_call):
            self.assertIsNone(_source_checkout())

    def test_source_version_read_from_pyproject(self) -> None:
        (self.checkout / "pyproject.toml").write_text(
            '[project]\nname = "td-task"\nversion = "9.9.9"\n', encoding="utf-8"
        )
        self.assertEqual(_source_version(str(self.checkout)), "9.9.9")

    def test_source_version_missing_pyproject(self) -> None:
        self.assertIsNone(_source_version(str(self.checkout)))


class RunUpdateTests(unittest.TestCase):
    def test_source_install_pulls_before_rebuilding(self) -> None:
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            return _completed(args)

        with patch("td.__main__._source_checkout", return_value="/repo"), \
                patch("td.__main__._source_version", return_value="0.3.0"), \
                patch("td.__main__._print_changelog"), \
                patch("importlib.metadata.version", return_value="0.2.9"), \
                patch("subprocess.run", side_effect=fake_run), \
                redirect_stdout(io.StringIO()):
            _run_update()

        self.assertEqual(calls[0], ["git", "-C", "/repo", "pull", "--ff-only"])
        self.assertEqual(calls[1], ["uv", "tool", "upgrade", "td-task", "--reinstall"])

    def test_source_install_skips_rebuild_when_current(self) -> None:
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            return _completed(args)

        buffer = io.StringIO()
        with patch("td.__main__._source_checkout", return_value="/repo"), \
                patch("td.__main__._source_version", return_value="0.2.9"), \
                patch("importlib.metadata.version", return_value="0.2.9"), \
                patch("subprocess.run", side_effect=fake_run), \
                redirect_stdout(buffer):
            _run_update()

        self.assertEqual(calls, [["git", "-C", "/repo", "pull", "--ff-only"]])
        self.assertIn("already up-to-date", buffer.getvalue())

    def test_failed_pull_aborts_without_rebuilding(self) -> None:
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            return _completed(args, returncode=1, stderr="divergent branches")

        buffer = io.StringIO()
        with patch("td.__main__._source_checkout", return_value="/repo"), \
                patch("subprocess.run", side_effect=fake_run), \
                redirect_stdout(buffer):
            with self.assertRaises(SystemExit):
                _run_update()

        self.assertEqual(calls, [["git", "-C", "/repo", "pull", "--ff-only"]])
        self.assertIn("divergent branches", buffer.getvalue())

    def test_pypi_install_upgrades_without_pull(self) -> None:
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            return _completed(args, stdout="Nothing to upgrade")

        with patch("td.__main__._source_checkout", return_value=None), \
                patch("subprocess.run", side_effect=fake_run), \
                redirect_stdout(io.StringIO()):
            _run_update()

        self.assertEqual(calls, [["uv", "tool", "upgrade", "td-task"]])


if __name__ == "__main__":
    unittest.main()
