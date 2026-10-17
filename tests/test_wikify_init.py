import contextlib
import importlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents.wikify import commands, init_cmd, scan
from tests.test_wikify_state import RepoCase

FILES = ["index.md", ".wikify.json", "WIKIFY.md", ".wikifyignore", ".wikify-allow", ".wikifydocs"]
TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "agents/kits/wikify/templates/wikify/WIKIFY.md"
)


class InitTests(RepoCase):
    def wiki(self, name):
        return self.root / "docs/wiki" / name

    def test_creates_six_files_and_verifies_clean(self):
        self.assertEqual(init_cmd.cmd_init(cwd=self.root), 0)
        for name in FILES:
            self.assertTrue(self.wiki(name).is_file(), name)
        self.assertEqual(scan.scan_wiki(self.root), [])
        self.assertEqual(commands.run_verify(self.root)[0], 0)

    def test_wikifydocs_is_comment_only_and_scaffolded(self):
        init_cmd.cmd_init(cwd=self.root)
        lines = self.wiki(".wikifydocs").read_text().splitlines()
        self.assertTrue(lines and all(ln.startswith("#") for ln in lines))
        self.assertIn("# docs-extra/", lines)
        from agents.wikify import docs_inventory

        self.assertEqual(docs_inventory.load_includes(self.root), [])

    def test_state_file_content(self):
        init_cmd.cmd_init(cwd=self.root)
        self.assertEqual(
            self.wiki(".wikify.json").read_text().replace(" ", "").replace("\n", ""),
            '{"version":1,"covered":null}',
        )

    def test_template_copied_byte_for_byte(self):
        self.assertTrue(TEMPLATE.is_file())
        self.assertLessEqual(len(TEMPLATE.read_text().splitlines()), 180)
        init_cmd.cmd_init(cwd=self.root)
        self.assertEqual(self.wiki("WIKIFY.md").read_bytes(), TEMPLATE.read_bytes())

    def test_template_confirmation_gate_shows_new_files(self):
        text = TEMPLATE.read_text()
        self.assertIn("git status --short -- docs/wiki", text)
        self.assertIn("git add -N -- docs/wiki && git diff -- docs/wiki", text)

    def test_index_scaffolds_empty_map(self):
        init_cmd.cmd_init(cwd=self.root)
        self.assertEqual(
            self.wiki("index.md").read_text(),
            "# Wiki index\n\n<!-- wikify:map -->\n<!-- /wikify:map -->\n",
        )

    def test_next_hint_on_init_and_reinit_writes_nothing_else(self):
        import contextlib
        import io

        hint = "Next: run vibe wikify link to add the agent pointer block to AGENTS.md"
        for _ in range(2):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(init_cmd.cmd_init(cwd=self.root), 0)
            self.assertEqual(buf.getvalue().splitlines()[-1], hint)
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_template_documents_agent_map(self):
        text = " ".join(TEMPLATE.read_text().split())
        for phrase in (
            "## Agent map",
            "<!-- wikify:map -->",
            "<!-- /wikify:map -->",
            "- [Title](path.md) — hint",
            "Add an entry for every page you create",
            "when an agent should load",
            "navigation, not factual claims",
            "60 entries",
            "6144 bytes",
            "Never use `@` imports",
            "`www.`",
            "untrusted text",
            "the user's confirmation before commit is the control",
        ):
            with self.subTest(phrase):
                self.assertIn(phrase, text)

    def test_template_states_limits_and_batching(self):
        text = " ".join(TEMPLATE.read_text().split())
        for phrase in (
            "After a squash merge",
            "one bounded context",
            "confirm each batch with the user",
            "`stale_deleted`",
            "never deleted automatically",
            "only after the user agrees",
            "One citation covers its whole paragraph",
            "link text is not verified",
            "does not re-run `verify`",
        ):
            with self.subTest(phrase):
                self.assertIn(phrase, text)

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
        self.assertEqual(buf.getvalue().count("already initialized"), 6)

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


class UpdateProtocolTests(RepoCase):
    OLD = "# WIKIFY: an older shipped protocol\n"

    def setUp(self):
        super().setUp()
        init_cmd.cmd_init(cwd=self.root)
        self.path = self.root / "docs/wiki/WIKIFY.md"
        self.known = mock.patch.object(
            init_cmd, "KNOWN_PROTOCOL_SHA256", frozenset({init_cmd.sha256(self.OLD.encode())})
        )
        self.known.start()
        self.addCleanup(self.known.stop)

    def run_update(self, apply=False):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = init_cmd.cmd_update_protocol(self.root, apply)
        return rc, buf.getvalue()

    def test_current_protocol_is_up_to_date(self):
        rc, out = self.run_update(apply=True)
        self.assertEqual(rc, 0)
        self.assertIn("up to date", out)

    def test_dry_run_reports_and_writes_nothing(self):
        self.path.write_text(self.OLD)
        rc, out = self.run_update()
        self.assertEqual(rc, 0)
        self.assertIn("would replace", out)
        self.assertEqual(self.path.read_text(), self.OLD)

    def test_apply_replaces_a_pristine_older_version(self):
        self.path.write_text(self.OLD)
        rc, out = self.run_update(apply=True)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.path.read_bytes(), TEMPLATE.read_bytes())

    def test_locally_edited_file_is_never_overwritten(self):
        self.path.write_text(self.OLD + "my own rule\n")
        for apply in (False, True):
            rc, out = self.run_update(apply)
            self.assertEqual(rc, 1)
            self.assertIn("locally edited; not overwritten", out)
        self.assertEqual(self.path.read_text(), self.OLD + "my own rule\n")

    def test_missing_file_and_symlink_are_refused(self):
        self.path.unlink()
        self.assertEqual(self.run_update(True)[0], 1)
        target = self.root / "elsewhere.md"
        target.write_text(self.OLD)
        self.path.symlink_to(target)
        rc, out = self.run_update(True)
        self.assertEqual(rc, 1)
        self.assertEqual(target.read_text(), self.OLD)

    def test_every_historical_version_is_known(self):
        init_cmd_known = importlib.reload(init_cmd).KNOWN_PROTOCOL_SHA256
        rel = "agents/kits/wikify/templates/wikify/WIKIFY.md"
        log = subprocess.run(
            ["git", "log", "--follow", "--format=%H", "--", rel],
            cwd=TEMPLATE.parents[5], capture_output=True, text=True, check=False,
        )
        commits = log.stdout.split()
        if log.returncode != 0 or len(commits) < 2:
            self.skipTest("git history of WIKIFY.md is not available")
        current = init_cmd.sha256(TEMPLATE.read_bytes())
        for commit in commits:
            blob = subprocess.run(
                ["git", "show", f"{commit}:{rel}"], cwd=TEMPLATE.parents[5], capture_output=True, check=True
            ).stdout
            digest = init_cmd.sha256(blob)
            self.assertTrue(
                digest == current or digest in init_cmd_known, f"{commit} is not in the known list"
            )
