import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.kits.claude_code.installer import install as claude_install
from agents.kits.opencode.installer import install as opencode_install


class InvalidConfigInstallTests(unittest.TestCase):
    def test_claude_install_aborts_on_invalid_settings_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude_dir = Path(tmp) / ".claude"
            claude_dir.mkdir()
            (claude_dir / "settings.json").write_text("not valid json", encoding="utf-8")

            captured = io.StringIO()
            with patch("sys.stdout", new=captured):
                rc = claude_install(home=tmp, dry_run=False, yes=True)

            self.assertEqual(rc, 1)
            self.assertIn("invalid settings.json", captured.getvalue())
            # Invalid file must be preserved untouched.
            self.assertEqual(
                (claude_dir / "settings.json").read_text(encoding="utf-8"),
                "not valid json",
            )
            # No partial writes: manifest must not exist.
            self.assertFalse((claude_dir / ".vibe-engineering-manifest.json").exists())

    def test_claude_install_aborts_on_invalid_settings_json_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude_dir = Path(tmp) / ".claude"
            claude_dir.mkdir()
            (claude_dir / "settings.json").write_text("not valid json", encoding="utf-8")

            captured = io.StringIO()
            with patch("sys.stdout", new=captured):
                rc = claude_install(home=tmp, dry_run=True, yes=True)

            self.assertEqual(rc, 1)
            self.assertIn("invalid settings.json", captured.getvalue())
            self.assertEqual(
                (claude_dir / "settings.json").read_text(encoding="utf-8"),
                "not valid json",
            )
            self.assertFalse((claude_dir / ".vibe-engineering-manifest.json").exists())

    def test_opencode_install_aborts_on_invalid_opencode_jsonc(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "opencode"
            config_dir.mkdir()
            (config_dir / "opencode.jsonc").write_text("not valid jsonc", encoding="utf-8")

            captured = io.StringIO()
            with patch("sys.stdout", new=captured):
                rc = opencode_install(home=tmp, dry_run=False, yes=True)

            self.assertEqual(rc, 1)
            self.assertIn("invalid opencode.jsonc", captured.getvalue())
            # Invalid file must be preserved untouched.
            self.assertEqual(
                (config_dir / "opencode.jsonc").read_text(encoding="utf-8"),
                "not valid jsonc",
            )
            # No partial writes: manifest must not exist.
            self.assertFalse((config_dir / ".vibe-engineering-manifest.json").exists())

    def test_opencode_install_aborts_on_invalid_opencode_jsonc_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "opencode"
            config_dir.mkdir()
            (config_dir / "opencode.jsonc").write_text("not valid jsonc", encoding="utf-8")

            captured = io.StringIO()
            with patch("sys.stdout", new=captured):
                rc = opencode_install(home=tmp, dry_run=True, yes=True)

            self.assertEqual(rc, 1)
            self.assertIn("invalid opencode.jsonc", captured.getvalue())
            self.assertEqual(
                (config_dir / "opencode.jsonc").read_text(encoding="utf-8"),
                "not valid jsonc",
            )
            self.assertFalse((config_dir / ".vibe-engineering-manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
