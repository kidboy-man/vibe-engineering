import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents.wikify import gitview, state

STATE = "docs/wiki/.wikify.json"


def git(root, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout.strip()


class RepoCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        git(self.root, "init", "-q", "-b", "main")

    def commit(self, rel, content="x\n", msg="c"):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        git(self.root, "add", rel)
        git(self.root, "commit", "-q", "-m", msg)

    def mark(self):
        state.save(self.root, gitview.head(self.root))
        git(self.root, "add", STATE)
        git(self.root, "commit", "-q", "-m", "mark")


class StateTests(RepoCase):
    def test_empty_repo(self):
        self.assertIsNone(gitview.head(self.root))
        self.assertTrue(state.is_fresh(self.root))
        self.assertIsNone(state.base(self.root))
        self.assertEqual(gitview.tracked_files(self.root), [])
        self.assertIsNone(gitview.show_head(self.root, "a"))

    def test_docs_only_after_mark_is_fresh(self):
        self.commit("src/a.py")
        self.mark()
        self.commit("docs/wiki/x.md")
        self.assertTrue(state.is_fresh(self.root))

    def test_code_after_mark_is_stale(self):
        self.commit("src/a.py")
        self.mark()
        self.commit("src/b.py")
        self.assertFalse(state.is_fresh(self.root))

    def test_untracked_state_is_stale(self):
        self.commit("src/a.py")
        state.save(self.root, gitview.head(self.root))
        self.assertIsNone(state.base(self.root))
        self.assertFalse(state.is_fresh(self.root))

    def test_history_rewrite_amend(self):
        self.commit("src/a.py")
        self.commit("src/b.py")
        self.mark()
        self.commit("docs/wiki/x.md")
        git(self.root, "rebase", "-q", "--root", "--exec", "git -c commit.gpgsign=false commit --amend -q --no-edit --reset-author")
        self.assertTrue(state.is_fresh(self.root))

    def test_history_rewrite_squash(self):
        self.commit("src/a.py")
        self.commit("src/b.py")
        self.commit("src/c.py")
        git(self.root, "reset", "-q", "--soft", "HEAD~2")
        git(self.root, "commit", "-q", "-m", "squash")
        self.mark()
        self.commit("docs/wiki/x.md")
        self.assertTrue(state.is_fresh(self.root))

    def test_squash_merge_needs_one_remark(self):
        """Documented limitation (R18): a squash merge folds code and the state
        file into one mixed commit, so the wiki reads stale until one more
        mark + docs-only commit. The hook must agree at every step."""
        from tests.test_wikify_hook import bash, guard

        def fresh():
            got = state.is_fresh(self.root)
            self.assertEqual(guard.decide(bash("git push", self.root)) is None, got)
            return got

        self.commit("src/a.py")
        self.mark()
        git(self.root, "checkout", "-q", "-b", "feat")
        self.commit("src/b.py")
        self.mark()
        self.commit("docs/wiki/x.md")
        self.assertTrue(fresh())
        git(self.root, "checkout", "-q", "main")
        git(self.root, "merge", "-q", "--squash", "feat")
        git(self.root, "commit", "-q", "-m", "feat (squashed)")
        self.assertFalse(fresh())
        self.mark()
        self.assertTrue(fresh())
        self.commit("docs/wiki/y.md")
        self.assertTrue(fresh())

    def test_corrupt_state_defaults(self):
        p = self.root / STATE
        p.parent.mkdir(parents=True)
        default = {"version": 1, "covered": None}
        for bad in ("[]", '{"covered": 5}', "not json", '"s"', '{"covered": ["a"]}'):
            p.write_text(bad)
            self.assertEqual(state.load(self.root), default, bad)
        self.assertEqual(state.load(self.root / "nope"), default)

    def test_load_valid(self):
        state.save(self.root, "abc")
        self.assertEqual(state.load(self.root), {"version": 1, "covered": "abc"})

    def test_loop_proof(self):
        self.commit("src/a.py")
        self.mark()
        self.commit("src/b.py")
        self.assertFalse(state.is_fresh(self.root))
        self.mark()
        self.assertTrue(state.is_fresh(self.root))

    def test_save_differs_per_head(self):
        self.commit("src/a.py")
        state.save(self.root, gitview.head(self.root))
        first = (self.root / STATE).read_text()
        self.commit("src/b.py")
        state.save(self.root, gitview.head(self.root))
        self.assertNotEqual(first, (self.root / STATE).read_text())

    def test_every_git_call_has_timeout_and_timeout_failsafe(self):
        self.commit("src/a.py")
        real = subprocess.run
        seen = []

        def spy(*a, **kw):
            seen.append(kw.get("timeout"))
            return real(*a, **kw)

        with mock.patch.object(gitview.subprocess, "run", spy):
            gitview.head(self.root)
            gitview.tracked_files(self.root)
            gitview.changed_since(self.root, "HEAD")
            state.is_fresh(self.root)
        self.assertTrue(seen)
        self.assertTrue(all(t == 10 for t in seen))

        boom = subprocess.TimeoutExpired(["git"], 10)
        with mock.patch.object(gitview.subprocess, "run", side_effect=boom):
            self.assertEqual(gitview.run_git(self.root, "status").returncode, 124)
            self.assertIsNone(gitview.head(self.root))
            self.assertIsNone(gitview.changed_since(self.root, "x"))
            self.assertEqual(gitview.tracked_files(self.root), [])

    def test_base_commit_mixing_code_is_stale(self):
        (self.root / "src").mkdir()
        (self.root / "src/a.py").write_text("x")
        state.save(self.root, None)
        git(self.root, "add", "src/a.py", STATE)
        git(self.root, "commit", "-q", "-m", "mixed")
        self.assertFalse(state.is_fresh(self.root))

    def test_base_commit_docs_only_root_is_fresh(self):
        state.save(self.root, None)
        git(self.root, "add", STATE)
        git(self.root, "commit", "-q", "-m", "root")
        self.assertTrue(state.is_fresh(self.root))

    def test_deleted_since_and_changed_since(self):
        self.commit("src/a.py")
        base = gitview.head(self.root)
        git(self.root, "rm", "-q", "src/a.py")
        git(self.root, "commit", "-q", "-m", "rm")
        self.assertEqual(gitview.deleted_since(self.root, base), ["src/a.py"])
        self.assertEqual(gitview.changed_since(self.root, base), ["src/a.py"])
        self.assertIsNone(gitview.changed_since(self.root, "deadbeef"))
        self.assertEqual(gitview.repo_root(self.root), self.root.resolve())
        self.assertIsNone(gitview.repo_root("/"))

    def test_show_head_binary_does_not_raise(self):
        p = self.root / "img.png"
        p.write_bytes(b"\x89PNG\xff\xfe\x00\x80")
        git(self.root, "add", "img.png")
        git(self.root, "commit", "-q", "-m", "bin")
        self.assertIsInstance(gitview.show_head(self.root, "img.png"), str)

    def test_non_ascii_paths(self):
        self.commit("src/ü.py")
        self.mark()
        self.commit("docs/wiki/é.md")
        self.assertEqual(
            sorted(gitview.tracked_files(self.root)),
            sorted(["src/ü.py", "docs/wiki/é.md", STATE]),
        )
        self.assertTrue(state.is_fresh(self.root))


if __name__ == "__main__":
    unittest.main()
