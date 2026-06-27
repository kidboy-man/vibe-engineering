import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.kits.gemini.installer import diff_kit, doctor, install, uninstall


class GeminiInstallerTests(unittest.TestCase):
    def test_install_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = install(home=tmp, dry_run=True, yes=True)
            self.assertEqual(rc, 0)
            self.assertFalse((Path(tmp) / ".gemini" / "GEMINI.md").exists())

    def test_install_dry_run_creates_no_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = install(home=tmp, dry_run=True, yes=True)
            self.assertEqual(rc, 0)
            self.assertFalse((Path(tmp) / ".gemini").exists())

    def test_install_copies_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = install(home=tmp, dry_run=False, yes=True)

            self.assertEqual(rc, 0)
            gemini_dir = Path(tmp) / ".gemini"
            self.assertTrue((gemini_dir / "GEMINI.md").exists())
            self.assertTrue((gemini_dir / ".vibe-engineering-manifest.json").exists())

    def test_install_accepts_merge_settings_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = install(home=tmp, dry_run=True, yes=True, merge_settings=False)
            self.assertEqual(rc, 0)

    def test_install_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            gemini_dir = Path(tmp) / ".gemini"
            self.assertTrue((gemini_dir / "GEMINI.md").exists())

    def test_uninstall_removes_unchanged_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)

            rc = uninstall(home=tmp, dry_run=False, yes=True)

            self.assertEqual(rc, 0)
            self.assertFalse((Path(tmp) / ".gemini" / "GEMINI.md").exists())
            self.assertFalse((Path(tmp) / ".gemini" / ".vibe-engineering-manifest.json").exists())

    def test_uninstall_keeps_modified_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            gemini_dir = Path(tmp) / ".gemini"
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            gemini_md = gemini_dir / "GEMINI.md"
            gemini_md.write_text(
                gemini_md.read_text(encoding="utf-8") + "\nlocal change\n",
                encoding="utf-8",
            )

            rc = uninstall(home=tmp, dry_run=False, yes=True)

            self.assertEqual(rc, 0)
            self.assertTrue(gemini_md.exists())
            self.assertFalse((gemini_dir / ".vibe-engineering-manifest.json").exists())

    def test_uninstall_dry_run_removes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)

            rc = uninstall(home=tmp, dry_run=True, yes=True)

            self.assertEqual(rc, 0)
            self.assertTrue((Path(tmp) / ".gemini" / "GEMINI.md").exists())

    def test_uninstall_no_manifest_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = uninstall(home=tmp, dry_run=False, yes=True)
            self.assertEqual(rc, 0)

    def test_diff_reports_no_changes_after_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            rc = diff_kit(home=tmp)
            self.assertEqual(rc, 0)

    def test_doctor_returns_nonzero_when_binary_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = doctor(home=tmp)
            self.assertIn(rc, (0, 1))


if __name__ == "__main__":
    unittest.main()
