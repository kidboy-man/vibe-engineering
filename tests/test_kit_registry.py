import io
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Mapping
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.cli import build_parser
from agents.kit_registry import KitSpec, KITS

CLI_SOURCE = Path(__file__).resolve().parent.parent / "agents" / "cli.py"
REGISTRY_SOURCE = Path(__file__).resolve().parent.parent / "agents" / "kit_registry.py"


class KitRegistryImportTests(unittest.TestCase):
    """Verify CLI depends on registry only, not concrete installers."""

    def test_cli_does_not_import_claude_code_installer(self):
        source = CLI_SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("agents.kits.claude_code.installer", source)

    def test_cli_does_not_import_opencode_installer(self):
        source = CLI_SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("agents.kits.opencode.installer", source)

    def test_registry_imports_claude_code_installer(self):
        source = REGISTRY_SOURCE.read_text(encoding="utf-8")
        self.assertIn("agents.kits.claude_code.installer", source)

    def test_registry_imports_opencode_installer(self):
        source = REGISTRY_SOURCE.read_text(encoding="utf-8")
        self.assertIn("agents.kits.opencode.installer", source)

    def test_registry_imports_second_brain_installer(self):
        source = REGISTRY_SOURCE.read_text(encoding="utf-8")
        self.assertIn("agents.kits.second_brain.installer", source)


class KitRegistryExtensionContractTests(unittest.TestCase):
    """Verify build_parser accepts injected registry and exposes new kits."""

    def _fake_kit(self, name: str) -> KitSpec:
        def _noop(**_kwargs):
            return 0
        return KitSpec(
            name=name,
            help=f"Manage the {name} kit",
            install=_noop,
            diff=_noop,
            doctor=_noop,
            uninstall=_noop,
        )

    def _kits_help_text(self, parser) -> str:
        """Capture the help text for the 'kits' subcommand without exiting."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            with self.assertRaises(SystemExit) as cm:
                parser.parse_args(["kits", "--help"])
            self.assertEqual(cm.exception.code, 0)
            return mock_stdout.getvalue()

    def test_build_parser_accepts_injected_registry(self):
        fake = self._fake_kit("fake-kit")
        injected: Mapping[str, KitSpec] = {**KITS, "fake-kit": fake}
        parser = build_parser(kit_specs=injected)
        help_text = self._kits_help_text(parser)
        self.assertIn("fake-kit", help_text)
        # Ensure original kits are still present
        self.assertIn("claude-code", help_text)
        self.assertIn("opencode", help_text)

    def test_build_parser_default_unchanged(self):
        parser = build_parser()
        help_text = self._kits_help_text(parser)
        self.assertIn("claude-code", help_text)
        self.assertIn("opencode", help_text)
        self.assertNotIn("fake-kit", help_text)


class KitRegistrySmokeTests(unittest.TestCase):
    """Basic smoke tests for the registry module."""

    def test_kits_has_expected_keys(self):
        self.assertIn("claude-code", KITS)
        self.assertIn("opencode", KITS)
        self.assertIn("second-brain", KITS)

    def test_kitspec_attributes(self):
        kit = KITS["claude-code"]
        self.assertEqual(kit.name, "claude-code")
        self.assertTrue(callable(kit.install))
        self.assertTrue(callable(kit.diff))
        self.assertTrue(callable(kit.doctor))
        self.assertTrue(callable(kit.uninstall))

    def test_second_brain_kitspec_attributes(self):
        kit = KITS["second-brain"]
        self.assertEqual(kit.name, "second-brain")
        self.assertTrue(callable(kit.install))
        self.assertTrue(callable(kit.diff))
        self.assertTrue(callable(kit.doctor))
        self.assertTrue(callable(kit.uninstall))


if __name__ == "__main__":
    unittest.main()
