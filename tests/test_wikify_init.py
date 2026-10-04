import tempfile
import unittest
from pathlib import Path

from agents.wikify import commands, init_cmd, scan
from tests.test_wikify_state import RepoCase

FILES = ["index.md", ".wikify.json", "WIKIFY.md", ".wikifyignore", ".wikify-allow"]
TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "agents/kits/wikify/templates/wikify/WIKIFY.md"
)


class InitTests(RepoCase):
    def wiki(self, name):
        return self.root / "docs/wiki" / name

    def test_creates_five_files_and_verifies_clean(self):
        self.assertEqual(init_cmd.cmd_init(cwd=self.root), 0)
        for name in FILES:
            self.assertTrue(self.wiki(name).is_file(), name)
        self.assertEqual(scan.scan_wiki(self.root), [])
        self.assertEqual(commands.run_verify(self.root)[0], 0)

    def test_state_file_content(self):
        init_cmd.cmd_init(cwd=self.root)
        self.assertEqual(
            self.wiki(".wikify.json").read_text().replace(" ", "").replace("\n", ""),
            '{"version":1,"covered":null}',
        )

    def test_template_copied_byte_for_byte(self):
        self.assertTrue(TEMPLATE.is_file())
        self.assertLessEqual(len(TEMPLATE.read_text().splitlines()), 120)
        init_cmd.cmd_init(cwd=self.root)
        self.assertEqual(self.wiki("WIKIFY.md").read_bytes(), TEMPLATE.read_bytes())

    def test_reinit_preserves_existing(self):
        init_cmd.cmd_init(cwd=self.root)
        self.wiki("index.md").write_text("custom\n")
        self.assertEqual(init_cmd.cmd_init(cwd=self.root), 0)
        self.assertEqual(self.wiki("index.md").read_text(), "custom\n")

    def test_reinit_reports_already_initialized(self):
        import contextlib
        import io

        init_cmd.cmd_init(cwd=self.root)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            init_cmd.cmd_init(cwd=self.root)
        self.assertEqual(buf.getvalue().count("already initialized"), 5)

    def test_missing_template_rc1(self):
        from unittest import mock

        with mock.patch.object(init_cmd, "TEMPLATE", self.root / "nope.md"):
            self.assertEqual(init_cmd.cmd_init(cwd=self.root), 1)

    def test_outside_git_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(init_cmd.cmd_init(cwd=tmp), 1)
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
