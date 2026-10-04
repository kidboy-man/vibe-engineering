import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents.wikify import gitview, state

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "agents/kits/wikify/templates/wikify/hooks/vibe-wikify/wikify_guard.py"
STATE = "docs/wiki/.wikify.json"
MESSAGE = (
    "wikify: docs/wiki is out of date for this push. Follow docs/wiki/WIKIFY.md: run "
    "'vibe wikify plan', update the wiki, run 'vibe wikify verify' and 'vibe wikify mark', "
    "show the user the wiki diff and scan result, and only after the user confirms commit "
    "with 'git add -- docs/wiki'. Set VIBE_WIKIFY=off to bypass."
)
BRANCH = "secretbranch"
SUBJECT = "zzsubjectzz"
CODE_FILE = "src/zzcodefile.py"


def load_module():
    spec = importlib.util.spec_from_file_location("wikify_guard", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = load_module()


def git(root, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout.strip()


def bash(command, cwd):
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}


class RepoCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        git(self.root, "init", "-q", "-b", BRANCH)

    def commit(self, rel, content="x\n", msg=SUBJECT):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        git(self.root, "add", rel)
        git(self.root, "commit", "-q", "-m", msg)

    def mark(self):
        state.save(self.root, gitview.head(self.root))
        git(self.root, "add", STATE)
        git(self.root, "commit", "-q", "-m", "mark")

    def push(self, command="git push -u origin main"):
        return guard.decide(bash(command, self.root))

    def run_script(self, stdin, *argv, env=None):
        full_env = {**os.environ, **(env or {})}
        return subprocess.run(
            [sys.executable, str(SCRIPT), *argv], input=stdin, capture_output=True,
            text=True, env=full_env, check=False, timeout=60,
        )


class DecideTests(RepoCase):
    def test_new_branch_without_upstream_blocked_when_stale(self):
        self.commit(CODE_FILE)
        self.mark()
        self.commit("src/b.py")
        self.assertTrue(self.push())

    def test_docs_only_since_mark_allowed(self):
        self.commit(CODE_FILE)
        self.mark()
        self.commit("docs/wiki/x.md")
        self.assertIsNone(self.push())

    def test_state_never_committed_blocked(self):
        self.commit(CODE_FILE)
        state.save(self.root, gitview.head(self.root))
        self.assertTrue(self.push())

    def test_base_commit_mixing_code_blocked(self):
        (self.root / "src").mkdir()
        (self.root / "src/a.py").write_text("x")
        state.save(self.root, None)
        git(self.root, "add", "src/a.py", STATE)
        git(self.root, "commit", "-q", "-m", "mixed")
        self.assertTrue(self.push())

    def test_allowed_after_rebase_amend_docs_only(self):
        self.commit("src/a.py")
        self.commit("src/b.py")
        self.mark()
        self.commit("docs/wiki/x.md")
        git(self.root, "rebase", "-q", "--root", "--exec",
            "git -c commit.gpgsign=false commit --amend -q --no-edit --reset-author")
        self.assertIsNone(self.push())

    def test_parity_with_is_fresh(self):
        def empty(r):
            pass

        def fresh(r):
            r.commit("src/a.py"); r.mark(); r.commit("docs/wiki/x.md")

        def stale(r):
            r.commit("src/a.py"); r.mark(); r.commit("src/b.py")

        def untracked(r):
            r.commit("src/a.py"); state.save(r.root, gitview.head(r.root))

        def mixed(r):
            (r.root / "src").mkdir()
            (r.root / "src/a.py").write_text("x")
            state.save(r.root, None)
            git(r.root, "add", "src/a.py", STATE)
            git(r.root, "commit", "-q", "-m", "mixed")

        def root_state(r):
            state.save(r.root, None)
            git(r.root, "add", STATE)
            git(r.root, "commit", "-q", "-m", "root")

        def remark(r):
            stale(r); r.mark()

        for build in (empty, fresh, stale, untracked, mixed, root_state, remark):
            with self.subTest(build.__name__):
                self.setUp()
                if build is empty:
                    state.save(self.root, None)  # wikified but no commits
                build(self)
                (self.root / STATE).parent.mkdir(parents=True, exist_ok=True)
                if not (self.root / STATE).exists():
                    state.save(self.root, None)
                blocked = self.push() is not None
                self.assertEqual(blocked, not state.is_fresh(self.root))

    def test_hung_git_allows_within_timeout(self):
        self.commit(CODE_FILE)
        state.save(self.root, gitview.head(self.root))  # stale
        self.assertTrue(self.push())
        shim = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(shim, ignore_errors=True))
        fake = shim / "git"
        fake.write_text("#!/bin/sh\nexec sleep 5\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        with mock.patch.object(guard, "TIMEOUT_SECONDS", 1), mock.patch.dict(
            os.environ, {"PATH": f"{shim}{os.pathsep}{os.environ['PATH']}"}
        ):
            import time
            start = time.monotonic()
            self.assertIsNone(self.push())
            self.assertLess(time.monotonic() - start, 4)

    def test_every_git_call_has_timeout(self):
        self.commit(CODE_FILE)
        self.mark()
        real = subprocess.run
        seen = []

        def spy(*a, **kw):
            seen.append(kw.get("timeout"))
            return real(*a, **kw)

        with mock.patch.object(guard.subprocess, "run", spy):
            self.push()
        self.assertTrue(seen)
        self.assertTrue(all(t == 10 for t in seen))

    def test_not_wikified_allowed(self):
        self.commit(CODE_FILE)
        self.assertIsNone(self.push())

    def test_no_commits_allowed(self):
        state.save(self.root, None)
        self.assertIsNone(self.push())

    def test_never_creates_files(self):
        self.commit(CODE_FILE)
        before = sorted(p for p in self.root.rglob("*") if ".git" not in p.parts)
        self.push()
        after = sorted(p for p in self.root.rglob("*") if ".git" not in p.parts)
        self.assertEqual(before, after)

    def _stale_repo(self):
        self.commit(CODE_FILE)
        state.save(self.root, gitview.head(self.root))

    def test_allowed_commands(self):
        self._stale_repo()
        for cmd in (
            "git push --delete origin x", "git push -d origin x", "git push --dry-run",
            "git push -n", "git status", "git commit -m x", "ls", "echo git push",
        ):
            with self.subTest(cmd):
                self.assertIsNone(self.push(cmd))

    def test_blocked_variants(self):
        self._stale_repo()
        (self.root / "sub").mkdir()
        for cmd in (
            "git push", "git push --tags", "sudo git push", "env FOO=1 git push",
            "FOO=1 git push", "git -c a=b push", "git status && git push origin main",
            "cd sub && git push", f"git -C {self.root} push", "git push || true",
        ):
            with self.subTest(cmd):
                self.assertTrue(self.push(cmd))

    def test_git_dash_c_dir_and_cd_relative(self):
        self._stale_repo()
        other = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(other, ignore_errors=True))
        git(other, "init", "-q")
        payload_cwd = other
        self.assertTrue(guard.decide(bash(f"git -C {self.root} push", payload_cwd)))
        self.assertTrue(guard.decide(bash(f"cd {self.root} && git push", payload_cwd)))
        self.assertIsNone(guard.decide(bash("git push", payload_cwd)))
        self.assertIsNone(guard.decide(bash("cd /nonexistent/zz && git push", self.root)))
        self.assertIsNone(guard.decide(bash("git -C /nonexistent/zz push", self.root)))

    def test_non_shell_tools_and_bad_payloads_allowed(self):
        self._stale_repo()
        self.assertIsNone(guard.decide({**bash("git push", self.root), "tool_name": "Write"}))
        self.assertTrue(guard.decide({"command": "git push", "cwd": str(self.root)}))
        for bad in (None, [], "x", {}, {"tool_input": "x"}):
            self.assertIsNone(guard.decide(bad))


