import io
import json
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import installer_core as core


def _run(fn, *args, **kwargs):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = fn(*args, **kwargs)
    return rc, buf.getvalue()


class ConfirmAndHomeTests(unittest.TestCase):
    def test_confirm_returns_false_on_eof(self):
        with mock.patch("builtins.input", side_effect=EOFError):
            self.assertFalse(core.confirm("go?", yes=False))

    def test_confirm_accepts_yes_answers(self):
        with mock.patch("builtins.input", return_value=" Y "):
            self.assertTrue(core.confirm("go?", yes=False))

    def test_resolve_home_expands_user_and_defaults_to_home(self):
        self.assertEqual(core.resolve_home("/tmp/x"), Path("/tmp/x"))
        self.assertEqual(core.resolve_home(None), Path.home())


class PruneEmptyDirsTests(unittest.TestCase):
    def test_removes_empty_chain_and_stops_at_non_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            outer = Path(tmp) / "a"
            inner = outer / "b"
            inner.mkdir(parents=True)
            core.prune_empty_dirs(inner, outer)
            self.assertFalse(outer.exists())

            inner.mkdir(parents=True)
            (inner / "keep.txt").write_text("x", encoding="utf-8")
            core.prune_empty_dirs(inner, outer)
            self.assertTrue(inner.exists())

    def test_missing_dir_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            core.prune_empty_dirs(Path(tmp) / "nope")


class ReportBinaryTests(unittest.TestCase):
    def test_missing_binary_prints_message_and_fails(self):
        with mock.patch("agents.installer_core.shutil.which", return_value=None):
            ok, out = _run(core.report_binary, "tool", "tool: missing (hint)")
        self.assertFalse(ok)
        self.assertEqual(out, "tool: missing (hint)\n")

    def test_present_binary_prints_path_and_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "tool"
            script.write_text("#!/bin/sh\necho v1.2.3\n", encoding="utf-8")
            script.chmod(script.stat().st_mode | stat.S_IXUSR)
            with mock.patch("agents.installer_core.shutil.which", return_value=str(script)):
                ok, out = _run(core.report_binary, "tool", "unused")
        self.assertTrue(ok)
        self.assertEqual(out, f"tool: {script}\ntool version: v1.2.3\n")

    def test_version_check_failure_reports_not_ok(self):
        with mock.patch("agents.installer_core.shutil.which", return_value="/bin/tool"), mock.patch(
            "agents.installer_core.subprocess.run", side_effect=OSError("boom")
        ):
            ok, out = _run(core.report_binary, "tool", "unused")
        self.assertFalse(ok)
        self.assertIn("tool version check failed: boom", out)


class CopyKitRunnerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.templates = root / "templates"
        self.templates.mkdir()
        (self.templates / "AGENTS.md").write_text("persona\n", encoding="utf-8")
        (self.templates / "manifest.json").write_text(
            json.dumps({"kit": "demo", "managed_files": ["AGENTS.md"]}), encoding="utf-8"
        )
        self.home = root / "home"
        self.kit = core.CopyKit(
            kit_name="demo",
            label="Demo CLI",
            template_dir=self.templates,
            target_subdir=".demo",
            binary="demo",
            missing_binary_message="demo: not found",
        )
        self.target = self.home / ".demo"

    def test_dry_run_install_writes_nothing(self):
        rc, out = _run(core.copy_kit_install, self.kit, home=str(self.home), dry_run=True)
        self.assertEqual(rc, 0)
        self.assertEqual(
            out.splitlines(),
            ["create AGENTS.md", f"write {core.MANIFEST_FILE}", "dry run: no files written"],
        )
        self.assertFalse(self.home.exists())

    def test_install_then_uninstall_roundtrip(self):
        rc, out = _run(core.copy_kit_install, self.kit, home=str(self.home), yes=True)
        self.assertEqual(rc, 0)
        self.assertIn("installed AGENTS.md", out)
        self.assertEqual((self.target / "AGENTS.md").read_text(encoding="utf-8"), "persona\n")
        manifest = json.loads((self.target / core.MANIFEST_FILE).read_text(encoding="utf-8"))
        self.assertEqual(manifest["kit"], "demo")
        self.assertEqual(manifest["managed_files"], ["AGENTS.md"])

        rc, out = _run(core.copy_kit_uninstall, self.kit, home=str(self.home), yes=True)
        self.assertEqual(rc, 0)
        self.assertIn("removed AGENTS.md", out)
        self.assertFalse((self.target / "AGENTS.md").exists())
        self.assertFalse((self.target / core.MANIFEST_FILE).exists())

    def test_uninstall_keeps_modified_files(self):
        _run(core.copy_kit_install, self.kit, home=str(self.home), yes=True)
        (self.target / "AGENTS.md").write_text("mine\n", encoding="utf-8")
        _rc, out = _run(core.copy_kit_uninstall, self.kit, home=str(self.home), yes=True)
        self.assertIn("kept modified file AGENTS.md", out)
        self.assertEqual((self.target / "AGENTS.md").read_text(encoding="utf-8"), "mine\n")

    def test_abort_without_consent(self):
        with mock.patch("builtins.input", return_value="n"):
            rc, out = _run(core.copy_kit_install, self.kit, home=str(self.home))
        self.assertEqual(rc, 1)
        self.assertTrue(out.endswith("aborted\n"))
        self.assertFalse(self.home.exists())

    def test_diff_reports_match_and_difference(self):
        _run(core.copy_kit_install, self.kit, home=str(self.home), yes=True)
        _rc, out = _run(core.copy_kit_diff, self.kit, home=str(self.home))
        self.assertEqual(out, "managed files match kit templates\n")
        (self.target / "AGENTS.md").write_text("changed\n", encoding="utf-8")
        _rc, out = _run(core.copy_kit_diff, self.kit, home=str(self.home))
        self.assertIn("--- AGENTS.md (installed)", out)

    def test_uninstall_without_manifest_is_noop(self):
        rc, out = _run(core.copy_kit_uninstall, self.kit, home=str(self.home), yes=True)
        self.assertEqual(rc, 0)
        self.assertEqual(out, f"no {core.MANIFEST_FILE} found; nothing to uninstall\n")

    def test_doctor_fails_when_binary_missing_unless_optional(self):
        with mock.patch("agents.installer_core.shutil.which", return_value=None):
            rc, out = _run(core.copy_kit_doctor, self.kit, home=str(self.home))
            self.assertEqual(rc, 1)
            self.assertIn("demo dir: ", out)
            self.assertIn("manifest: not installed", out)
            self.assertIn("templates: ok", out)
            optional = core.CopyKit(**{**self.kit.__dict__, "missing_binary_is_failure": False})
            rc, _out = _run(core.copy_kit_doctor, optional, home=str(self.home))
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
