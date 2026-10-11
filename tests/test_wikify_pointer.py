import contextlib
import io
import os
from pathlib import Path

from agents.wikify import commands, gitview, pointer
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
