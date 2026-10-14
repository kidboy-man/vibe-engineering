import contextlib
import io
import json
import os
import unittest
from unittest import mock

from agents import cli
from agents.wikify import commands, gitview, init_cmd, scan, state
from tests.test_wikify_state import RepoCase, git
from tests.wikify_perf_helpers import assert_scales_linearly

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
        # legacy index without a map: these tests are about citations, not the map
        (self.root / "docs/wiki/index.md").write_text("# Wiki index\n")

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
        with mock.patch.object(scan, "report", side_effect=PermissionError("x")):
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
        key = scan.allow_key("x@example.org")
        self.assertIn(f"ALLOW-LIST KEY: a.md:1: email -> a.md|{key}", self.verify()[1])
        allow.write_text(f"a.md|{key}\n")
        rc, lines = self.verify()
        self.assertEqual(rc, 0)
        self.assertIn(f"ALLOW-LIST CHANGED: a.md|{key}", lines)
        self.assertNotIn("x@example.org", "\n".join(lines))
        self.assertIn("ALLOW-LISTED:", lines)
        self.assertTrue(any("email (allow-listed)" in ln for ln in lines))
        self.commit_wiki()
        self.assertFalse(any("ALLOW-LIST CHANGED" in ln for ln in self.verify()[1]))


class NonUtf8PageTests(VerifyCase):
    def test_names_the_page(self):
        self.page("fine (src: src/a.py:1)\n")
        (self.root / "docs/wiki/bad.md").write_bytes(b"\xff\xfe broken\n")
        rc, lines = self.verify()
        self.assertEqual(rc, 1)
        self.assertIn("bad.md: not valid UTF-8", lines)
        self.assertFalse(any(ln.startswith("verify failed") for ln in lines))


class IgnoreNegationTests(VerifyCase):
    def test_negation_is_a_verify_error(self):
        self.page("x (src: src/a.py:1)\n")
        (self.root / "docs/wiki/.wikifyignore").write_text("# c\nvendor/\n!vendor/keep.py\n")
        rc, lines = self.verify()
        self.assertEqual(rc, 1)
        self.assertTrue(
            any("'!' negation is not supported, line 3" in ln for ln in lines), lines
        )


class LegacyAllowTests(VerifyCase):
    def test_plaintext_entry_honoured_with_migration_notice(self):
        self.page("Contact (src: src/a.py:1) x@example.org\n")
        (self.root / "docs/wiki/.wikify-allow").write_text("a.md|x@example.org\n")
        rc, lines = self.verify()
        key = scan.allow_key("x@example.org")
        self.assertEqual(rc, 0)
        self.assertIn(f"ALLOW-LIST CHANGED: a.md|{key}", lines)
        self.assertTrue(any(ln.startswith("ALLOW-LIST LEGACY: a.md") and key in ln for ln in lines))
        self.assertNotIn("x@example.org", "\n".join(ln for ln in lines if "LIST" in ln and "|" in ln))


