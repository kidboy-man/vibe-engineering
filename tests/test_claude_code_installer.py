import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.kits.claude_code.installer import doctor, install, uninstall


class ClaudeCodeInstallerTests(unittest.TestCase):
    def test_install_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = install(home=tmp, dry_run=True, yes=True)
            self.assertEqual(rc, 0)
            self.assertFalse((Path(tmp) / ".claude" / "CLAUDE.md").exists())

    def test_install_dry_run_creates_no_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = install(home=tmp, dry_run=True, yes=True)
            self.assertEqual(rc, 0)
            self.assertFalse((Path(tmp) / ".claude").exists())

    def test_install_copies_templates_and_preserves_secret_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude_dir = Path(tmp) / ".claude"
            claude_dir.mkdir()
            settings = {
                "env": {
                    "ANTHROPIC_AUTH_TOKEN": "secret-token",
                    "ANTHROPIC_BASE_URL": "https://example.invalid/anthropic/v1",
                },
                "model": "opus",
            }
            (claude_dir / "settings.json").write_text(__import__('json').dumps(settings), encoding="utf-8")

            rc = install(home=tmp, dry_run=False, yes=True)

            self.assertEqual(rc, 0)
            self.assertTrue((claude_dir / "CLAUDE.md").exists())
            self.assertTrue((claude_dir / "agents" / "go-backend-implementer.md").exists())
            merged = __import__('json').loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(merged["env"]["ANTHROPIC_AUTH_TOKEN"], "secret-token")
            self.assertEqual(merged["env"]["ANTHROPIC_BASE_URL"], "https://example.invalid/anthropic/v1")
            self.assertEqual(merged["model"], "opus")
            self.assertEqual(merged["effortLevel"], "xhigh")
            self.assertTrue((claude_dir / ".vibe-engineering-manifest.json").exists())

    def test_uninstall_keeps_modified_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude_dir = Path(tmp) / ".claude"
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            claude_md = claude_dir / "CLAUDE.md"
            claude_md.write_text(claude_md.read_text(encoding="utf-8") + "\nlocal change\n", encoding="utf-8")

            rc = uninstall(home=tmp, dry_run=False, yes=True)

            self.assertEqual(rc, 0)
            self.assertTrue(claude_md.exists())
            self.assertFalse((claude_dir / ".vibe-engineering-manifest.json").exists())

    def test_doctor_runs_against_empty_temp_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = doctor(home=tmp)
            self.assertIn(rc, (0, 1))


if __name__ == "__main__":
    unittest.main()
