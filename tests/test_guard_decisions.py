import importlib.util
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
GUARD_PATH = ROOT / "agents" / "kits" / "guardrails" / "templates" / "guardrails" / "hooks" / "vibe-guardrails" / "guard.py"

spec = importlib.util.spec_from_file_location("guard", GUARD_PATH)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

CWD = "/work/repo"


def bash(command: str, tool: str = "Bash") -> dict:
    return {"tool_name": tool, "tool_input": {"command": command}, "cwd": CWD}


def file_tool(path: str, tool: str = "Read") -> dict:
    return {"tool_name": tool, "tool_input": {"file_path": path}, "cwd": CWD}


BLOCKED = [
    ("rm -rf root", bash("rm -rf /")),
    ("rm -rf root glob", bash("rm -rf /*")),
    ("rm -rf home tilde", bash("rm -rf ~")),
    ("rm -rf home var", bash("rm -rf $HOME/projects")),
    ("rm -fr outside cwd", bash("rm -fr /etc/nginx")),
    ("rm --recursive parent", bash("rm --recursive --force ../other")),
    ("rm -rf cwd dot", bash("rm -rf .")),
    ("rm chained", bash("make build && rm -rf /var/lib")),
    ("rm cwd itself", bash("rm -rf /work/repo")),
    ("rm cwd itself trailing slash", bash("rm -rf /work/repo/")),
    ("rm outside when cwd is root", {**bash("rm -rf /home/u/projects"), "cwd": "/"}),
    ("rm outside when cwd is home", {**bash("rm -rf /home/u/projects"), "cwd": os.path.expanduser("~")}),
    (
        "notebook edit of secret",
        {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": "/work/repo/.env"}},
    ),
    ("force push", bash("git push --force origin main")),
    ("force push short", bash("git push -f origin main")),
    ("force push after remote", bash("git push origin main --force")),
    ("reset hard", bash("git reset --hard HEAD~3")),
    ("clean fdx", bash("git clean -fdx")),
    ("psql drop", bash('psql -c "DROP TABLE users"')),
    ("mysql truncate", bash("mysql -e 'truncate table orders'")),
    ("cat env", bash("cat .env")),
    ("cat env local", bash("cat .env.local")),
    ("head pem", bash("head -n1 certs/server.pem")),
    ("cat ssh key", bash("cat ~/.ssh/id_rsa")),
    ("cat aws creds", bash("cat ~/.aws/credentials")),
    ("redirect into env", bash("echo SECRET=1 > .env")),
    ("append into env", bash("echo SECRET=1 >> .env.production")),
    ("read tool env", file_tool("/work/repo/.env")),
    ("read tool ssh key", file_tool("/home/u/.ssh/id_ed25519")),
    ("write tool env", file_tool("/work/repo/.env", tool="Write")),
    ("edit tool pem", file_tool("/work/repo/tls/key.pem", tool="Edit")),
    ("aws creds via read tool", file_tool("/home/u/.aws/credentials")),
    ("cursor shell payload", {"command": "git push --force", "cwd": CWD}),
    ("cursor read payload", {"file_path": "/work/repo/.env"}),
    ("shell tool name", bash("rm -rf /", tool="Shell")),
    (
        "codex apply_patch touching env",
        {
            "tool_name": "apply_patch",
            "tool_input": {"command": "*** Begin Patch\n*** Update File: .env\n@@\n-A=1\n+A=2\n*** End Patch"},
        },
    ),
]

ALLOWED = [
    ("rm build dir", bash("rm -rf ./build")),
    ("rm node_modules", bash("rm -rf node_modules")),
    ("rm under cwd absolute", bash("rm -rf /work/repo/dist")),
    ("rm tmp", bash("rm -rf /tmp/scratch")),
    ("rm single file", bash("rm notes.txt")),
    ("rm force only", bash("rm -f notes.txt")),
    ("force with lease", bash("git push --force-with-lease origin feature")),
    ("normal push", bash("git push origin feature")),
    ("reset soft", bash("git reset --soft HEAD~1")),
    ("clean dry run", bash("git clean -n")),
    ("psql select", bash('psql -c "SELECT 1"')),
    ("drop in echo", bash('echo "DROP TABLE is dangerous"')),
    ("env example", bash("cat .env.example")),
    ("env sample read tool", file_tool("/work/repo/.env.sample")),
    ("public key", bash("cat ~/.ssh/id_rsa.pub")),
    ("gitignore mention", bash("echo .env >> .gitignore")),
    ("grep mentions env in quotes", bash('grep -rn "\\.env" README.md')),
    ("ordinary read", file_tool("/work/repo/main.go")),
    ("ordinary write", file_tool("/work/repo/main.go", tool="Write")),
    ("apply_patch normal", {"tool_name": "apply_patch", "tool_input": {"command": "*** Update File: main.go\n"}}),
    ("empty payload", {}),
    ("no command", {"tool_name": "Bash", "tool_input": {}}),
    ("non-dict tool_input", {"tool_name": "Bash", "tool_input": "oops"}),
    ("unbalanced quote falls back", bash("echo 'unterminated")),
]


class DecideTests(unittest.TestCase):
    def test_blocked(self):
        for name, payload in BLOCKED:
            with self.subTest(name):
                reason = guard.decide(payload)
                self.assertTrue(reason, f"expected block for {name}")

    def test_allowed(self):
        for name, payload in ALLOWED:
            with self.subTest(name):
                self.assertIsNone(guard.decide(payload), f"expected allow for {name}")

    def test_non_dict_payload_allowed(self):
        for payload in (None, [], "x", 3):
            with self.subTest(payload=payload):
                self.assertIsNone(guard.decide(payload))


class MainTests(unittest.TestCase):
    def _run(self, stdin_text: str, env: dict | None = None, argv: list[str] | None = None) -> tuple[int, str]:
        rc, _, err = self._run_full(stdin_text, env, argv)
        return rc, err

    def _run_full(
        self, stdin_text: str, env: dict | None = None, argv: list[str] | None = None
    ) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(stdin_text)), mock.patch.object(
            sys, "stdout", stdout
        ), mock.patch.object(sys, "stderr", stderr), mock.patch.dict(os.environ, env or {}, clear=False):
            rc = guard.main(argv or [])
        return rc, stdout.getvalue(), stderr.getvalue()

    def test_block_exits_2_with_reason_on_stderr(self):
        rc, err = self._run(json.dumps(bash("git push --force")))
        self.assertEqual(rc, 2)
        self.assertIn("force", err.lower())

    def test_allow_exits_0_silently(self):
        rc, err = self._run(json.dumps(bash("ls -la")))
        self.assertEqual((rc, err), (0, ""))

    def test_malformed_json_fails_open(self):
        rc, err = self._run("{not json")
        self.assertEqual(rc, 0)

    def test_empty_stdin_fails_open(self):
        rc, _ = self._run("")
        self.assertEqual(rc, 0)

    def test_env_override_disables_guard(self):
        rc, _ = self._run(json.dumps(bash("git push --force")), env={"VIBE_GUARDRAILS": "off"})
        self.assertEqual(rc, 0)

    def test_claude_format_prints_nothing_on_stdout(self):
        rc, out, _ = self._run_full(json.dumps(bash("ls")))
        self.assertEqual((rc, out), (0, ""))

    def test_internal_error_fails_open(self):
        with mock.patch.object(guard, "decide", side_effect=RuntimeError("boom")):
            rc, _ = self._run(json.dumps(bash("git push --force")))
        self.assertEqual(rc, 0)


