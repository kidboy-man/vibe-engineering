from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from typing import Mapping
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.cli import build_parser, main
from agents.kit_registry import KitSpec, KITS


class FakeKitModule:
    """Test-only fake kit demonstrating the installer interface contract."""

    @staticmethod
    def install(home: str | None = None, dry_run: bool = False, yes: bool = False, merge_settings: bool = True) -> int:
        return 0

    @staticmethod
    def diff_kit(home: str | None = None) -> int:
        return 0

    @staticmethod
    def doctor(home: str | None = None) -> int:
        return 0

    @staticmethod
    def uninstall(home: str | None = None, dry_run: bool = False, yes: bool = False) -> int:
        return 0


def _fake_kit_spec(name: str = "fake-kit") -> KitSpec:
    return KitSpec(
        name=name,
        help=f"Manage the {name} kit",
        install=FakeKitModule.install,
        diff=FakeKitModule.diff_kit,
        doctor=FakeKitModule.doctor,
        uninstall=FakeKitModule.uninstall,
    )


class ExtensionContractTests(unittest.TestCase):
    """Prove a new kit can be added without editing CLI dispatch code."""

    def _kits_help_text(self, parser) -> str:
        """Capture the help text for the 'kits' subcommand without exiting."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            with self.assertRaises(SystemExit) as cm:
                parser.parse_args(["kits", "--help"])
            self.assertEqual(cm.exception.code, 0)
            return mock_stdout.getvalue()

    def test_fake_kit_appears_in_parser_help(self) -> None:
        fake = _fake_kit_spec()
        injected: Mapping[str, KitSpec] = {**KITS, "fake-kit": fake}
        parser = build_parser(kit_specs=injected)
        help_text = self._kits_help_text(parser)
        self.assertIn("fake-kit", help_text)
        self.assertIn("Manage the fake-kit kit", help_text)

    def test_fake_kit_subcommands_appear(self) -> None:
        fake = _fake_kit_spec()
        injected: Mapping[str, KitSpec] = {**KITS, "fake-kit": fake}
        parser = build_parser(kit_specs=injected)
        for sub in ("install", "diff", "doctor", "uninstall"):
            with self.subTest(sub=sub):
                with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                    with self.assertRaises(SystemExit) as cm:
                        parser.parse_args(["kits", "fake-kit", sub, "--help"])
                    self.assertEqual(cm.exception.code, 0)
                    help_text = mock_stdout.getvalue()
                    self.assertIn(sub, help_text)

    def test_fake_kit_runnable_via_main(self) -> None:
        fake = _fake_kit_spec()
        injected: Mapping[str, KitSpec] = {**KITS, "fake-kit": fake}
        parser = build_parser(kit_specs=injected)
        with patch("agents.cli.build_parser", return_value=parser):
            with patch("agents.cli.KITS", injected):
                rc = main(["kits", "fake-kit", "doctor"])
        self.assertEqual(rc, 0)

    def test_no_cli_source_edit_required(self) -> None:
        """CLI source must not hard-code kit names; dispatch is registry-driven."""
        cli_source = Path(__file__).resolve().parent.parent / "agents" / "cli.py"
        source = cli_source.read_text(encoding="utf-8")
        self.assertNotIn("claude-code", source)
        self.assertNotIn("opencode", source)


if __name__ == "__main__":
    unittest.main()
