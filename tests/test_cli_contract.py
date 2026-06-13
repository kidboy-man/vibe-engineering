import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "cli_help"


class CliHelpContractTests(unittest.TestCase):
    """Characterization tests for CLI help output.

    These tests capture the current argparse-generated help text so that
    any future refactor (e.g. moving to click, restructuring subcommands)
    must intentionally change the user-facing help contract.
    """

    def _help_text(self, *args: str) -> str:
        result = subprocess.run(
            [sys.executable, "-m", "agents.cli", *args, "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, f"help failed: {result.stderr}")
        return result.stdout

    def _assert_matches_fixture(self, fixture_name: str, *args: str) -> None:
        expected = (FIXTURES_DIR / fixture_name).read_text(encoding="utf-8")
        actual = self._help_text(*args)
        self.assertEqual(
            actual,
            expected,
            f"Help output for '{' '.join(args)}' changed. "
            "If the change is intentional, update the fixture.",
        )

    def test_main_help(self):
        self._assert_matches_fixture("main_help.txt")

    def test_kits_help(self):
        self._assert_matches_fixture("kits_help.txt", "kits")

    def test_kits_claude_code_help(self):
        self._assert_matches_fixture("kits_claude_code_help.txt", "kits", "claude-code")

    def test_kits_opencode_help(self):
        self._assert_matches_fixture("kits_opencode_help.txt", "kits", "opencode")

    def test_kits_claude_code_install_help(self):
        self._assert_matches_fixture(
            "kits_claude_code_install_help.txt", "kits", "claude-code", "install"
        )

    def test_kits_claude_code_diff_help(self):
        self._assert_matches_fixture(
            "kits_claude_code_diff_help.txt", "kits", "claude-code", "diff"
        )

    def test_kits_claude_code_doctor_help(self):
        self._assert_matches_fixture(
            "kits_claude_code_doctor_help.txt", "kits", "claude-code", "doctor"
        )

    def test_kits_claude_code_uninstall_help(self):
        self._assert_matches_fixture(
            "kits_claude_code_uninstall_help.txt", "kits", "claude-code", "uninstall"
        )

    def test_kits_opencode_install_help(self):
        self._assert_matches_fixture(
            "kits_opencode_install_help.txt", "kits", "opencode", "install"
        )

    def test_kits_opencode_diff_help(self):
        self._assert_matches_fixture(
            "kits_opencode_diff_help.txt", "kits", "opencode", "diff"
        )

    def test_kits_opencode_doctor_help(self):
        self._assert_matches_fixture(
            "kits_opencode_doctor_help.txt", "kits", "opencode", "doctor"
        )

    def test_kits_opencode_uninstall_help(self):
        self._assert_matches_fixture(
            "kits_opencode_uninstall_help.txt", "kits", "opencode", "uninstall"
        )


class CliDispatchContractTests(unittest.TestCase):
    """Characterization tests for CLI argument dispatching.

    These tests verify that the CLI parser builds the correct namespace
    for the commands and flags we currently support.
    """

    def test_kits_list_prints_kit_names(self):
        result = subprocess.run(
            [sys.executable, "-m", "agents.cli", "kits", "list"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.strip().splitlines()
        self.assertIn("claude-code", lines)
        self.assertIn("opencode", lines)

    def test_kits_unknown_kit_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, "-m", "agents.cli", "kits", "no-such-kit"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
