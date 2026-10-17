import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.kits.guardrails import installer as guardrails
from agents.kits.wikify import installer as wikify
from agents.kits.wikify.installer import diff_kit, doctor, install, uninstall

REL = "hooks/vibe-wikify/wikify_guard.py"
GUARD_REL = "hooks/vibe-guardrails/guard.py"
SKILL_REL = "skills/wikify-adopt/SKILL.md"
SYNC_REL = "skills/wikify-sync/SKILL.md"


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
            for agent in (".claude", ".codex", ".cursor"):
                self.assertEqual(list((home / agent).iterdir()), [])
            self.assertFalse((home / ".vibe-wikify").exists())

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
            self.assertTrue((home / ".claude" / REL).exists())
            self.assertFalse((home / ".claude" / "hooks" / "vibe-wikify" / "WIKIFY.md").exists())
            self.assertFalse((home / ".codex").exists())
            self.assertFalse((home / ".cursor").exists())
            self.assertIn("skipping Codex CLI", out)

    def test_claude_registers_pretooluse_bash(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            groups = read_json(home / ".claude" / "settings.json")["hooks"]["PreToolUse"]
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["matcher"], "Bash")
            self.assertEqual(groups[0]["hooks"][0]["command"], f'python3 "{home / ".claude" / REL}"')

    def test_codex_registers_pretooluse_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".codex")
            do_install(home)
            text = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
            self.assertIn("[[hooks.PreToolUse]]", text)
            self.assertIn('matcher = "^Bash$"', text)
            self.assertIn(f"command = 'python3 \"{home / '.codex' / REL}\"'", text)

    def test_cursor_registers_before_shell_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".cursor")
            do_install(home)
            config = read_json(home / ".cursor" / "hooks.json")
            command = f'python3 "{home / ".cursor" / REL}" --format=cursor'
            self.assertEqual(config["hooks"], {"beforeShellExecution": [{"command": command}]})

    def test_install_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", ".codex", ".cursor")
            do_install(home)
            paths = [
                home / ".claude" / "settings.json",
                home / ".codex" / "config.toml",
                home / ".cursor" / "hooks.json",
            ]
            before = [p.read_bytes() for p in paths]
            rc, out = do_install(home)
            self.assertEqual(rc, 0)
            self.assertEqual(before, [p.read_bytes() for p in paths])
            self.assertNotIn("registered", out)
            self.assertNotIn("installed .", out)

    def test_user_config_and_hooks_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", ".codex", ".cursor")
            user_hook = {"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]}
            (home / ".claude" / "settings.json").write_text(
                json.dumps({"model": "opus", "hooks": {"PreToolUse": [user_hook]}}), encoding="utf-8"
            )
            (home / ".codex" / "config.toml").write_text('model = "gpt"\n', encoding="utf-8")
            (home / ".cursor" / "hooks.json").write_text(
                json.dumps({"version": 1, "hooks": {"beforeShellExecution": [{"command": "mine.sh"}]}}),
                encoding="utf-8",
            )
            do_install(home)
            settings = read_json(home / ".claude" / "settings.json")
            self.assertEqual(settings["model"], "opus")
            self.assertEqual(settings["hooks"]["PreToolUse"][0], user_hook)
            self.assertEqual(len(settings["hooks"]["PreToolUse"]), 2)
            self.assertTrue((home / ".codex" / "config.toml").read_text(encoding="utf-8").startswith('model = "gpt"\n'))
            cursor = read_json(home / ".cursor" / "hooks.json")
            self.assertEqual(cursor["hooks"]["beforeShellExecution"][0], {"command": "mine.sh"})
            self.assertEqual(len(cursor["hooks"]["beforeShellExecution"]), 2)

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

    def test_manifest_records_installed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", ".cursor")
            do_install(home)
            manifest = read_json(home / ".vibe-wikify" / ".vibe-engineering-manifest.json")
            self.assertEqual(manifest["kit"], "wikify")
            self.assertEqual(
                manifest["managed_files"],
                [f".claude/{REL}", f".claude/{SKILL_REL}", f".claude/{SYNC_REL}", f".cursor/{REL}"],
            )


class UninstallTests(unittest.TestCase):
    def test_uninstall_keeps_scripts_and_manifest_when_unregister_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", ".codex")
            do_install(home)
            (home / ".claude" / "settings.json").write_text("{broken", encoding="utf-8")
            (home / ".codex" / "config.toml").write_text("# hand edited\n", encoding="utf-8")
            rc, out = run(uninstall, home=str(home), yes=True)
            self.assertNotEqual(rc, 0)
            self.assertTrue((home / ".claude" / REL).exists())
            self.assertTrue((home / ".vibe-wikify" / ".vibe-engineering-manifest.json").exists())
            self.assertIn("hook not removed", out)

    def test_uninstall_keeps_scripts_when_codex_block_was_edited(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".codex")
            do_install(home)
            cfg = home / ".codex" / "config.toml"
            cfg.write_text(cfg.read_text(encoding="utf-8").replace("PreToolUse", "PreToolUse # edited", 1), encoding="utf-8")
            rc, _ = run(uninstall, home=str(home), yes=True)
            self.assertNotEqual(rc, 0)
            self.assertTrue((home / ".codex" / REL).exists())

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
            do_install(home)
            rc, _ = run(uninstall, home=str(home), yes=True)
            self.assertEqual(rc, 0)
            for agent in (".claude", ".codex", ".cursor"):
                self.assertFalse((home / agent / REL).exists())
                self.assertFalse((home / agent / "hooks").exists())
            self.assertEqual(read_json(home / ".claude" / "settings.json"), {"hooks": {"PreToolUse": [user_hook]}})
            self.assertEqual((home / ".codex" / "config.toml").read_text(encoding="utf-8"), 'model = "gpt"\n')
            self.assertEqual(
                read_json(home / ".cursor" / "hooks.json"),
                {"version": 1, "hooks": {"beforeShellExecution": [{"command": "mine.sh"}]}},
            )
            self.assertFalse((home / ".vibe-wikify").exists())

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
            self.assertTrue((home / ".claude" / REL).exists())
            self.assertIn("hooks", read_json(home / ".claude" / "settings.json"))

    def test_modified_script_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            script = home / ".claude" / REL
            script.write_text("# my edit\n", encoding="utf-8")
            _, out = run(uninstall, home=str(home), yes=True)
            self.assertTrue(script.exists())
            self.assertIn("kept modified file", out)


class DiffAndDoctorTests(unittest.TestCase):
    def test_diff_clean_after_install_and_reports_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            _, clean = run(diff_kit, home=str(home))
            self.assertIn("match kit templates", clean)
            (home / ".claude" / REL).write_text("# edited\n", encoding="utf-8")
            _, changed = run(diff_kit, home=str(home))
            self.assertIn(REL, changed)

    def test_doctor_reports_status_and_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", ".codex")
            do_install(home)
            with mock.patch.object(wikify.shutil, "which", return_value=None):
                rc, out = run(doctor, home=str(home))
            self.assertEqual(rc, 0)
            self.assertIn("Claude Code: hook installed, registered", out)
            self.assertIn("Codex CLI: hook installed, registered", out)
            self.assertIn("Cursor: not present", out)
            self.assertIn("manifest: installed", out)
            self.assertIn("templates: ok", out)
            self.assertIn("/hooks", out)
            self.assertIn("convenience gate, not a security control", out)
            self.assertIn("VIBE_WIKIFY=off", out)
            self.assertIn("scan: no external scanner on PATH", out)

    def test_doctor_reports_scanner_on_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            with mock.patch.object(wikify.shutil, "which", side_effect=lambda n: "/x/trufflehog" if n == "trufflehog" else None):
                _, out = run(doctor, home=str(home))
            self.assertIn("scan: trufflehog found on PATH (informational; wikify's built-in scan is a floor, not a complete scanner)", out)
            self.assertNotIn("/hooks", out)

    def test_doctor_flags_unregistered_hook_and_missing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            (home / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
            _, out = run(doctor, home=str(home))
            self.assertIn("Claude Code: hook installed, NOT registered", out)
            _, out = run(doctor, home=tempfile.mkdtemp())
            self.assertIn("manifest: not installed", out)


class CoexistenceTests(unittest.TestCase):
    def test_guardrails_and_wikify_coexist(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            run(guardrails.install, home=str(home), yes=True)
            do_install(home)
            commands = lambda: [
                h["command"]
                for g in read_json(home / ".claude" / "settings.json")["hooks"]["PreToolUse"]
                for h in g["hooks"]
            ]
            self.assertEqual(len(commands()), 2)
            self.assertTrue(any("vibe-guardrails" in c for c in commands()))
            self.assertTrue(any("vibe-wikify" in c for c in commands()))

            run(uninstall, home=str(home), yes=True)
            self.assertEqual(len(commands()), 1)
            self.assertIn("vibe-guardrails", commands()[0])
            self.assertTrue((home / ".claude" / GUARD_REL).exists())
            self.assertFalse((home / ".claude" / REL).exists())

            do_install(home)
            run(guardrails.uninstall, home=str(home), yes=True)
            self.assertEqual(len(commands()), 1)
            self.assertIn("vibe-wikify", commands()[0])
            self.assertTrue((home / ".claude" / REL).exists())



class SyncSkillTests(unittest.TestCase):
    TEMPLATE = Path(wikify.__file__).resolve().parent / "templates" / "wikify" / SYNC_REL

    def test_sync_skill_is_a_managed_template(self):
        manifest = read_json(self.TEMPLATE.parents[2] / "manifest.json")
        self.assertIn(SYNC_REL, manifest["managed_files"])
        self.assertTrue(self.TEMPLATE.read_text(encoding="utf-8").startswith("---\nname: wikify-sync\n"))

    def test_install_is_idempotent_and_backs_up_a_changed_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            skill = home / ".claude" / SYNC_REL
            self.assertEqual(skill.read_text(), self.TEMPLATE.read_text())
            self.assertNotIn("installed .claude/" + SYNC_REL, do_install(home)[1])
            skill.write_text("edited")
            do_install(home)
            self.assertEqual(skill.read_text(), self.TEMPLATE.read_text())
            backups = [p for p in (home / ".claude").rglob("*") if p.is_file() and "edited" in p.read_text()]
            self.assertTrue(backups)

    def test_cursor_and_codex_get_no_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", ".cursor", ".codex")
            do_install(home)
            self.assertFalse((home / ".cursor" / "skills").exists())
            self.assertFalse((home / ".codex" / "skills").exists())

    def test_uninstall_removes_both_unmodified_skills_but_keeps_an_edited_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            run(uninstall, home=str(home), yes=True)
            self.assertFalse((home / ".claude" / "skills" / "wikify-adopt").exists())
            self.assertFalse((home / ".claude" / "skills" / "wikify-sync").exists())
            do_install(home)
            (home / ".claude" / SYNC_REL).write_text("edited")
            run(uninstall, home=str(home), yes=True)
            self.assertEqual((home / ".claude" / SYNC_REL).read_text(), "edited")
            self.assertFalse((home / ".claude" / SKILL_REL).exists())

    def test_doctor_and_diff_cover_the_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            self.assertIn("templates: ok", run(doctor, home=str(home))[1])
            (home / ".claude" / SYNC_REL).write_text("edited")
            self.assertIn("skills/wikify-sync/SKILL.md", run(diff_kit, home=str(home))[1])

    def test_dry_run_lists_both_skills_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            rc, out = run(install, home=str(home), dry_run=True, yes=True)
            self.assertIn(f"install .claude/{SYNC_REL}", out)
            self.assertEqual(list((home / ".claude").iterdir()), [])

    def test_skill_text_names_only_real_commands_and_keeps_its_guardrails(self):
        import re
        text = self.TEMPLATE.read_text(encoding="utf-8")
        for bad in ("/home/", "/Users/", "C:\\", "token", "password", "api_key", "api-key"):
            self.assertNotIn(bad, text)
        real = {"init", "plan", "verify", "mark", "link", "docs", "adopt", "check", "reanchor",
                "sync", "install-hook", "migrate-imported", "fix-links"}
        used = set(re.findall(r"vibe wikify ([a-z-]+)", text))
        self.assertTrue(used)
        self.assertLessEqual(used, real)
        for sentence in (
            "never invent facts", "contradiction", "untrusted", "wikify:human",
            "wikify:generated", ".wikifyignore", ".wikify-allow", "never deleted", "Never push",
        ):
            self.assertIn(sentence.lower(), text.lower())


class SkillTests(unittest.TestCase):
    TEMPLATE = Path(wikify.__file__).resolve().parent / "templates" / "wikify" / SKILL_REL

    def test_skill_is_a_managed_template(self):
        manifest = read_json(self.TEMPLATE.parents[2] / "manifest.json")
        self.assertIn(SKILL_REL, manifest["managed_files"])
        self.assertTrue(self.TEMPLATE.is_file())

    def test_install_puts_the_skill_only_in_agents_that_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", ".cursor")
            rc, out = do_install(home)
            self.assertEqual(rc, 0)
            self.assertTrue((home / ".claude" / SKILL_REL).is_file())
            self.assertFalse((home / ".cursor" / "skills").exists())
            self.assertIn(f".claude/{SKILL_REL}", read_json(home / ".vibe-wikify" / wikify.MANIFEST_FILE)["managed_files"])

    def test_dry_run_lists_the_skill_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            rc, out = run(install, home=str(home), dry_run=True, yes=True)
            self.assertIn(f"install .claude/{SKILL_REL}", out)
            self.assertEqual(list((home / ".claude").iterdir()), [])

    def test_uninstall_removes_the_skill_but_keeps_modified_or_foreign_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            other = home / ".claude" / "skills" / "mine" / "SKILL.md"
            other.parent.mkdir(parents=True)
            other.write_text("mine")
            do_install(home)
            rc, out = run(uninstall, home=str(home), yes=True)
            self.assertEqual(rc, 0)
            self.assertFalse((home / ".claude" / "skills" / "wikify-adopt").exists())
            self.assertEqual(other.read_text(), "mine")
            do_install(home)
            skill = home / ".claude" / SKILL_REL
            skill.write_text("edited")
            run(uninstall, home=str(home), yes=True)
            self.assertEqual(skill.read_text(), "edited")

    def test_diff_reports_a_changed_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            (home / ".claude" / SKILL_REL).write_text("edited")
            rc, out = run(diff_kit, home=str(home))
            self.assertIn("skills/wikify-adopt/SKILL.md", out)

    def test_skill_text_is_portable_and_only_names_real_commands(self):
        text = self.TEMPLATE.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: wikify-adopt\n"))
        for bad in ("/home/", "/Users/", "C:\\", "token", "password", "api_key", "api-key"):
            self.assertNotIn(bad, text)
        import re
        real = {"init", "plan", "verify", "mark", "link", "docs", "adopt"}
        used = set(re.findall(r"vibe wikify ([a-z]+)", text))
        self.assertTrue(used)
        self.assertLessEqual(used, real)
        for sentence in (
            "never rewrite migrated prose",
            "never invent facts",
            "contradiction",
            "untrusted",
            "one bounded context",
        ):
            self.assertIn(sentence, text.lower(), sentence)


if __name__ == "__main__":
    unittest.main()
