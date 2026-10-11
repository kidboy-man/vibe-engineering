import contextlib
import io
import os
import tempfile
from pathlib import Path
from unittest import mock

from agents.wikify import commands, gitview, init_cmd, pointer, state
from tests.test_wikify_hook import bash, guard
from tests.test_wikify_state import RepoCase, git

BLOCK = pointer.BEGIN + pointer.TEMPLATE + pointer.END


def link(root, dry_run=False):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = pointer.cmd_link(root, dry_run)
    return rc, buf.getvalue()


class LinkCase(RepoCase):
    def setUp(self):
        super().setUp()
        self.commit("src/a.py", "x = 1\n")
        (self.root / "docs/wiki").mkdir(parents=True)
        (self.root / "docs/wiki/index.md").write_text("# Wiki index\n")

    def write(self, rel, data):
        p = self.root / rel
        if isinstance(data, bytes):
            p.write_bytes(data)
        else:
            p.write_text(data, newline="")
        return p

    def read(self, rel):
        return (self.root / rel).read_bytes()

    def backups(self):
        gd = gitview.git_dir(self.root)
        base = gd / "wikify-backups"
        return sorted(p for p in base.rglob("*") if p.is_file()) if base.exists() else []


class LinkTests(LinkCase):
    def test_git_dir(self):
        self.assertEqual(gitview.git_dir(self.root), (self.root / ".git").resolve())
        self.assertIsNone(gitview.git_dir(self.root / "nope"))

    def test_creates_agents_md_only(self):
        rc, text = link(self.root)
        self.assertEqual(rc, 0)
        self.assertEqual(self.read("AGENTS.md"), BLOCK.encode())
        self.assertFalse((self.root / "CLAUDE.md").exists())
        self.assertFalse((self.root / "GEMINI.md").exists())
        self.assertIn("create AGENTS.md", text)
        self.assertIn("+## Repo docs (wikify)", text)
        self.assertIn(
            "Next: commit AGENTS.md in their own commit (not together with docs/wiki), "
            "then run vibe wikify mark.",
            text,
        )
        self.assertEqual(self.backups(), [])

    def test_template_is_static(self):
        self.assertNotIn("@", pointer.TEMPLATE)
        self.assertEqual(pointer.TARGETS, ("AGENTS.md", "CLAUDE.md", "GEMINI.md"))

    def test_preserves_user_text_below_block(self):
        user = "# Mine\n\nkeep  this \t\nno trailing newline"
        self.write("AGENTS.md", user)
        rc, text = link(self.root)
        self.assertEqual(rc, 0)
        self.assertIn("update AGENTS.md", text)
        self.assertEqual(self.read("AGENTS.md"), BLOCK.encode() + user.encode())
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(self.backups()[0].read_bytes(), user.encode())

    def test_crlf_preserved(self):
        user = "# Mine\r\nline\r\n"
        self.write("AGENTS.md", user)
        self.assertEqual(link(self.root)[0], 0)
        self.assertTrue(self.read("AGENTS.md").endswith(user.encode()))

    def test_crlf_block_updated_in_place(self):
        old = BLOCK.replace("\n", "\r\n").replace("Start at", "Begin at")
        self.write("AGENTS.md", "top\r\n" + old + "bottom\r\n")
        self.assertEqual(link(self.root)[0], 0)
        data = self.read("AGENTS.md")
        self.assertEqual(data.count(b"<!-- wikify:pointer -->"), 1)
        self.assertTrue(data.startswith(b"top\r\n") and data.endswith(b"bottom\r\n"))
        self.assertIn(b"Start at", data)

    def test_rerun_unchanged_no_write_no_backup(self):
        link(self.root)
        before = self.read("AGENTS.md")
        mtime = (self.root / "AGENTS.md").stat().st_mtime_ns
        rc, text = link(self.root)
        self.assertEqual(rc, 0)
        self.assertIn("unchanged AGENTS.md", text)
        self.assertNotIn("Next:", text)
        self.assertEqual(self.read("AGENTS.md"), before)
        self.assertEqual((self.root / "AGENTS.md").stat().st_mtime_ns, mtime)
        self.assertEqual(self.backups(), [])

    def test_stale_block_updated_in_place(self):
        stale = pointer.BEGIN + "old text\n" + pointer.END
        self.write("AGENTS.md", "above\n" + stale + "below\n")
        self.assertEqual(link(self.root)[0], 0)
        self.assertEqual(self.read("AGENTS.md"), ("above\n" + BLOCK + "below\n").encode())

    def test_existing_claude_gets_block_absent_gemini_not_created(self):
        self.write("CLAUDE.md", "claude rules\n")
        rc, text = link(self.root)
        self.assertEqual(rc, 0)
        self.assertEqual(self.read("CLAUDE.md"), (BLOCK + "claude rules\n").encode())
        self.assertFalse((self.root / "GEMINI.md").exists())
        self.assertIn("commit AGENTS.md CLAUDE.md in", text)

    def test_symlink_to_other_target_is_skipped(self):
        os.symlink("AGENTS.md", self.root / "CLAUDE.md")
        self.write("AGENTS.md", "mine\n")
        rc, text = link(self.root)
        self.assertEqual(rc, 0)
        self.assertIn("CLAUDE.md -> AGENTS.md: covered by its target", text)
        self.assertTrue((self.root / "CLAUDE.md").is_symlink())
        self.assertEqual(self.read("AGENTS.md"), (BLOCK + "mine\n").encode())

    def test_agents_md_symlink_to_claude_is_covered(self):
        self.write("CLAUDE.md", "mine\n")
        os.symlink("CLAUDE.md", self.root / "AGENTS.md")
        rc, text = link(self.root)
        self.assertEqual(rc, 0)
        self.assertIn("AGENTS.md -> CLAUDE.md: covered by its target", text)
        self.assertTrue((self.root / "AGENTS.md").is_symlink())
        self.assertEqual(self.read("CLAUDE.md"), (BLOCK + "mine\n").encode())
        self.assertEqual(pointer.pointer_notices(self.root), [])

    def test_symlink_outside_repo_refuses(self):
        os.symlink("/etc/hostname", self.root / "CLAUDE.md")
        rc, text = link(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("CLAUDE.md", text)
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_symlink_relative_escape_refuses(self):
        outside = self.root.parent / "outside-target.md"
        outside.write_text("secret\n")
        self.addCleanup(outside.unlink)
        os.symlink("../outside-target.md", self.root / "GEMINI.md")
        self.assertEqual(link(self.root)[0], 1)
        self.assertEqual(outside.read_text(), "secret\n")
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_symlink_to_non_target_in_repo_refuses(self):
        os.symlink("src/a.py", self.root / "CLAUDE.md")
        self.assertEqual(link(self.root)[0], 1)
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_agents_md_symlink_refuses(self):
        os.symlink("src/a.py", self.root / "AGENTS.md")
        self.assertEqual(link(self.root)[0], 1)
        self.assertEqual(self.read("src/a.py"), b"x = 1\n")

    def test_ignored_target_refuses(self):
        self.write(".gitignore", "AGENTS.md\n")
        rc, text = link(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("AGENTS.md", text)
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_missing_index_refuses(self):
        (self.root / "docs/wiki/index.md").unlink()
        rc, text = link(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("vibe wikify init", text)
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_dry_run_writes_nothing(self):
        self.write("CLAUDE.md", "c\n")
        rc, text = link(self.root, dry_run=True)
        self.assertEqual(rc, 0)
        self.assertIn("dry run: no files written", text)
        self.assertIn("create AGENTS.md", text)
        self.assertIn("update CLAUDE.md", text)
        self.assertIn("+## Repo docs (wikify)", text)
        self.assertNotIn("Next:", text)
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertEqual(self.read("CLAUDE.md"), b"c\n")
        self.assertFalse((gitview.git_dir(self.root) / "wikify-backups").exists())

    def test_backup_in_git_dir_not_worktree(self):
        self.write("AGENTS.md", "mine\n")
        link(self.root)
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(self.backups()[0].name, "AGENTS.md")
        self.assertFalse((self.root / "backups").exists())
        self.assertNotIn("wikify-backups", git(self.root, "status", "--short"))

    def test_no_git_dir_refuses_to_modify_existing(self):
        self.write("AGENTS.md", "mine\n")
        from unittest import mock
        with mock.patch.object(gitview, "git_dir", return_value=None):
            rc, _ = link(self.root)
        self.assertEqual(rc, 1)
        self.assertEqual(self.read("AGENTS.md"), b"mine\n")

    def test_non_utf8_refuses_all(self):
        self.write("AGENTS.md", b"\xff\xfe bad")
        self.write("CLAUDE.md", "ok\n")
        rc, text = link(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("AGENTS.md", text)
        self.assertEqual(self.read("AGENTS.md"), b"\xff\xfe bad")
        self.assertEqual(self.read("CLAUDE.md"), b"ok\n")

    def test_half_marker_refuses(self):
        for text in (pointer.BEGIN + "x\n", "x\n" + pointer.END):
            self.write("AGENTS.md", text)
            rc, _ = link(self.root)
            self.assertEqual(rc, 1)
            self.assertEqual(self.read("AGENTS.md"), text.encode())

    def test_reversed_or_duplicate_markers_refuse(self):
        for text in (
            pointer.END + "mid\n" + pointer.BEGIN + "tail\n",
            BLOCK + "mid\n" + BLOCK,
        ):
            self.write("AGENTS.md", text)
            self.assertEqual(link(self.root)[0], 1)
            self.assertEqual(self.read("AGENTS.md"), text.encode())

    def test_all_or_nothing(self):
        self.write("CLAUDE.md", "ok\n")
        self.write("GEMINI.md", pointer.BEGIN + "half\n")
        self.assertEqual(link(self.root)[0], 1)
        self.assertEqual(self.read("CLAUDE.md"), b"ok\n")
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertEqual(self.backups(), [])

    def test_not_a_repo(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            rc, text = link(tmp)
        self.assertEqual(rc, 1)
        self.assertIn("not a git repository", text)


class HardeningTests(LinkCase):
    def swap_to_symlink(self, rel, dest):
        """Patch git_dir so the target is swapped for a symlink after planning."""
        real = gitview.git_dir

        def swap(root):
            p = self.root / rel
            p.unlink()
            os.symlink(dest, p)
            return real(root)

        return mock.patch.object(gitview, "git_dir", side_effect=swap)

    def outside(self, data="secret\n"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "outside.md"
        p.write_text(data)
        return p

    def test_hard_link_refuses(self):
        out = self.outside()
        os.link(out, self.root / "AGENTS.md")
        rc, text = link(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("AGENTS.md", text)
        self.assertNotIn(str(out.parent), text)
        self.assertEqual(out.read_bytes(), b"secret\n")
        self.assertEqual(self.backups(), [])

    def test_bom_kept_first_when_prepending(self):
        user = "\ufeff# Mine\nrest\n".encode()
        self.write("AGENTS.md", user)
        self.assertEqual(link(self.root)[0], 0)
        self.assertEqual(self.read("AGENTS.md"), b"\xef\xbb\xbf" + BLOCK.encode() + user[3:])

    def test_bom_kept_when_updating_in_place(self):
        stale = pointer.BEGIN + "old\n" + pointer.END
        self.write("AGENTS.md", "\ufeffabove\n" + stale + "below\n")
        self.assertEqual(link(self.root)[0], 0)
        self.assertEqual(
            self.read("AGENTS.md"), ("\ufeffabove\n" + BLOCK + "below\n").encode()
        )

    def test_bom_notice_and_unchanged(self):
        self.write("AGENTS.md", "\ufeff" + BLOCK + "x\n")
        self.assertEqual(pointer.pointer_notices(self.root), [])
        self.assertIn("unchanged AGENTS.md", link(self.root)[1])

    def test_two_runs_keep_two_backups(self):
        self.write("AGENTS.md", "one\n")
        rc, text = link(self.root)
        self.assertRegex(text, r"backup: .*wikify-backups")
        self.write("AGENTS.md", pointer.BEGIN + "old\n" + pointer.END)
        self.assertEqual(link(self.root)[0], 0)
        self.assertEqual(len(self.backups()), 2)

    def test_backup_collision_refuses(self):
        self.write("AGENTS.md", "one\n")
        with mock.patch.object(pointer, "_stamp", return_value="fixed"):
            self.assertEqual(link(self.root)[0], 0)
            self.write("AGENTS.md", pointer.BEGIN + "old\n" + pointer.END)
            before = self.read("AGENTS.md")
            rc, _ = link(self.root)
        self.assertEqual(rc, 1)
        self.assertEqual(self.read("AGENTS.md"), before)

    def test_swap_fails_and_rolls_back(self):
        out = self.outside()
        self.write("CLAUDE.md", "mine\n")
        with self.swap_to_symlink("CLAUDE.md", out):
            rc, text = link(self.root)
        self.assertEqual(rc, 1)
        self.assertEqual(out.read_bytes(), b"secret\n")
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_rollback_failure_reported(self):
        out = self.outside()
        self.write("CLAUDE.md", "mine\n")
        with self.swap_to_symlink("CLAUDE.md", out), mock.patch.object(
            pointer, "_restore", side_effect=PermissionError
        ):
            rc, text = link(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("rollback failed for AGENTS.md; backup at ", text)

    def test_open_uses_nofollow(self):
        if not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("no O_NOFOLLOW")
        self.write("CLAUDE.md", "mine\n")
        flags = []
        real = os.open

        def spy(path, fl, *a):
            flags.append(fl)
            return real(path, fl, *a)

        with mock.patch.object(pointer.os, "open", side_effect=spy):
            self.assertEqual(link(self.root)[0], 0)
        self.assertEqual(len(flags), 2)
        self.assertTrue(all(f & os.O_NOFOLLOW for f in flags))
        self.assertTrue(flags[0] & os.O_EXCL)  # create
        self.assertTrue(flags[1] & os.O_TRUNC)  # existing inode

    def test_diff_escapes_control_characters(self):
        self.write("AGENTS.md", "\x1b[31mred\x1b]0;title\x07\nkeep\ttab\x7f\n")
        rc, text = link(self.root)
        self.assertEqual(rc, 0)
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\x07", text)
        self.assertNotIn("\x7f", text)
        self.assertIn("\\x1b[31mred", text)
        self.assertIn("keep\ttab", text)

    def test_fenced_marker_refuses(self):
        for fence in ("```", "~~~"):
            text = f"how to:\n{fence}\n{pointer.BEGIN}x\n{pointer.END}{fence}\n"
            self.write("AGENTS.md", text)
            rc, out = link(self.root)
            self.assertEqual(rc, 1)
            self.assertIn("code fence", out)
            self.assertEqual(self.read("AGENTS.md"), text.encode())

    def test_marker_after_closed_fence_ok(self):
        self.write("AGENTS.md", "```\ncode\n```\n" + BLOCK)
        self.assertEqual(link(self.root)[0], 0)

    def test_fence_probes_refuse(self):
        B, E = pointer.BEGIN, pointer.END
        cases = {
            "end only inside fence": B + "x\n```\n" + E + "```\n",
            "begin only inside fence": "~~~\n" + B + "~~~\nx\n" + E,
            "4-backtick fence holding ```": "````\n```\n" + B + "x\n" + E + "```\n````\n",
            "bom before fence": "﻿```\n" + B + "x\n" + E + "```\n",
            "closing line with info string": "```\n```py\n" + B + "x\n" + E + "```\n",
            "shorter run does not close": "~~~~\n~~~\n" + B + E + "~~~~\n",
            "other char does not close": "```\n~~~\n" + B + E + "```\n",
            "indented fence": "   ```\n" + B + E + "   ```\n",
            "unclosed fence at eof": BLOCK + "```\n" + B,
        }
        for name, text in cases.items():
            with self.subTest(name):
                self.write("AGENTS.md", text)
                rc, out = link(self.root)
                self.assertEqual(rc, 1)
                self.assertIn("refused: AGENTS.md has a wikify:pointer marker inside a code fence", out)
                self.assertIn("nothing written", out)
                self.assertEqual(self.read("AGENTS.md"), text.encode())

    def test_markers_not_at_column_zero_are_text(self):
        cases = {
            "indented example": "    " + pointer.BEGIN + "    x\n    " + pointer.END,
            "mid-line": "see " + pointer.BEGIN + "and " + pointer.END,
        }
        for name, user in cases.items():
            with self.subTest(name):
                self.write("AGENTS.md", user)
                self.assertEqual(link(self.root)[0], 0)
                self.assertEqual(self.read("AGENTS.md"), (BLOCK + user).encode())

    def test_fences_closed_before_block_ok(self):
        for fence in ("```\ncode\n`````\n", "~~~ py\ncode\n~~~\n", "````\n```\n````\n"):
            with self.subTest(fence):
                self.write("AGENTS.md", fence + pointer.BEGIN + "old\n" + pointer.END + "tail\n")
                self.assertEqual(link(self.root)[0], 0)
                self.assertEqual(self.read("AGENTS.md"), (fence + BLOCK + "tail\n").encode())

    def test_block_then_fenced_code_ok(self):
        self.write("AGENTS.md", BLOCK + "```\ncode\n```\n")
        rc, out = link(self.root)
        self.assertEqual(rc, 0)
        self.assertIn("unchanged AGENTS.md", out)

    def test_crlf_without_markers_gets_crlf_block(self):
        user = "# Mine\r\nline\r\n"
        self.write("AGENTS.md", user)
        self.assertEqual(link(self.root)[0], 0)
        self.assertEqual(self.read("AGENTS.md"), (BLOCK.replace("\n", "\r\n") + user).encode())
        rc, out = link(self.root)
        self.assertEqual(rc, 0)
        self.assertIn("unchanged AGENTS.md", out)
        self.assertEqual(pointer.pointer_notices(self.root), [])

    def test_lf_or_no_newline_gets_lf_block(self):
        for user in ("a\nb\n", "no newline"):
            with self.subTest(user):
                self.write("AGENTS.md", user)
                self.assertEqual(link(self.root)[0], 0)
                self.assertEqual(self.read("AGENTS.md"), (BLOCK + user).encode())

    def test_ignore_check_error_refuses(self):
        real = gitview.run_git

        def run_git(root, *args):
            if args[0] == "check-ignore":
                return mock.Mock(returncode=128, stdout="", stderr="fatal")
            return real(root, *args)

        self.write("CLAUDE.md", "mine\n")
        with mock.patch.object(gitview, "run_git", side_effect=run_git):
            rc, out = link(self.root)
        self.assertEqual(rc, 1)
        self.assertIn("refused: could not determine whether AGENTS.md is ignored", out)
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertEqual(self.read("CLAUDE.md"), b"mine\n")

    def test_ignored_or_none(self):
        self.write(".gitignore", "AGENTS.md\n")
        self.assertEqual(gitview.ignored_or_none(self.root, ["AGENTS.md"]), ["AGENTS.md"])
        self.assertEqual(gitview.ignored_or_none(self.root, ["CLAUDE.md"]), [])
        for rc in (128, 124):
            fake = mock.Mock(returncode=rc, stdout="AGENTS.md\n")
            with mock.patch.object(gitview, "run_git", return_value=fake):
                self.assertIsNone(gitview.ignored_or_none(self.root, ["AGENTS.md"]))
                self.assertEqual(gitview.ignored(self.root, ["AGENTS.md"]), [])

    def test_backup_printed_before_failed_write(self):
        out = self.outside()
        self.write("CLAUDE.md", "mine\n")
        with self.swap_to_symlink("CLAUDE.md", out):
            rc, text = link(self.root)
        self.assertEqual(rc, 1)
        self.assertRegex(text, r"backup: .*wikify-backups.*\n(.*\n)*refused: write failed")
        self.assertEqual(text.count("backup: "), 1)

    def test_backup_printed_once_on_success(self):
        self.write("AGENTS.md", "mine\n")
        rc, text = link(self.root)
        self.assertEqual(rc, 0)
        self.assertEqual(text.count("backup: "), 1)
        self.assertLess(text.index("backup: "), text.index("Next:"))


class NoticeTests(LinkCase):
    def test_none_when_block_current(self):
        link(self.root)
        self.assertEqual(pointer.pointer_notices(self.root), [])

    def test_no_block(self):
        self.write("AGENTS.md", "mine\n")
        self.assertEqual(
            pointer.pointer_notices(self.root),
            ["NOTICE: no wikify pointer block in AGENTS.md/CLAUDE.md/GEMINI.md; "
             "run vibe wikify link"],
        )

    def test_target_without_block_when_another_has_one(self):
        link(self.root)
        self.write("CLAUDE.md", "claude rules\n")
        self.write("GEMINI.md", "gemini rules\n")
        self.assertEqual(
            pointer.pointer_notices(self.root),
            [
                "NOTICE: CLAUDE.md has no wikify pointer block; run vibe wikify link",
                "NOTICE: GEMINI.md has no wikify pointer block; run vibe wikify link",
            ],
        )

    def test_symlinked_target_covered_stays_silent(self):
        link(self.root)
        os.symlink("AGENTS.md", self.root / "CLAUDE.md")
        self.assertEqual(pointer.pointer_notices(self.root), [])

    def test_crlf_block_not_stale(self):
        self.write("AGENTS.md", BLOCK.replace("\n", "\r\n") + "x\r\n")
        self.assertEqual(pointer.pointer_notices(self.root), [])

    def test_fenced_marker_only_is_not_a_block(self):
        self.write("AGENTS.md", "```\n" + BLOCK + "```\n")
        self.assertEqual(
            pointer.pointer_notices(self.root),
            ["NOTICE: AGENTS.md has unusable wikify:pointer markers; run vibe wikify link"],
        )

    def test_no_targets_at_all(self):
        self.assertEqual(len(pointer.pointer_notices(self.root)), 1)

    def test_stale(self):
        self.write("AGENTS.md", pointer.BEGIN + "old\n" + pointer.END)
        self.assertEqual(
            pointer.pointer_notices(self.root),
            ["POINTER STALE: AGENTS.md; run vibe wikify link"],
        )

    def test_broken(self):
        link(self.root)
        (self.root / "docs/wiki/index.md").unlink()
        self.assertEqual(
            pointer.pointer_notices(self.root),
            ["POINTER BROKEN: AGENTS.md points at a missing docs/wiki/index.md"],
        )

    def test_unreadable_never_raises(self):
        self.write("AGENTS.md", b"\xff\xfe")
        notes = pointer.pointer_notices(self.root)
        self.assertIn("NOTICE: could not read AGENTS.md", notes)

    def test_verify_prints_notices_rc_unchanged(self):
        rc0, _ = commands.run_verify(self.root)
        self.write("AGENTS.md", pointer.BEGIN + "old\n" + pointer.END)
        rc, lines = commands.run_verify(self.root)
        self.assertEqual(rc, rc0)
        self.assertIn("POINTER STALE: AGENTS.md; run vibe wikify link", lines)


class EndToEndTests(RepoCase):
    """Spec flow: init, page, map, link, then the two commit orders (spec R4)."""

    def quiet(self, fn, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*args)

    def setUp(self):
        super().setUp()
        self.commit("src/a.py", "def foo():\n    return 1\n")
        self.assertEqual(self.quiet(init_cmd.cmd_init, self.root), 0)
        (self.root / "docs/wiki/a.md").write_text("Foo returns one (src: src/a.py:1-2 `foo`)\n")
        (self.root / "docs/wiki/index.md").write_text(
            "# Wiki index\n\n<!-- wikify:map -->\n"
            "- [Foo](a.md) — when changing foo\n<!-- /wikify:map -->\n"
        )
        self.assertEqual(self.quiet(pointer.cmd_link, self.root, False), 0)
        self.assertEqual((self.root / "AGENTS.md").read_text(), BLOCK)

    def push_allowed(self):
        return guard.decide(bash("git push -u origin main", self.root)) is None

    def test_readme_order_is_fresh(self):
        git(self.root, "add", "--", "AGENTS.md")
        git(self.root, "commit", "-q", "-m", "chore: wikify pointer")
        self.assertEqual(self.quiet(commands.cmd_mark, self.root), 0)
        git(self.root, "add", "--", "docs/wiki")
        git(self.root, "commit", "-q", "-m", "docs(wiki): map")
        self.assertEqual(commands.run_verify(self.root)[0], 0)
        self.assertTrue(state.is_fresh(self.root))
        self.assertTrue(self.push_allowed())

    def test_one_commit_with_pointer_is_stale(self):
        self.assertEqual(self.quiet(commands.cmd_mark, self.root), 0)
        git(self.root, "add", "--", "AGENTS.md", "docs/wiki")
        git(self.root, "commit", "-q", "-m", "everything")
        self.assertFalse(state.is_fresh(self.root))
        self.assertFalse(self.push_allowed())