class ScriptTests(RepoCase):
    def stale(self):
        self.commit(CODE_FILE)
        self.mark()
        self.commit("src/b.py")

    def payload(self, command="git push -u origin main"):
        return json.dumps(bash(command, self.root))

    def test_block_exit_2_exact_stderr(self):
        self.stale()
        result = self.run_script(self.payload())
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr.strip(), MESSAGE)
        for leak in (BRANCH, SUBJECT, CODE_FILE, "zzcodefile", "b.py"):
            self.assertNotIn(leak, result.stderr)

    def test_allow_exit_0(self):
        self.stale()
        for stdin in (self.payload("git status"), "{not json", "", "null"):
            with self.subTest(stdin):
                result = self.run_script(stdin)
                self.assertEqual((result.returncode, result.stderr), (0, ""))

    def test_off_switch(self):
        self.stale()
        for value in ("off", "OFF"):
            result = self.run_script(self.payload(), env={"VIBE_WIKIFY": value})
            self.assertEqual(result.returncode, 0)

    def test_cursor_format_always_json(self):
        self.stale()
        deny = self.run_script(self.payload(), "--format=cursor")
        self.assertEqual(deny.returncode, 2)
        out = json.loads(deny.stdout)
        self.assertEqual(out["permission"], "deny")
        self.assertEqual(out["agent_message"], MESSAGE)
        for stdin, env in (
            ("{bad json", None), ("", None), (self.payload("git status"), None),
            (self.payload(), {"VIBE_WIKIFY": "off"}),
        ):
            with self.subTest(stdin=stdin, env=env):
                result = self.run_script(stdin, "--format=cursor", env=env)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(json.loads(result.stdout), {"permission": "allow"})

    def test_cursor_format_split_argv(self):
        result = self.run_script("{bad", "--format", "cursor")
        self.assertEqual(json.loads(result.stdout), {"permission": "allow"})


if __name__ == "__main__":
    unittest.main()
