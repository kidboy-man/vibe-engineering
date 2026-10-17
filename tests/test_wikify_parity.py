"""The agent hook, `check --ci` and the installed pre-push script return one verdict."""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents.wikify import check_cmd, hookinstall, state
from tests.test_wikify_state import git
from tests.wikify_drift_helpers import DriftCase, quiet, svc_source

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "agents/kits/wikify/templates/wikify/hooks/vibe-wikify/wikify_guard.py"
spec = importlib.util.spec_from_file_location("wikify_guard_parity", SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class ParityCase(DriftCase):
    def setUp(self):
        super().setUp()
        self.bin = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.bin, ignore_errors=True))
        wrapper = self.bin / "vibe"
        wrapper.write_text(
            f"#!/bin/sh\nexec env PYTHONPATH={REPO} {sys.executable} -m agents.cli \"$@\"\n"
        )
        wrapper.chmod(0o755)
        patcher = mock.patch.object(guard, "_find_vibe", return_value=str(wrapper))
        patcher.start()
        self.addCleanup(patcher.stop)
        quiet(hookinstall.cmd_install_hook, self.root, True)

    def verdicts(self):
        """(hook blocks, check --ci fails, pre-push script fails)."""
        hook = guard.decide(
            {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}, "cwd": str(self.root)}
        )
        check = quiet(check_cmd.cmd_check, self.root, True)[0]
        env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}"}
        script = subprocess.run(
            [str(self.root / ".git/hooks/pre-push")], cwd=self.root, env=env, capture_output=True, text=True,
            input="refs/heads/main 1111111111111111111111111111111111111111 refs/heads/main 2222222222222222222222222222222222222222\n"
        )
        return hook is not None, check != 0, script.returncode != 0


class ParityTests(ParityCase):
    def test_clean(self):
        self.assertEqual(self.verdicts(), (False, False, False))

    def test_drifting_commit_is_blocked_everywhere(self):
        self.write_code(svc_source(tag="!"))
        self.assertEqual(self.verdicts(), (True, True, True))

    def test_squash_merge_is_allowed_everywhere(self):
        self.commit("src/other.py", "x = 1\n")
        git(self.root, "reset", "--soft", "HEAD~1")
        state.save(self.root, state.load(self.root)["covered"], citations=state.load(self.root)["citations"])
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "squash")
        self.assertFalse(state.is_fresh(self.root))
        self.assertEqual(self.verdicts(), (False, False, False))

    def test_moved_only_is_allowed_everywhere(self):
        self.insert_lines_above(15)
        self.assertEqual(self.verdicts(), (False, False, False))

    def test_unbaselined_citations_are_the_documented_exception(self):
        state.save(self.root, state.load(self.root)["covered"], citations={})
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "docs(wiki): drop hashes")
        self.insert_lines_above(2)  # symbol stays inside the old range, so check sees nothing wrong
        hook_blocks, check_fails, script_fails = self.verdicts()
        self.assertTrue(hook_blocks)  # FR-019: the hook keeps the commit-order rule here
        self.assertFalse(check_fails)
        self.assertFalse(script_fails)


if __name__ == "__main__":
    unittest.main()
