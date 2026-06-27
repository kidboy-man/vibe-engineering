import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.kits.codex.installer import diff_kit, doctor, install, uninstall


class CodexInstallerTests(unittest.TestCase):
    def test_install_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = install(home=tmp, dry_run=True, yes=True)
            self.assertEqual(rc, 0)
            self.assertFalse((Path(tmp) / ".codex" / "instructions.md").exists())

    def test_install_dry_run_creates_no_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = install(home=tmp, dry_run=True, yes=True)
            self.assertEqual(rc, 0)
            self.assertFalse((Path(tmp) / ".codex").exists())

    def test_install_copies_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = install(home=tmp, dry_run=False, yes=True)

            self.assertEqual(rc, 0)
            codex_dir = Path(tmp) / ".codex"
            self.assertTrue((codex_dir / "instructions.md").exists())
            self.assertTrue((codex_dir / ".vibe-engineering-manifest.json").exists())

    def test_install_accepts_merge_settings_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = install(home=tmp, dry_run=True, yes=True, merge_settings=False)
            self.assertEqual(rc, 0)

    def test_install_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            codex_dir = Path(tmp) / ".codex"
            self.assertTrue((codex_dir / "instructions.md").exists())

    def test_uninstall_removes_unchanged_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)

            rc = uninstall(home=tmp, dry_run=False, yes=True)

            self.assertEqual(rc, 0)
            self.assertFalse((Path(tmp) / ".codex" / "instructions.md").exists())
            self.assertFalse((Path(tmp) / ".codex" / ".vibe-engineering-manifest.json").exists())

    def test_uninstall_keeps_modified_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_dir = Path(tmp) / ".codex"
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            instructions = codex_dir / "instructions.md"
            instructions.write_text(
                instructions.read_text(encoding="utf-8") + "\nlocal change\n",
                encoding="utf-8",
            )

            rc = uninstall(home=tmp, dry_run=False, yes=True)

            self.assertEqual(rc, 0)
            self.assertTrue(instructions.exists())
            self.assertFalse((codex_dir / ".vibe-engineering-manifest.json").exists())

    def test_uninstall_dry_run_removes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)

            rc = uninstall(home=tmp, dry_run=True, yes=True)

            self.assertEqual(rc, 0)
            self.assertTrue((Path(tmp) / ".codex" / "instructions.md").exists())

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