class AgentMapVerifyTests(VerifyCase):
    NOTICE = "NOTICE: docs/wiki/index.md has no wikify:map block"
    EMPTY = "# Wiki index\n\n<!-- wikify:map -->\n<!-- /wikify:map -->\n"

    def setUp(self):
        super().setUp()
        self.index(self.EMPTY)

    def index(self, text):
        self.page(text, "docs/wiki/index.md")

    def mapped(self, *entries):
        body = "".join(f"{e}\n" for e in entries)
        return f"# Wiki index\n\n<!-- wikify:map -->\n{body}<!-- /wikify:map -->\n"

    def errs(self):
        rc, lines = self.verify()
        return rc, [ln for ln in lines if ".md:" in ln]

    def test_fresh_init_verifies_clean(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q")
            out(init_cmd.cmd_init, cwd=root)
            rc, lines = commands.run_verify(root)
        self.assertEqual((rc, lines[-1]), (0, "ok: wiki verified"))
        self.assertEqual(scan.scan_wiki(root), [])

    def test_unmapped_page_is_error(self):
        self.page("Foo (src: src/a.py:1)\n")
        rc, errs = self.errs()
        self.assertEqual(rc, 1)
        self.assertEqual(errs, ["index.md:3: page not reachable from the map: a.md"])

    def test_mapped_entry_is_navigation_not_cited(self):
        self.page("Foo (src: src/a.py:1)\n")
        self.index(self.mapped("- [A](a.md) — when changing foo"))
        self.assertEqual(self.errs(), (0, []))

    def test_duplicate_and_missing_targets(self):
        self.page("Foo (src: src/a.py:1)\n")
        self.index(self.mapped(
            "- [A](a.md) — when changing foo",
            "- [A](a.md) — again",
            "- [B](b.md) — nothing there",
        ))
        rc, errs = self.errs()
        self.assertEqual(rc, 1)
        self.assertEqual(
            errs,
            ["index.md:5: duplicate entry: a.md", "index.md:6: link target missing: b.md"],
        )

    def test_prose_outside_block_still_needs_citation(self):
        self.index(self.EMPTY + "\nUncited claim here.\n")
        rc, errs = self.errs()
        self.assertEqual(rc, 1)
        self.assertEqual(errs, ["index.md:6: uncited paragraph"])

    def test_map_inside_human_block_is_ignored(self):
        self.page("Foo (src: src/a.py:1)\n")
        self.index(
            "# Wiki index\n\n<!-- wikify:human -->\n"
            "<!-- wikify:map -->\n<!-- /wikify:map -->\n<!-- /wikify:human -->\n"
        )
        rc, lines = self.verify()
        self.assertEqual(rc, 0)
        self.assertTrue(any(ln.startswith(self.NOTICE) and "1 page(s)" in ln for ln in lines))

    def test_legacy_wiki_without_block_gets_notice_only(self):
        self.page("Foo (src: src/a.py:1)\n")
        self.index("# Wiki index\n")
        rc, lines = self.verify()
        self.assertEqual(rc, 0)
        self.assertIn(self.NOTICE + "; 1 page(s) are not reachable from a map", lines)

    def test_no_notice_when_only_index_or_map_present(self):
        self.index("# Wiki index\n")
        self.assertFalse(any(ln.startswith(self.NOTICE) for ln in self.verify()[1]))
        self.page("Foo (src: src/a.py:1)\n")
        self.index(self.mapped("- [A](a.md) — when changing foo"))
        self.assertFalse(any(ln.startswith(self.NOTICE) for ln in self.verify()[1]))

    def test_cap_of_sixty_entries(self):
        for i in range(61):
            self.page(f"Foo (src: src/a.py:1)\n", f"docs/wiki/p{i}.md")
        self.index(self.mapped(*(f"- [P{i}](p{i}.md) — hint" for i in range(61))))
        rc, errs = self.errs()
        self.assertEqual(rc, 1)
        self.assertIn("index.md:3: map exceeds 60 entries", errs)

    def test_nested_index_is_an_ordinary_page(self):
        self.page("Foo (src: src/a.py:1)\n", "docs/wiki/sub/index.md")
        rc, errs = self.errs()
        self.assertEqual(errs, ["index.md:3: page not reachable from the map: sub/index.md"])
        self.index(self.mapped("- [S](sub/index.md) — when in sub"))
        self.assertEqual(self.errs(), (0, []))


    def sources_wiki(self, n, linked=True):
        links = "".join(f"- [P{i}](docs/p{i}.md)\n" for i in range(n)) if linked else "\n"
        self.page(f"# Sources\n{links}", "docs/wiki/sources/index.md")
        for i in range(n):
            self.page("Foo (src: src/a.py:1)\n", f"docs/wiki/sources/docs/p{i}.md")
        self.index(self.mapped("- [Sources](sources/index.md) \u2014 doc outlines"))

    def test_pages_linked_from_listed_page_are_reachable(self):
        self.sources_wiki(70)
        self.assertEqual(self.errs(), (0, []))

    def test_same_pages_unlinked_are_orphans(self):
        self.sources_wiki(3, linked=False)
        rc, errs = self.errs()
        self.assertEqual(rc, 1)
        self.assertEqual(len(errs), 3)
        self.assertIn("page not reachable from the map: sources/docs/p0.md", errs[0])

    def test_three_hops_is_an_orphan(self):
        self.page("[b](b.md)\n", "docs/wiki/a.md")
        self.page("[c](c.md)\n", "docs/wiki/b.md")
        self.page("[d](d.md)\n", "docs/wiki/c.md")
        self.page("Foo (src: src/a.py:1)\n", "docs/wiki/d.md")
        self.index(self.mapped("- [A](a.md) \u2014 start"))
        rc, errs = self.errs()
        self.assertEqual(errs, ["index.md:3: page not reachable from the map: d.md"])

    def test_plan_map_missing_agrees_with_verify(self):
        from agents.wikify import plan

        self.sources_wiki(3)
        self.page("Foo (src: src/a.py:1)\n", "docs/wiki/lonely.md")
        self.commit_wiki()
        _, errs = self.errs()
        self.assertEqual(errs, ["index.md:3: page not reachable from the map: lonely.md"])
        self.assertEqual(plan.build_plan(self.root)["map_missing"], ["lonely.md"])


class HostilePageTests(VerifyCase):
    def test_megabyte_of_link_openers_is_bounded(self):
        from agents.wikify import plan

        def make(n):
            self.page("](" * (n // 2))
            self.commit_wiki()
            return (self.root,)

        assert_scales_linearly(self, make, lambda root: commands.run_verify(root), 1 << 14, label="verify")
        assert_scales_linearly(self, make, plan.build_plan, 1 << 14, label="build_plan")


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

    def files_section(self, text):
        return text.split("Files to commit:\n", 1)[1].split("\nNext:", 1)[0].splitlines()

    def test_mark_lists_new_and_modified_files(self):
        self.page("Foo (src: src/a.py:1)\n")
        self.commit_wiki()
        self.page("Foo again (src: src/a.py:1)\n")
        self.page("New (src: src/a.py:2)\n", "docs/wiki/sub/new é.md")
        rc, text = out(commands.cmd_mark, self.root)
        self.assertEqual(rc, 0)
        self.assertEqual(
            sorted(self.files_section(text)),
            ["   M docs/wiki/.wikify.json", "   M docs/wiki/a.md", "  ?? docs/wiki/sub/new é.md"],
        )
        self.assertIn("git status --short -- docs/wiki", text)
        self.assertIn("git add -N -- docs/wiki && git diff -- docs/wiki", text)

    def test_status_helper_clean_and_failure(self):
        self.commit_wiki()
        self.assertEqual(gitview.status_paths(self.root, "docs/wiki"), [])
        failed = gitview.subprocess.CompletedProcess([], 128, "", "")
        with mock.patch.object(gitview, "run_git", return_value=failed):
            self.assertIsNone(gitview.status_paths(self.root, "docs/wiki"))
        with mock.patch.object(gitview, "status_paths", return_value=None):
            rc, text = out(commands.cmd_mark, self.root)
        self.assertIn("git status failed", text)

    def test_status_helper_rename_and_intent_to_add(self):
        self.page("Foo (src: src/a.py:1)\n")
        self.commit_wiki()
        git(self.root, "mv", "docs/wiki/a.md", "docs/wiki/b.md")
        self.page("x\n", "docs/wiki/c.md")
        git(self.root, "add", "-N", "--", "docs/wiki/c.md")
        self.assertEqual(
            sorted(gitview.status_paths(self.root, "docs/wiki")),
            [" A docs/wiki/c.md", "R  docs/wiki/b.md"],
        )

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
        key = scan.allow_key("x@y.zz")
        self.assertEqual(scan.parse_allow(f"a.md|{key}\n"), {("a.md", key)})
        self.assertRegex(key, r"^sha256:[0-9a-f]{16}$")



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


@unittest.skipIf(os.geteuid() == 0, "root bypasses directory permissions")
class ListableNotSearchableDirTests(VerifyCase):
    """0o444: names are listable but every per-entry stat fails."""

    def setUp(self):
        super().setUp()
        priv = self.root / "docs/wiki/priv"
        priv.mkdir()
        (priv / "x.txt").write_text("AKIA" + "A" * 16 + "\n")
        priv.chmod(0o444)
        self.addCleanup(priv.chmod, 0o755)

    def test_verify_fails_closed(self):
        rc, lines = commands.run_verify(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("docs/wiki/priv/x.txt: unreadable", lines)

    def test_scan_reports_unreadable(self):
        self.assertIn("priv/x.txt:0: unreadable", scan.scan_wiki(self.root))


class PageListTests(VerifyCase):
    def test_uppercase_md_is_indexed_and_planned(self):
        from agents.wikify import citations, plan

        self.page("Foo (src: src/a.py:1)\n", "docs/wiki/page.MD")
        self.assertEqual(citations.index(self.root)["page.MD"], {"src/a.py"})
        self.assertIn("page.MD", plan.build_plan(self.root, full=True)["refresh_pages"])

    def test_symlinked_md_is_not_indexed(self):
        import tempfile
        from pathlib import Path

        from agents.wikify import citations

        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "t.md"
            target.write_text("Foo (src: src/missing.py:1) " + "AKIA" + "A" * 16 + "\n")
            os.symlink(target, self.root / "docs/wiki/link.md")
            self.assertNotIn("link.md", citations.index(self.root))
            rc, lines = self.verify()
            hits = scan.scan_wiki(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("docs/wiki/link.md: symlink not allowed", lines)
        self.assertFalse(any(ln.startswith("link.md:") for ln in lines), lines)
        self.assertFalse(any("link.md" in h for h in hits), hits)

    def test_non_regular_file_is_an_error(self):
        os.mkfifo(self.root / "docs/wiki/pipe.md")
        rc, lines = self.verify()
        self.assertEqual(rc, 1)
        self.assertTrue(any(ln.startswith("docs/wiki/pipe.md:") for ln in lines), lines)
        self.assertIn("pipe.md:0: unreadable", scan.scan_wiki(self.root))  # never opened


class GitignoredControlFileTests(RepoCase):
    def setUp(self):
        super().setUp()
        self.commit("src/a.py", "x = 1\n")

    def ignore(self, text):
        (self.root / ".gitignore").write_text(text)

    def test_init_refuses_and_writes_nothing(self):
        self.ignore("*.json\n")
        rc, text = out(init_cmd.cmd_init, cwd=self.root)
        self.assertEqual(rc, 1)
        self.assertIn("docs/wiki/.wikify.json", text)
        self.assertIn("!docs/wiki/", text)
        self.assertFalse((self.root / "docs").exists())

    def test_mark_and_verify_refuse(self):
        out(init_cmd.cmd_init, cwd=self.root)
        self.ignore("*.json\n")
        before = (self.root / state.STATE_REL).read_text()
        rc, lines = commands.run_verify(self.root)
        self.assertEqual(rc, 1)
        self.assertTrue(any(ln.startswith("docs/wiki/.wikify.json: ignored by git") for ln in lines), lines)
        rc, text = out(commands.cmd_mark, self.root)
        self.assertEqual(rc, 1)
        self.assertIn("not marked", text)
        self.assertEqual((self.root / state.STATE_REL).read_text(), before)

    def test_other_control_files_checked(self):
        self.ignore("index.md\n")
        rc, text = out(init_cmd.cmd_init, cwd=self.root)
        self.assertEqual(rc, 1)
        self.assertIn("docs/wiki/index.md", text)

    def test_hint_negations_work_for_docs_glob(self):
        self.ignore("docs/*\n")
        rc, text = out(init_cmd.cmd_init, cwd=self.root)
        self.assertEqual(rc, 1)
        self.assertIn("`!docs/wiki/` then `!docs/wiki/**`", text)
        self.ignore("docs/*\n!docs/wiki/\n!docs/wiki/**\n")
        self.assertEqual(gitview.ignored(self.root, state.CONTROL_RELS), [])
        self.assertEqual(out(init_cmd.cmd_init, cwd=self.root)[0], 0)

    def test_negation_accepted(self):
        self.ignore("*.json\n!docs/wiki/.wikify.json\n")
        self.assertEqual(out(init_cmd.cmd_init, cwd=self.root)[0], 0)
        self.assertEqual(commands.run_verify(self.root)[0], 0)

    def test_tracked_file_not_reported(self):
        out(init_cmd.cmd_init, cwd=self.root)
        git(self.root, "add", "--", "docs/wiki")
        git(self.root, "commit", "-q", "-m", "docs(wiki): init")
        self.ignore("*.json\n")
        self.assertEqual(commands.run_verify(self.root)[0], 0)

    def test_git_error_is_not_ignored(self):
        self.ignore("*.json\n")
        failed = gitview.subprocess.CompletedProcess([], 128, "", "")
        with mock.patch.object(gitview, "run_git", return_value=failed):
            self.assertEqual(gitview.ignored(self.root, ["docs/wiki/.wikify.json"]), [])


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