class CursorFormatTests(unittest.TestCase):
    """Cursor treats empty stdout from a permission hook as invalid and blocks, so
    --format=cursor must always print a permission JSON object."""

    ARGV = ["--format=cursor"]

    def _run(self, stdin_text: str, env: dict | None = None, argv: list[str] | None = None) -> tuple[int, dict, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(stdin_text)), mock.patch.object(
            sys, "stdout", stdout
        ), mock.patch.object(sys, "stderr", stderr), mock.patch.dict(os.environ, env or {}, clear=False):
            rc = guard.main(self.ARGV if argv is None else argv)
        return rc, json.loads(stdout.getvalue()), stderr.getvalue()

    def test_allow_prints_allow_json(self):
        rc, out, _ = self._run(json.dumps({"command": "ls -la", "cwd": CWD}))
        self.assertEqual((rc, out), (0, {"permission": "allow"}))

    def test_deny_prints_deny_json_and_exits_2(self):
        rc, out, err = self._run(json.dumps({"command": "git push --force", "cwd": CWD}))
        self.assertEqual(rc, 2)
        self.assertEqual(out["permission"], "deny")
        self.assertIn("force", out["user_message"])
        self.assertIn("force", out["agent_message"])
        self.assertIn("force", err)

    def test_read_file_payload_denied(self):
        rc, out, _ = self._run(json.dumps({"file_path": "/work/repo/.env", "content": "A=1"}))
        self.assertEqual((rc, out["permission"]), (2, "deny"))

    def test_fail_open_paths_still_print_allow_json(self):
        cases = {
            "malformed": ("{nope", None),
            "empty": ("", None),
            "override": (json.dumps({"command": "git push --force"}), {"VIBE_GUARDRAILS": "off"}),
        }
        for name, (stdin_text, env) in cases.items():
            with self.subTest(name):
                rc, out, _ = self._run(stdin_text, env=env)
                self.assertEqual((rc, out), (0, {"permission": "allow"}))

    def test_internal_error_prints_allow_json(self):
        with mock.patch.object(guard, "decide", side_effect=RuntimeError("boom")):
            rc, out, _ = self._run(json.dumps({"command": "git push --force"}))
        self.assertEqual((rc, out), (0, {"permission": "allow"}))

    def test_space_separated_flag_form_accepted(self):
        rc, out, _ = self._run(json.dumps({"command": "ls"}), argv=["--format", "cursor"])
        self.assertEqual(out, {"permission": "allow"})


if __name__ == "__main__":
    unittest.main()
