import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.kits.guardrails.installer import diff_kit, doctor, install, uninstall

GUARD_REL = "hooks/vibe-guardrails/guard.py"
VERIFY_REL = "hooks/vibe-guardrails/verify.py"
CLAUDE_MATCHER = "Bash|Read|Edit|Write|MultiEdit|NotebookEdit"


def make_home(tmp: str, *agents: str) -> Path:
    home = Path(tmp)
    for agent in agents:
        (home / agent).mkdir()
    return home


def run(fn, **kwargs) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        rc = fn(**kwargs)
    return rc, out.getvalue()


def do_install(home: Path, **kwargs) -> tuple[int, str]:
    return run(install, home=str(home), yes=True, **kwargs)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class InstallTests(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", ".codex", ".cursor")
            rc, _ = run(install, home=str(home), dry_run=True, yes=True)
            self.assertEqual(rc, 0)
            self.assertEqual(list((home / ".claude").iterdir()), [])
            self.assertEqual(list((home / ".codex").iterdir()), [])
            self.assertEqual(list((home / ".cursor").iterdir()), [])
            self.assertFalse((home / ".vibe-guardrails").exists())

    def test_no_agent_dirs_installs_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, out = do_install(Path(tmp))
            self.assertEqual(rc, 1)
            self.assertIn("no supported agent", out)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_only_existing_agent_dirs_are_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            rc, out = do_install(home)
            self.assertEqual(rc, 0)
            self.assertTrue((home / ".claude" / GUARD_REL).exists())
            self.assertFalse((home / ".codex").exists())
            self.assertFalse((home / ".cursor").exists())
            self.assertIn("skipping Codex CLI", out)

    def test_claude_registers_pretooluse_with_matcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            groups = read_json(home / ".claude" / "settings.json")["hooks"]["PreToolUse"]
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["matcher"], CLAUDE_MATCHER)
            self.assertEqual(groups[0]["hooks"][0]["command"], f'python3 "{home / ".claude" / GUARD_REL}"')

    def test_codex_registers_pretooluse_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".codex")
            do_install(home)
            text = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
            self.assertIn("[[hooks.PreToolUse]]", text)
            self.assertIn('matcher = "^(Bash|apply_patch)$"', text)
            self.assertIn(f"command = 'python3 \"{home / '.codex' / GUARD_REL}\"'", text)

    def test_cursor_registers_shell_read_and_write_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".cursor")
            do_install(home)
            config = read_json(home / ".cursor" / "hooks.json")
            self.assertEqual(config["version"], 1)
            command = f'python3 "{home / ".cursor" / GUARD_REL}" --format=cursor'
            self.assertEqual(config["hooks"]["beforeShellExecution"], [{"command": command}])
            self.assertEqual(config["hooks"]["beforeReadFile"], [{"command": command}])
            self.assertEqual(config["hooks"]["preToolUse"], [{"command": command, "matcher": "Write"}])

    def test_install_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", ".codex", ".cursor")
            do_install(home, with_verify=True)
            paths = [
                home / ".claude" / "settings.json",
                home / ".codex" / "config.toml",
                home / ".cursor" / "hooks.json",
            ]
            before = [p.read_bytes() for p in paths]
            rc, _ = do_install(home, with_verify=True)
            self.assertEqual(rc, 0)
            self.assertEqual(before, [p.read_bytes() for p in paths])

    def test_user_config_and_hooks_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", ".codex", ".cursor")
            user_hook = {"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]}
            (home / ".claude" / "settings.json").write_text(
                json.dumps({"model": "opus", "env": {"TOKEN": "x"}, "hooks": {"PreToolUse": [user_hook]}}),
                encoding="utf-8",
            )
            (home / ".codex" / "config.toml").write_text('model = "gpt"\n', encoding="utf-8")
            (home / ".cursor" / "hooks.json").write_text(
                json.dumps({"version": 1, "hooks": {"beforeShellExecution": [{"command": "mine.sh"}]}}),
                encoding="utf-8",
            )
            do_install(home)
            settings = read_json(home / ".claude" / "settings.json")
            self.assertEqual(settings["model"], "opus")
            self.assertEqual(settings["env"], {"TOKEN": "x"})
            self.assertEqual(settings["hooks"]["PreToolUse"][0], user_hook)
            self.assertEqual(len(settings["hooks"]["PreToolUse"]), 2)
            self.assertTrue((home / ".codex" / "config.toml").read_text(encoding="utf-8").startswith('model = "gpt"\n'))
            cursor = read_json(home / ".cursor" / "hooks.json")
            self.assertEqual(cursor["hooks"]["beforeShellExecution"][0], {"command": "mine.sh"})
            self.assertEqual(len(cursor["hooks"]["beforeShellExecution"]), 2)

    def test_existing_config_is_backed_up_before_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            (home / ".claude" / "settings.json").write_text('{"model": "opus"}', encoding="utf-8")
            do_install(home)
            backups = list((home / ".claude" / "backups").rglob("settings.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), '{"model": "opus"}')

    def test_invalid_json_config_left_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", ".cursor")
            (home / ".claude" / "settings.json").write_text("{broken", encoding="utf-8")
            (home / ".cursor" / "hooks.json").write_text("{broken", encoding="utf-8")
            rc, out = do_install(home)
            self.assertEqual(rc, 0)
            self.assertEqual((home / ".claude" / "settings.json").read_text(encoding="utf-8"), "{broken")
            self.assertEqual((home / ".cursor" / "hooks.json").read_text(encoding="utf-8"), "{broken")
            self.assertIn("skipping invalid settings.json", out)
            self.assertIn("skipping invalid hooks.json", out)

    def test_verify_hook_is_opt_in_and_claude_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", ".codex", ".cursor")
            do_install(home)
            self.assertNotIn("PostToolUse", read_json(home / ".claude" / "settings.json")["hooks"])
            self.assertFalse((home / ".claude" / VERIFY_REL).exists())

            do_install(home, with_verify=True)
            groups = read_json(home / ".claude" / "settings.json")["hooks"]["PostToolUse"]
            self.assertEqual(groups[0]["matcher"], "Edit|Write|MultiEdit")
            self.assertTrue((home / ".claude" / VERIFY_REL).exists())
            self.assertNotIn("verify", (home / ".codex" / "config.toml").read_text(encoding="utf-8"))
            self.assertNotIn("verify", (home / ".cursor" / "hooks.json").read_text(encoding="utf-8"))

    def test_installed_guard_script_blocks_and_allows(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            script = str(home / ".claude" / GUARD_REL)

            def call(command: str) -> subprocess.CompletedProcess:
                payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
                return subprocess.run(
                    [sys.executable, script], input=payload, capture_output=True, text=True, check=False
                )

            blocked = call("git push --force")
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("force", blocked.stderr)
            self.assertEqual(call("git status").returncode, 0)

    def test_installed_cursor_command_prints_permission_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".cursor")
            do_install(home)
            command = read_json(home / ".cursor" / "hooks.json")["hooks"]["beforeShellExecution"][0]["command"]
            for payload, expected in (
                ({"command": "git status", "cwd": "/w"}, ("allow", 0)),
                ({"command": "git push --force", "cwd": "/w"}, ("deny", 2)),
            ):
                result = subprocess.run(
                    command, shell=True, input=json.dumps(payload), capture_output=True, text=True, check=False
                )
                self.assertEqual((json.loads(result.stdout)["permission"], result.returncode), expected)

    def test_manifest_records_installed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", ".cursor")
            do_install(home)
            manifest = read_json(home / ".vibe-guardrails" / ".vibe-engineering-manifest.json")
            self.assertEqual(manifest["kit"], "guardrails")
            self.assertEqual(
                manifest["managed_files"],
                [f".claude/{GUARD_REL}", f".cursor/{GUARD_REL}"],
            )


class UninstallTests(unittest.TestCase):
    def test_uninstall_removes_scripts_and_only_our_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", ".codex", ".cursor")
            user_hook = {"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]}
            (home / ".claude" / "settings.json").write_text(
                json.dumps({"hooks": {"PreToolUse": [user_hook]}}), encoding="utf-8"
            )
            (home / ".codex" / "config.toml").write_text('model = "gpt"\n', encoding="utf-8")
            (home / ".cursor" / "hooks.json").write_text(
                json.dumps({"version": 1, "hooks": {"beforeShellExecution": [{"command": "mine.sh"}]}}),
                encoding="utf-8",
            )
            do_install(home, with_verify=True)

            rc, _ = run(uninstall, home=str(home), yes=True)

            self.assertEqual(rc, 0)
            for agent in (".claude", ".codex", ".cursor"):
                self.assertFalse((home / agent / GUARD_REL).exists())
            self.assertFalse((home / ".claude" / VERIFY_REL).exists())
            self.assertEqual(read_json(home / ".claude" / "settings.json"), {"hooks": {"PreToolUse": [user_hook]}})
            self.assertEqual((home / ".codex" / "config.toml").read_text(encoding="utf-8"), 'model = "gpt"\n')
            self.assertEqual(
                read_json(home / ".cursor" / "hooks.json"),
                {"version": 1, "hooks": {"beforeShellExecution": [{"command": "mine.sh"}]}},
            )
            self.assertFalse((home / ".vibe-guardrails" / ".vibe-engineering-manifest.json").exists())
            self.assertFalse((home / ".codex" / "hooks").exists())

    def test_uninstall_keeps_hooks_dir_used_by_other_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            other = home / ".claude" / "hooks" / "other.py"
            other.write_text("# not ours\n", encoding="utf-8")
            run(uninstall, home=str(home), yes=True)
            self.assertTrue(other.exists())
            self.assertFalse((home / ".claude" / "hooks" / "vibe-guardrails").exists())

    def test_uninstall_when_nothing_installed_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, out = run(uninstall, home=tmp, yes=True)
            self.assertEqual(rc, 0)
            self.assertIn("nothing to uninstall", out)

    def test_uninstall_dry_run_removes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            rc, _ = run(uninstall, home=str(home), dry_run=True, yes=True)
            self.assertEqual(rc, 0)
            self.assertTrue((home / ".claude" / GUARD_REL).exists())
            self.assertIn("hooks", read_json(home / ".claude" / "settings.json"))

    def test_modified_script_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            script = home / ".claude" / GUARD_REL
            script.write_text("# my edit\n", encoding="utf-8")
            _, out = run(uninstall, home=str(home), yes=True)
            self.assertTrue(script.exists())
            self.assertIn("kept modified file", out)

    def test_codex_block_edited_by_user_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".codex")
            do_install(home)
            config = home / ".codex" / "config.toml"
            edited = config.read_text(encoding="utf-8").replace("type = ", "timeout = 5\ntype = ")
            config.write_text(edited, encoding="utf-8")
            run(uninstall, home=str(home), yes=True)
            self.assertEqual(config.read_text(encoding="utf-8"), edited)


class DiffAndDoctorTests(unittest.TestCase):
    def test_diff_clean_after_install_and_reports_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            _, clean = run(diff_kit, home=str(home))
            self.assertIn("match kit templates", clean)
            (home / ".claude" / GUARD_REL).write_text("# edited\n", encoding="utf-8")
            _, changed = run(diff_kit, home=str(home))
            self.assertIn(GUARD_REL, changed)

    def test_doctor_reports_per_agent_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", ".codex")
            do_install(home)
            rc, out = run(doctor, home=str(home))
            self.assertEqual(rc, 0)
            self.assertIn("Claude Code: guard installed, hook registered", out)
            self.assertIn("Codex CLI: guard installed, hook registered", out)
            self.assertIn("Cursor: not present", out)

    def test_doctor_tells_codex_users_to_trust_the_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".codex")
            do_install(home)
            _, out = run(doctor, home=str(home))
            self.assertIn("/hooks", out)

    def test_doctor_omits_codex_trust_note_without_codex(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            _, out = run(doctor, home=str(home))
            self.assertNotIn("/hooks", out)

    def test_doctor_flags_unregistered_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            (home / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
            _, out = run(doctor, home=str(home))
            self.assertIn("Claude Code: guard installed, hook NOT registered", out)


if __name__ == "__main__":
    unittest.main()
