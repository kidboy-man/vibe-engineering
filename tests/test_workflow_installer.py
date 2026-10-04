import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.kits.workflow.installer import _paths, diff_kit, doctor, install, uninstall

FILES = [
    "commands/flow.md",
    "commands/implement-ticket.md",
    "commands/prd.md",
    "commands/push-tickets.md",
    "skills/vibe-flow/SKILL.md",
    "skills/vibe-flow/scripts/check_trace.py",
]
SCRIPT_REL = "skills/vibe-flow/scripts/check_trace.py"
TARGETS = {"claude": ".claude", "opencode": "opencode"}


def make_home(tmp: str, *dirs: str) -> Path:
    home = Path(tmp)
    for name in dirs:
        (home / name).mkdir(parents=True)
    return home


def run(fn, **kwargs) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        rc = fn(**kwargs)
    return rc, out.getvalue()


def do_install(home: Path, **kwargs) -> tuple[int, str]:
    return run(install, home=str(home), yes=True, **kwargs)


class InstallTests(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", "opencode")
            rc, out = run(install, home=str(home), dry_run=True, yes=True)
            self.assertEqual(rc, 0)
            self.assertIn("create commands/prd.md", out)
            self.assertEqual(list((home / ".claude").iterdir()), [])
            self.assertEqual(list((home / "opencode").iterdir()), [])
            self.assertFalse((home / ".vibe-workflow").exists())

    def test_no_agent_dirs_installs_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, out = do_install(Path(tmp))
            self.assertEqual(rc, 1)
            self.assertIn("no supported agent", out)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_installs_all_files_only_into_existing_agent_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            rc, out = do_install(home)
            self.assertEqual(rc, 0)
            for rel in FILES:
                self.assertTrue((home / ".claude" / rel).is_file(), rel)
            self.assertFalse((home / "opencode").exists())
            self.assertIn("skipping OpenCode", out)

    def test_each_target_gets_its_own_variant(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", "opencode")
            do_install(home)
            claude = (home / ".claude" / "commands" / "prd.md").read_text(encoding="utf-8")
            opencode = (home / "opencode" / "commands" / "prd.md").read_text(encoding="utf-8")
            self.assertIn("AskUserQuestion", claude)
            self.assertNotIn("AskUserQuestion", opencode)
            self.assertIn("~/.claude/skills/vibe-flow", (home / ".claude" / "commands" / "implement-ticket.md").read_text(encoding="utf-8"))
            self.assertIn("${XDG_CONFIG_HOME:-$HOME/.config}/opencode/skills/vibe-flow", (home / "opencode" / "commands" / "implement-ticket.md").read_text(encoding="utf-8"))

    def test_shared_script_is_identical_across_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", "opencode")
            do_install(home)
            self.assertEqual(
                (home / ".claude" / SCRIPT_REL).read_bytes(),
                (home / "opencode" / SCRIPT_REL).read_bytes(),
            )

    def test_install_is_idempotent_and_makes_no_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", "opencode")
            do_install(home)
            def snapshot() -> dict[Path, bytes]:
                return {p: p.read_bytes() for d in (".claude", "opencode") for p in (home / d).rglob("*") if p.is_file()}

            before = snapshot()
            rc, _ = do_install(home)
            self.assertEqual(rc, 0)
            self.assertEqual(before, snapshot())
            self.assertFalse(list(home.rglob("backups")))

    def test_locally_edited_file_is_backed_up_then_refreshed(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            target = home / ".claude" / "commands" / "prd.md"
            target.write_text("# my edit\n", encoding="utf-8")
            do_install(home)
            backups = list((home / ".claude" / "backups").rglob("prd.md"))
            self.assertEqual([b.read_text(encoding="utf-8") for b in backups], ["# my edit\n"])
            self.assertNotEqual(target.read_text(encoding="utf-8"), "# my edit\n")

    def test_unrelated_user_files_are_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude/commands", ".claude/skills/other")
            mine = home / ".claude" / "commands" / "mine.md"
            mine.write_text("mine\n", encoding="utf-8")
            other = home / ".claude" / "skills" / "other" / "SKILL.md"
            other.write_text("other\n", encoding="utf-8")
            do_install(home)
            run(uninstall, home=str(home), yes=True)
            self.assertEqual(mine.read_text(encoding="utf-8"), "mine\n")
            self.assertEqual(other.read_text(encoding="utf-8"), "other\n")

    def test_manifest_records_target_and_relative_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", "opencode")
            do_install(home)
            manifest = json.loads(
                (home / ".vibe-workflow" / ".vibe-engineering-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["kit"], "workflow")
            self.assertEqual(
                manifest["managed_files"],
                sorted([f"claude/{r}" for r in FILES] + [f"opencode/{r}" for r in FILES]),
            )

    def test_installed_script_runs_from_the_installed_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            tickets = home / "tickets"
            tickets.mkdir()
            (tickets / "issue-01.md").write_text("---\nid: T-01\nstatus: todo\n---\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(home / ".claude" / SCRIPT_REL), "--tickets", str(tickets), "--next"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual((result.returncode, result.stdout.strip()), (0, "T-01"))


class PathsTests(unittest.TestCase):
    def test_opencode_dir_follows_xdg_when_no_home_given(self):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/fake-xdg"}):
            paths = _paths(None)
        self.assertEqual(paths.agent_dirs["opencode"], Path("/tmp/fake-xdg/opencode"))
        self.assertEqual(paths.agent_dirs["claude"], Path.home() / ".claude")

    def test_home_override_uses_claude_dot_dir_and_opencode_dir(self):
        paths = _paths("/tmp/h")
        self.assertEqual(paths.agent_dirs["claude"], Path("/tmp/h/.claude"))
        self.assertEqual(paths.agent_dirs["opencode"], Path("/tmp/h/opencode"))


class UninstallTests(unittest.TestCase):
    def test_uninstall_removes_files_manifest_and_empty_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude", "opencode")
            do_install(home)
            rc, _ = run(uninstall, home=str(home), yes=True)
            self.assertEqual(rc, 0)
            for target in TARGETS.values():
                for rel in FILES:
                    self.assertFalse((home / target / rel).exists(), rel)
                self.assertFalse((home / target / "skills" / "vibe-flow").exists())
            self.assertFalse((home / ".vibe-workflow").exists())

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
            self.assertTrue((home / ".claude" / "commands" / "prd.md").exists())

    def test_modified_file_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            target = home / ".claude" / "commands" / "prd.md"
            target.write_text("# edited\n", encoding="utf-8")
            _, out = run(uninstall, home=str(home), yes=True)
            self.assertTrue(target.exists())
            self.assertIn("kept modified file", out)
            self.assertFalse((home / ".claude" / "commands" / "flow.md").exists())


class DiffAndDoctorTests(unittest.TestCase):
    def test_diff_clean_then_reports_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            _, clean = run(diff_kit, home=str(home))
            self.assertIn("match kit templates", clean)
            (home / ".claude" / "commands" / "flow.md").write_text("# edited\n", encoding="utf-8")
            _, changed = run(diff_kit, home=str(home))
            self.assertIn("commands/flow.md", changed)

    def test_doctor_reports_install_state_per_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            rc, out = run(doctor, home=str(home))
            self.assertEqual(rc, 0)
            self.assertIn("Claude Code: 6/6 files installed", out)
            self.assertIn("OpenCode: not present", out)

    def test_doctor_warns_when_upstream_stages_are_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            _, out = run(doctor, home=str(home))
            self.assertIn("/trd command not found", out)
            self.assertIn("vibe-engineering skill not found", out)

    def test_doctor_is_quiet_when_upstream_stages_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude/commands", ".claude/skills/vibe-engineering")
            (home / ".claude" / "commands" / "trd.md").write_text("x", encoding="utf-8")
            (home / ".claude" / "skills" / "vibe-engineering" / "SKILL.md").write_text("x", encoding="utf-8")
            do_install(home)
            _, out = run(doctor, home=str(home))
            self.assertNotIn("not found", out)

    def test_doctor_reports_partial_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp, ".claude")
            do_install(home)
            (home / ".claude" / "commands" / "prd.md").unlink()
            _, out = run(doctor, home=str(home))
            self.assertIn("5/6 files installed", out)


if __name__ == "__main__":
    unittest.main()
