import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
VERIFY_PATH = ROOT / "agents" / "kits" / "guardrails" / "templates" / "guardrails" / "hooks" / "vibe-guardrails" / "verify.py"

spec = importlib.util.spec_from_file_location("verify", VERIFY_PATH)
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)

UNFORMATTED = "package main\nfunc main(){\nx:=1\n_ = x}\n"
FORMATTED = "package main\n\nfunc main() {\n\tx := 1\n\t_ = x\n}\n"


@unittest.skipUnless(shutil.which("gofmt"), "gofmt not installed")
class VerifyTests(unittest.TestCase):
    def _run(self, path: str, env: dict | None = None) -> tuple[int, str]:
        payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": path}})
        stderr = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(payload)), mock.patch.object(
            sys, "stderr", stderr
        ), mock.patch.dict(os.environ, env or {}, clear=False):
            rc = verify.main()
        return rc, stderr.getvalue()

    def _go_file(self, tmp: str, content: str, name: str = "main.go") -> str:
        path = Path(tmp) / name
        path.write_text(content, encoding="utf-8")
        return str(path)

    def test_unformatted_go_file_warns_with_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, err = self._run(self._go_file(tmp, UNFORMATTED))
        self.assertEqual(rc, 2)
        self.assertIn("gofmt", err)

    def test_formatted_go_file_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._run(self._go_file(tmp, FORMATTED)), (0, ""))

    def test_non_go_file_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._run(self._go_file(tmp, UNFORMATTED, "notes.txt")), (0, ""))

    def test_missing_file_fails_open(self):
        self.assertEqual(self._run("/nonexistent/x.go")[0], 0)

    def test_env_override_disables(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, _ = self._run(self._go_file(tmp, UNFORMATTED), env={"VIBE_GUARDRAILS": "off"})
        self.assertEqual(rc, 0)


class VerifyFailOpenTests(unittest.TestCase):
    def test_malformed_stdin_fails_open(self):
        with mock.patch.object(sys, "stdin", io.StringIO("{nope")):
            self.assertEqual(verify.main(), 0)

    def test_missing_gofmt_fails_open(self):
        payload = json.dumps({"tool_input": {"file_path": "/x/main.go"}})
        with mock.patch.object(sys, "stdin", io.StringIO(payload)), mock.patch.object(
            verify.shutil, "which", return_value=None
        ):
            self.assertEqual(verify.main(), 0)


if __name__ == "__main__":
    unittest.main()
