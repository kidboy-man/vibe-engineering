import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.kits.cursor.installer import diff_kit, doctor, install, uninstall

EXPECTED_RULES = [
    "rules/00-persona.mdc",
    "rules/operating-model.mdc",
    "rules/go-backend-engineering.mdc",
    "rules/testing-and-verification.mdc",
    "rules/security-and-data-safety.mdc",
    "rules/database-and-operations.mdc",
    "rules/uncertainty-and-sources.mdc",
]


class CursorInstallerTests(unittest.TestCase):
    def test_install_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = install(home=tmp, dry_run=True, yes=True)
            self.assertEqual(rc, 0)
            self.assertFalse((Path(tmp) / ".cursor" / "rules").exists())

    def test_install_copies_all_rule_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = install(home=tmp, dry_run=False, yes=True)

            self.assertEqual(rc, 0)
            cursor_dir = Path(tmp) / ".cursor"
            for rel in EXPECTED_RULES:
                self.assertTrue((cursor_dir / rel).exists(), f"missing {rel}")
            self.assertTrue((cursor_dir / ".vibe-engineering-manifest.json").exists())

    def test_install_accepts_merge_settings_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = install(home=tmp, dry_run=True, yes=True, merge_settings=False)
            self.assertEqual(rc, 0)

    def test_install_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            cursor_dir = Path(tmp) / ".cursor"
            self.assertTrue((cursor_dir / "rules" / "00-persona.mdc").exists())

    def test_mdc_files_have_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            cursor_dir = Path(tmp) / ".cursor"
            for rel in EXPECTED_RULES:
                content = (cursor_dir / rel).read_text(encoding="utf-8")
                self.assertTrue(content.startswith("---\n"), f"{rel} missing frontmatter")
                self.assertIn("description:", content)

    def test_uninstall_removes_unchanged_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)

            rc = uninstall(home=tmp, dry_run=False, yes=True)

            self.assertEqual(rc, 0)
            cursor_dir = Path(tmp) / ".cursor"
            for rel in EXPECTED_RULES:
                self.assertFalse((cursor_dir / rel).exists(), f"should be removed: {rel}")
            self.assertFalse((cursor_dir / ".vibe-engineering-manifest.json").exists())

    def test_uninstall_keeps_modified_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            cursor_dir = Path(tmp) / ".cursor"
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            persona = cursor_dir / "rules" / "00-persona.mdc"
            persona.write_text(
                persona.read_text(encoding="utf-8") + "\nlocal addition\n",
                encoding="utf-8",
            )

            rc = uninstall(home=tmp, dry_run=False, yes=True)

            self.assertEqual(rc, 0)
            self.assertTrue(persona.exists())
            self.assertFalse((cursor_dir / ".vibe-engineering-manifest.json").exists())

    def test_uninstall_dry_run_removes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)

            rc = uninstall(home=tmp, dry_run=True, yes=True)

            self.assertEqual(rc, 0)
            self.assertTrue((Path(tmp) / ".cursor" / "rules" / "00-persona.mdc").exists())

    def test_uninstall_no_manifest_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = uninstall(home=tmp, dry_run=False, yes=True)
            self.assertEqual(rc, 0)

    def test_diff_reports_no_changes_after_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            rc = diff_kit(home=tmp)
            self.assertEqual(rc, 0)

    def test_doctor_runs_without_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = doctor(home=tmp)
            self.assertIn(rc, (0, 1))


class CursorGlobalNoticeTests(unittest.TestCase):
    """Cursor does not reliably load ~/.cursor/rules, so the default global install warns."""

    def _run(self, fn, fake_home: str, **kwargs) -> str:
        buf = io.StringIO()
        with mock.patch.object(Path, "home", return_value=Path(fake_home)), redirect_stdout(buf):
            fn(**kwargs)
        return buf.getvalue()

    def test_install_warns_on_default_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._run(install, tmp, home=None, dry_run=True, yes=True)
        self.assertIn("warning:", out)
        self.assertIn("--home <repo>", out)

    def test_dry_run_on_default_home_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._run(install, tmp, home=None, dry_run=True, yes=True)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_explicit_home_equal_to_default_still_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._run(install, tmp, home=tmp, dry_run=True, yes=True)
        self.assertIn("warning:", out)

    def test_project_home_is_silent(self):
        with tempfile.TemporaryDirectory() as fake_home, tempfile.TemporaryDirectory() as repo:
            out = self._run(install, fake_home, home=repo, dry_run=True, yes=True)
        self.assertNotIn("warning:", out)

    def test_doctor_warns_on_default_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._run(doctor, tmp, home=None)
        self.assertIn("warning:", out)


if __name__ == "__main__":
    unittest.main()
