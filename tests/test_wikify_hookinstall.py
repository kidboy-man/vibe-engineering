import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from agents.wikify import hookinstall
from tests.test_wikify_state import RepoCase, git
from tests.wikify_drift_helpers import quiet


class InstallHookTests(RepoCase):
    def setUp(self):
        super().setUp()
        self.commit("a.txt")
        self.hook = self.root / ".git/hooks/pre-push"

    def run_install(self, apply=False):
        return quiet(hookinstall.cmd_install_hook, self.root, apply)

    def test_dry_run_prints_target_and_script_and_writes_nothing(self):
        before = sorted(p.name for p in (self.root / ".git/hooks").iterdir())
        rc, out = self.run_install()
        self.assertEqual(rc, 0)
        self.assertIn("pre-push", out)
        self.assertIn("vibe wikify check --ci", out)
        self.assertFalse(self.hook.exists())
        self.assertEqual(sorted(p.name for p in (self.root / ".git/hooks").iterdir()), before)

    def test_apply_writes_an_executable_hook_only_when_absent(self):
        rc, out = self.run_install(apply=True)
        self.assertEqual(rc, 0, out)
        self.assertTrue(self.hook.is_file())
        self.assertEqual(stat.S_IMODE(self.hook.stat().st_mode), 0o755)
        self.assertTrue(self.hook.read_text().startswith("#!/bin/sh\n"))

    def test_existing_hook_is_never_overwritten(self):
        self.hook.write_text("#!/bin/sh\necho mine\n")
        for apply in (False, True):
            rc, out = self.run_install(apply)
            self.assertEqual(rc, 1)
            self.assertIn("already exists", out)
        self.assertEqual(self.hook.read_text(), "#!/bin/sh\necho mine\n")

    def test_existing_symlink_hook_is_never_overwritten(self):
        target = self.root / "elsewhere.sh"
        target.write_text("#!/bin/sh\n")
        self.hook.symlink_to(target)
        self.assertEqual(self.run_install(True)[0], 1)
        self.assertEqual(target.read_text(), "#!/bin/sh\n")

    def test_custom_hooks_path_is_refused(self):
        git(self.root, "config", "core.hooksPath", ".husky")
        for apply in (False, True):
            rc, out = self.run_install(apply)
            self.assertEqual(rc, 1)
            self.assertIn("core.hooksPath", out)
        self.assertFalse(self.hook.exists())
        self.assertFalse((self.root / ".husky/pre-push").exists())

    def test_linked_worktree_uses_the_shared_hooks_directory(self):
        wt = self.root.parent / (self.root.name + "-wt")
        git(self.root, "worktree", "add", "-q", str(wt), "-b", "other")
        self.addCleanup(lambda: subprocess.run(
            ["git", "worktree", "remove", "--force", str(wt)], cwd=self.root, check=False))
        rc, out = quiet(hookinstall.cmd_install_hook, wt, True)
        self.assertEqual(rc, 0, out)
        self.assertTrue(self.hook.is_file())

    def test_not_a_git_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, out = quiet(hookinstall.cmd_install_hook, tmp, True)
        self.assertEqual(rc, 1)
        self.assertIn("not a git repository", out)


class ScriptTests(RepoCase):
    def setUp(self):
        super().setUp()
        self.commit("a.txt")
        quiet(hookinstall.cmd_install_hook, self.root, True)
        self.hook = self.root / ".git/hooks/pre-push"
        self.bin = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.bin, ignore_errors=True))

    def run_hook(self, path):
        env = {**os.environ, "PATH": path}
        return subprocess.run([str(self.hook)], cwd=self.root, env=env, capture_output=True, text=True)

    def fake_vibe(self, exit_code):
        script = self.bin / "vibe"
        script.write_text(f"#!/bin/sh\necho \"$@\" > {self.bin}/args\nexit {exit_code}\n")
        script.chmod(0o755)

    def test_script_runs_check_ci_and_propagates_failure(self):
        for code in (0, 1):
            self.fake_vibe(code)
            result = self.run_hook(f"{self.bin}:/usr/bin:/bin")
            self.assertEqual(result.returncode, code)
            self.assertEqual((self.bin / "args").read_text().strip(), "wikify check --ci")

    def test_script_fails_closed_when_vibe_is_missing(self):
        result = self.run_hook(str(self.bin))
        self.assertEqual(result.returncode, 1)
        self.assertIn("vibe", result.stderr)


if __name__ == "__main__":
    unittest.main()
