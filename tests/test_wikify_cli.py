import contextlib
import io
import json
import os
import unittest
from unittest import mock

from agents import cli
from agents.wikify import commands, gitview, init_cmd, scan, state
from tests.test_wikify_state import RepoCase, git

PAGE = "docs/wiki/a.md"
HUMAN = "<!-- wikify:human -->\nwhy\n<!-- /wikify:human -->\n"


def out(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*a, **kw)
    return rc, buf.getvalue()


class VerifyCase(RepoCase):
    def setUp(self):
        super().setUp()
        self.commit("src/a.py", "def foo():\n    return 1\n")
        out(init_cmd.cmd_init, cwd=self.root)

    def page(self, text, rel=PAGE):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def commit_wiki(self):
        git(self.root, "add", "--", "docs/wiki")
        git(self.root, "commit", "-q", "-m", "docs(wiki): x")

    def verify(self):
        return commands.run_verify(self.root)


class VerifyTests(VerifyCase):
    def test_clean_page_ok(self):
        self.page("Foo returns one (src: src/a.py:1-2 `foo`)\n")
        rc, lines = self.verify()
        self.assertEqual(rc, 0)
        self.assertIn("ok: wiki verified", lines)
        self.assertIn(scan.FLOOR_NOTICE, lines)

    def test_bad_citation(self):
        self.page("Claim (src: src/missing.py:1)\n")
        rc, lines = self.verify()
        self.assertEqual(rc, 1)
        self.assertTrue(any("a.md:1" in ln and "not tracked" in ln for ln in lines))

    def test_secret_line(self):
        self.page('Cfg (src: src/a.py:1)\n\npassword = "hunter2hunter2"\n')
        rc, lines = self.verify()
        self.assertEqual(rc, 1)
        self.assertTrue(any("secret-assignment" in ln for ln in lines))

    def test_secret_inside_human_block_still_flagged(self):
        self.page("<!-- wikify:human -->\nreach me at someone@example.org\n<!-- /wikify:human -->\n")
        self.assertEqual(self.verify()[0], 1)

    def test_scan_exception_fails(self):
        with mock.patch.object(scan, "scan_wiki", side_effect=PermissionError("x")):
            rc, text = out(commands.cmd_verify, self.root)
        self.assertEqual(rc, 1)
        self.assertIn("verify failed: PermissionError", text)

    def test_human_block_new_and_unchanged(self):
        self.page(HUMAN)
        rc, lines = self.verify()
        self.assertEqual(rc, 0)
        self.assertIn("HUMAN BLOCK CHANGED: a.md:1", lines)
        self.commit_wiki()
        self.assertFalse(any("HUMAN BLOCK" in ln for ln in self.verify()[1]))
        self.page(HUMAN.replace("why", "because"))
        self.assertIn("HUMAN BLOCK CHANGED: a.md:1", self.verify()[1])

    def test_allow_list_changed_and_allow_listed(self):
        self.page("Contact (src: src/a.py:1) x@example.org\n")
        self.assertEqual(self.verify()[0], 1)
        allow = self.root / "docs/wiki/.wikify-allow"
        allow.write_text("a.md|x@example.org\n")
        rc, lines = self.verify()
        self.assertEqual(rc, 0)
        self.assertIn("ALLOW-LIST CHANGED: a.md|x@example.org", lines)
        self.assertIn("ALLOW-LISTED:", lines)
        self.assertTrue(any("email (allow-listed)" in ln for ln in lines))
        self.commit_wiki()
        self.assertFalse(any("ALLOW-LIST CHANGED" in ln for ln in self.verify()[1]))


