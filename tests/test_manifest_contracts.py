from __future__ import annotations

import json
import tomllib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.kits.claude_code import installer as claude_installer
from agents.kits.opencode import installer as opencode_installer


ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"


class PackageDataGlobTests(unittest.TestCase):
    def test_package_data_globs_are_symmetric(self) -> None:
        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        globs = data["tool"]["setuptools"]["package-data"]["agents"]
        self.assertEqual(
            globs,
            [
                "kits/claude_code/templates/**/*",
                "kits/claude_code/templates/**/**/*",
                "kits/opencode/templates/**/*",
                "kits/opencode/templates/**/**/*",
            ],
        )


class ManifestSurfaceTests(unittest.TestCase):
    def _assert_manifest_surface(self, installer_module, kit_name: str) -> None:
        template_dir = installer_module._template_dir()
        manifest = json.loads((template_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["kit"], kit_name)
        for rel in manifest["managed_files"]:
            with self.subTest(kit=kit_name, rel=rel):
                path = template_dir / rel
                self.assertTrue(path.exists(), f"missing managed file: {path}")
                self.assertTrue(
                    path.resolve().is_relative_to(template_dir.resolve()),
                    f"managed file escapes template root: {path}",
                )

    def test_claude_manifest_surface(self) -> None:
        self._assert_manifest_surface(claude_installer, "claude-code")

    def test_opencode_manifest_surface(self) -> None:
        self._assert_manifest_surface(opencode_installer, "opencode")


class ManifestParityTests(unittest.TestCase):
    """Verify each real kit manifest includes the expected file categories."""

    def _load_manifest(self, installer_module) -> dict:
        template_dir = installer_module._template_dir()
        return json.loads((template_dir / "manifest.json").read_text(encoding="utf-8"))

    def _managed_files(self, installer_module) -> set[str]:
        return set(self._load_manifest(installer_module)["managed_files"])

    def test_claude_has_persona_root_file(self) -> None:
        files = self._managed_files(claude_installer)
        self.assertIn("CLAUDE.md", files)

    def test_opencode_has_persona_root_file(self) -> None:
        files = self._managed_files(opencode_installer)
        self.assertIn("AGENTS.md", files)

    def test_claude_has_rules_files(self) -> None:
        files = self._managed_files(claude_installer)
        rules = {f for f in files if f.startswith("rules/")}
        self.assertTrue(rules, "claude manifest missing rules files")

    def test_opencode_has_rules_files(self) -> None:
        files = self._managed_files(opencode_installer)
        rules = {f for f in files if f.startswith("rules/")}
        self.assertTrue(rules, "opencode manifest missing rules files")

    def test_claude_has_agents_files(self) -> None:
        files = self._managed_files(claude_installer)
        agents = {f for f in files if f.startswith("agents/")}
        self.assertTrue(agents, "claude manifest missing agents files")

    def test_opencode_has_agents_files(self) -> None:
        files = self._managed_files(opencode_installer)
        agents = {f for f in files if f.startswith("agents/")}
        self.assertTrue(agents, "opencode manifest missing agents files")

    def test_claude_has_commands_files(self) -> None:
        files = self._managed_files(claude_installer)
        commands = {f for f in files if f.startswith("commands/")}
        self.assertTrue(commands, "claude manifest missing commands files")

    def test_opencode_has_commands_files(self) -> None:
        files = self._managed_files(opencode_installer)
        commands = {f for f in files if f.startswith("commands/")}
        self.assertTrue(commands, "opencode manifest missing commands files")

    def test_claude_has_vibe_engineering_skill(self) -> None:
        files = self._managed_files(claude_installer)
        self.assertIn("skills/vibe-engineering/SKILL.md", files)

    def test_opencode_has_vibe_engineering_skill(self) -> None:
        files = self._managed_files(opencode_installer)
        self.assertIn("skills/vibe-engineering/SKILL.md", files)

    def test_claude_has_settings_fragment(self) -> None:
        manifest = self._load_manifest(claude_installer)
        self.assertIn("settings_fragment", manifest)
        self.assertTrue(manifest["settings_fragment"])

    def test_opencode_has_settings_fragment(self) -> None:
        manifest = self._load_manifest(opencode_installer)
        self.assertIn("settings_fragment", manifest)
        self.assertTrue(manifest["settings_fragment"])

    def test_claude_has_uncertainty_and_sources_intentionally_missing_from_opencode(self) -> None:
        """Claude includes rules/uncertainty-and-sources.md; OpenCode omits it by design."""
        claude_files = self._managed_files(claude_installer)
        opencode_files = self._managed_files(opencode_installer)
        self.assertIn("rules/uncertainty-and-sources.md", claude_files)
        self.assertNotIn("rules/uncertainty-and-sources.md", opencode_files)


if __name__ == "__main__":
    unittest.main()
