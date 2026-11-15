"""scripts/sync_rules.py keeps opencode and cursor rule copies equal to the claude-code rules."""

from __future__ import annotations

import importlib.util
import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "sync_rules.py"

CLAUDE = Path("agents/kits/claude_code/templates/claude/rules")
OPENCODE = Path("agents/kits/opencode/templates/opencode/rules")
CURSOR = Path("agents/kits/cursor/templates/cursor/rules")
TEMPLATE_DIRS = (
    Path("agents/kits/claude_code/templates/claude"),
    Path("agents/kits/opencode/templates/opencode"),
    Path("agents/kits/cursor/templates/cursor"),
)


def _load_script():
    spec = importlib.util.spec_from_file_location("sync_rules", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SyncRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sync_rules = _load_script()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for rel in TEMPLATE_DIRS:
            shutil.copytree(REPO_ROOT / rel, self.root / rel)

    def _run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = self.sync_rules.main(argv, root=self.root)
        return rc, out.getvalue(), err.getvalue()

    def test_expected_outputs_cover_twelve_files(self):
        self.assertEqual(len(self.sync_rules.expected_outputs(self.root)), 12)

    def test_cursor_output_has_frontmatter_and_canonical_body(self):
        name = "uncertainty-and-sources"
        out = self.sync_rules.expected_outputs(self.root)[self.root / CURSOR / f"{name}.mdc"]
        canonical = (self.root / CLAUDE / f"{name}.md").read_text(encoding="utf-8")
        self.assertTrue(out.startswith("---\ndescription: "))
        self.assertIn("\nalwaysApply: true\n---\n\n", out)
        self.assertTrue(out.endswith(canonical))

    def test_sync_write_then_check_is_clean_and_idempotent(self):
        (self.root / OPENCODE / "operating-model.md").write_text("stale\n", encoding="utf-8")
        self.assertTrue(self.sync_rules.sync(self.root, True))
        self.assertEqual(self.sync_rules.sync(self.root, False), [])
        self.assertEqual(self.sync_rules.sync(self.root, True), [])
        for path in self.sync_rules.expected_outputs(self.root):
            self.assertNotIn(b"\r", path.read_bytes(), f"{path} has CR")

    def test_check_reports_edited_copy(self):
        self.sync_rules.sync(self.root, True)
        copy = self.root / OPENCODE / "operating-model.md"
        copy.write_text(copy.read_text(encoding="utf-8") + "x", encoding="utf-8")
        stale = self.sync_rules.sync(self.root, False)
        self.assertIn(copy, stale)
        self.assertNotIn(self.root / CLAUDE / "operating-model.md", stale)

    def test_check_reports_missing_destination(self):
        self.sync_rules.sync(self.root, True)
        missing = self.root / CURSOR / "go-backend-engineering.mdc"
        missing.unlink()
        self.assertIn(missing, self.sync_rules.sync(self.root, False))

    def test_main_check_exit_codes(self):
        rc, _out, _err = self._run_main([])  # write mode
        self.assertEqual(rc, 0)
        rc, _out, _err = self._run_main(["--check"])
        self.assertEqual(rc, 0)
        copy = self.root / CURSOR / "operating-model.mdc"
        copy.write_text(copy.read_text(encoding="utf-8") + "x", encoding="utf-8")
        rc, out, _err = self._run_main(["--check"])
        self.assertEqual(rc, 1)
        self.assertIn(str(copy), out)
        self.assertIn("python3 scripts/sync_rules.py", out)

    def test_missing_canonical_exits_2(self):
        (self.root / CLAUDE / "operating-model.md").unlink()
        rc, _out, err = self._run_main(["--check"])
        self.assertEqual(rc, 2)
        self.assertIn("operating-model.md", err)


class RepoTemplateTests(unittest.TestCase):
    """The committed templates, not a temp copy."""

    def test_repo_templates_are_in_sync(self):
        stale = _load_script().sync(REPO_ROOT, False)
        self.assertEqual(
            stale,
            [],
            "stale rule copies (canonical: claude-code rules); run `python3 scripts/sync_rules.py`:\n"
            + "\n".join(str(path) for path in stale),
        )

    def test_embedded_kits_have_a_section_per_rule(self):
        embedded = (
            REPO_ROOT / "agents/kits/codex/templates/codex/AGENTS.md",
            REPO_ROOT / "agents/kits/gemini/templates/gemini/GEMINI.md",
        )
        for name in _load_script().RULES:
            title = (REPO_ROOT / CLAUDE / f"{name}.md").read_text(encoding="utf-8").splitlines()[0]
            self.assertTrue(title.startswith("# "), f"{name}: first line is not an H1")
            heading = "### " + title[2:]
            for path in embedded:
                lines = path.read_text(encoding="utf-8").splitlines()
                self.assertIn(heading, lines, f"{path.name} lacks section {heading!r}")


if __name__ == "__main__":
    unittest.main()