class MarkTests(VerifyCase):
    def test_refuses_when_failing(self):
        self.page("Claim (src: src/missing.py:1)\n")
        before = (self.root / state.STATE_REL).read_text()
        rc, _ = out(commands.cmd_mark, self.root)
        self.assertEqual(rc, 1)
        self.assertEqual((self.root / state.STATE_REL).read_text(), before)

    def test_mark_then_commit_is_fresh_and_advances(self):
        rc, text = out(commands.cmd_mark, self.root)
        self.assertEqual(rc, 0)
        head = gitview.head(self.root)
        self.assertIn(f"marked at {head[:7]}", text)
        self.assertIn("git add -- docs/wiki", text)
        self.assertEqual(state.load(self.root)["covered"], head)
        self.commit_wiki()
        self.assertTrue(state.is_fresh(self.root))
        self.commit("src/b.py", "x = 1\n")
        self.assertFalse(state.is_fresh(self.root))
        before = (self.root / state.STATE_REL).read_text()
        out(commands.cmd_mark, self.root)
        self.assertNotEqual((self.root / state.STATE_REL).read_text(), before)

    def test_mark_no_commits(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init", "-q", "-b", "main")
            init_cmd.cmd_init(cwd=root)
            rc, text = out(commands.cmd_mark, root)
        self.assertEqual(rc, 0)
        self.assertIn("marked at no commits", text)


class PlanAndMainTests(VerifyCase):
    def test_plan_json(self):
        rc, text = out(commands.cmd_plan, self.root, full=True, as_json=True)
        self.assertEqual(rc, 0)
        self.assertIsInstance(json.loads(text), dict)

    def test_plan_error_rc1(self):
        with mock.patch("agents.wikify.plan.build_plan", return_value={"error": "boom"}), \
                mock.patch("agents.wikify.plan.render", return_value="boom"):
            self.assertEqual(out(commands.cmd_plan, self.root)[0], 1)

    def test_main_dispatch(self):
        old = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, old)
        self.assertEqual(out(cli.main, ["wikify", "plan"])[0], 0)
        self.assertEqual(out(cli.main, ["wikify", "verify"])[0], 0)

    def test_not_a_repo(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            rc, text = out(commands.cmd_verify, tmp)
        self.assertEqual(rc, 1)
        self.assertIn("not a git repository", text)


class ParseAllowTests(unittest.TestCase):
    def test_parse_allow(self):
        self.assertEqual(
            scan.parse_allow("# c\n\na.md|x@y.zz\nbad\n"), {("a.md", "x@y.zz")}
        )



class GateHardeningTests(VerifyCase):
    def errors(self):
        rc, lines = self.verify()
        return rc, "\n".join(lines)

    def test_non_markdown_file(self):
        (self.root / "docs/wiki/notes.txt").write_text("hi\n")
        rc, text = self.errors()
        self.assertEqual(rc, 1)
        self.assertIn("docs/wiki/notes.txt", text)

    def test_uppercase_md_is_verified(self):
        self.page("uncited prose\n", "docs/wiki/page.MD")
        rc, text = self.errors()
        self.assertEqual(rc, 1)
        self.assertIn("page.MD:1: uncited paragraph", text)

    def test_nested_control_name_not_exempt(self):
        (self.root / "docs/wiki/sub").mkdir()
        (self.root / "docs/wiki/sub/.wikifyignore").write_text("x\n")
        self.assertEqual(self.errors()[0], 1)

    def test_symlinked_file(self):
        os.symlink("/etc/hostname", self.root / "docs/wiki/host.txt")
        rc, text = self.errors()
        self.assertEqual(rc, 1)
        self.assertIn("docs/wiki/host.txt: symlink not allowed", text)

    def test_symlinked_dir(self):
        import tempfile

        with tempfile.TemporaryDirectory() as outside:
            os.symlink(outside, self.root / "docs/wiki/linked")
            rc, text = self.errors()
        self.assertEqual(rc, 1)
        self.assertIn("docs/wiki/linked: symlink not allowed", text)
        self.assertNotIn(outside, text)

    def test_symlinked_wiki(self):
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as outside:
            shutil.rmtree(self.root / "docs/wiki")
            os.symlink(outside, self.root / "docs/wiki")
            rc, text = self.errors()
        self.assertEqual(rc, 1)
        self.assertIn("docs/wiki: symlink not allowed", text)

    def test_human_block_removed(self):
        self.page(HUMAN)
        self.commit_wiki()
        self.page("Foo (src: src/a.py:1)\n")
        rc, lines = self.verify()
        self.assertEqual(rc, 0)
        self.assertIn("HUMAN BLOCK REMOVED: a.md", lines)

    def test_template_shows_markers(self):
        t = (self.root / "docs/wiki/WIKIFY.md").read_text()
        self.assertIn("    <!-- wikify:human -->\n", t)
        self.assertIn("    <!-- /wikify:human -->\n", t)
        self.assertEqual(self.verify()[0], 0)

    def test_unknown_subcommand_rc2(self):
        ns = type("A", (), {"wikify_command": "bogus"})()
        self.assertEqual(out(commands.cmd_wikify, ns, self.root)[0], 2)


class SymlinkWriteTests(RepoCase):
    def setUp(self):
        super().setUp()
        import tempfile
        from pathlib import Path

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.outside = Path(tmp.name)
        self.victim = self.outside / "victim"
        self.victim.write_bytes(b"precious\n")

    def assert_refused(self):
        self.assertEqual(out(init_cmd.cmd_init, cwd=self.root)[0], 1)
        self.assertEqual(out(commands.cmd_mark, self.root)[0], 1)
        self.assertEqual(self.victim.read_bytes(), b"precious\n")
        self.assertEqual(sorted(p.name for p in self.outside.iterdir()), ["victim"])

    def test_symlinked_docs(self):
        os.symlink(self.outside, self.root / "docs")
        self.assert_refused()

    def test_symlinked_wiki(self):
        (self.root / "docs").mkdir()
        os.symlink(self.outside, self.root / "docs/wiki")
        self.assert_refused()

    def test_symlinked_state_file(self):
        (self.root / "docs/wiki").mkdir(parents=True)
        os.symlink(self.victim, self.root / "docs/wiki/.wikify.json")
        self.assert_refused()

    def test_wiki_is_regular_file(self):
        (self.root / "docs").mkdir()
        (self.root / "docs/wiki").write_text("x")
        rc, text = out(init_cmd.cmd_init, cwd=self.root)
        self.assertEqual(rc, 1)
        self.assertIn("cannot create", text)


@unittest.skipIf(os.geteuid() == 0, "root bypasses directory permissions")
class UnreadableDirTests(VerifyCase):
    def setUp(self):
        super().setUp()
        priv = self.root / "docs/wiki/priv"
        priv.mkdir()
        (priv / "x.txt").write_text("AKIA" + "A" * 16 + "\n")
        priv.chmod(0)
        self.addCleanup(priv.chmod, 0o755)

    def test_verify_fails_closed(self):
        rc, lines = commands.run_verify(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("docs/wiki/priv: unreadable directory", lines)

    def test_scan_reports_unreadable(self):
        self.assertIn("priv:0: unreadable", scan.scan_wiki(self.root))


class WikiIsFileTests(RepoCase):
    def setUp(self):
        super().setUp()
        (self.root / "docs").mkdir()
        (self.root / "docs/wiki").write_text("x")

    def test_verify_errors(self):
        rc, lines = commands.run_verify(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("docs/wiki: not a directory", lines)

    def test_mark_no_traceback(self):
        rc, text = out(commands.cmd_mark, self.root)
        self.assertEqual(rc, 1)
        self.assertIn("not marked", text)


if __name__ == "__main__":
    unittest.main()
