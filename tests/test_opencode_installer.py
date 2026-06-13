import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.kits.opencode import installer
from agents.kits.opencode.installer import doctor, install, uninstall


class OpenCodeInstallerTests(unittest.TestCase):
    def test_install_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = install(home=tmp, dry_run=True, yes=True)
            self.assertEqual(rc, 0)
            self.assertFalse((Path(tmp) / "opencode" / "AGENTS.md").exists())

    def test_install_copies_templates_and_preserves_local_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "opencode"
            config_dir.mkdir()
            # Use JSONC with comments + trailing commas to verify the
            # installer can read user config and preserve local-only keys.
            existing = """{
                // Local-only config the kit must NOT touch.
                "model": "anthropic/claude-sonnet-4-5",
                "provider": {
                    "anthropic": {
                        "options": {
                            "apiKey": "sk-secret-do-not-leak"  // secret-ish substring
                        }
                    }
                },
                "plugin": ["oh-my-openagent@latest"],
                "mcp": {
                    "composio": {
                        "headers": {
                            "Authorization": "Bearer sk-secret-do-not-leak"
                        }
                    }
                },
                "theme": "system",
            }
"""
            (config_dir / "opencode.jsonc").write_text(existing, encoding="utf-8")

            rc = install(home=tmp, dry_run=False, yes=True)
            self.assertEqual(rc, 0)
            # Persona + rules + agents + commands + skill are all installed.
            self.assertTrue((config_dir / "AGENTS.md").exists())
            self.assertTrue((config_dir / "rules" / "operating-model.md").exists())
            self.assertTrue((config_dir / "agents" / "go-backend-implementer.md").exists())
            self.assertTrue((config_dir / "commands" / "review-go.md").exists())
            self.assertTrue((config_dir / "skills" / "vibe-engineering" / "SKILL.md").exists())
            # Manifest is written.
            self.assertTrue((config_dir / ".vibe-engineering-manifest.json").exists())
            # opencode.jsonc is merged: local-only keys preserved, secrets preserved.
            merged = json.loads((config_dir / "opencode.jsonc").read_text(encoding="utf-8"))
            self.assertEqual(merged["model"], "anthropic/claude-sonnet-4-5")
            self.assertEqual(merged["plugin"], ["oh-my-openagent@latest"])
            self.assertEqual(merged["theme"], "system")
            self.assertEqual(
                merged["provider"]["anthropic"]["options"]["apiKey"],
                "sk-secret-do-not-leak",
            )
            self.assertEqual(
                merged["mcp"]["composio"]["headers"]["Authorization"],
                "Bearer sk-secret-do-not-leak",
            )
            # Safe defaults from the fragment are applied because they were absent.
            self.assertIn("$schema", merged)
            self.assertTrue(merged.get("lsp"))

    def test_install_is_idempotent_when_nothing_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            backups_dir = Path(tmp) / "opencode" / "backups"
            agents_md = Path(tmp) / "opencode" / "AGENTS.md"
            original_agents = agents_md.read_text(encoding="utf-8")
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            self.assertFalse(backups_dir.exists(), "idempotent re-install must not create backups")
            self.assertEqual(agents_md.read_text(encoding="utf-8"), original_agents)

    def test_uninstall_keeps_modified_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "opencode"
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            agents_md = config_dir / "AGENTS.md"
            agents_md.write_text(agents_md.read_text(encoding="utf-8") + "\nlocal change\n", encoding="utf-8")

            rc = uninstall(home=tmp, dry_run=False, yes=True)

            self.assertEqual(rc, 0)
            self.assertTrue(agents_md.exists())
            self.assertFalse((config_dir / ".vibe-engineering-manifest.json").exists())

    def test_doctor_runs_against_empty_temp_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = doctor(home=tmp)
            self.assertIn(rc, (0, 1))

    def test_paths_respects_xdg_config_home(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/fake-xdg"}):
            paths = installer._paths()
        self.assertEqual(paths.config_dir, Path("/tmp/fake-xdg/opencode"))

    def test_install_merges_into_existing_agents_md_preserving_user_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "opencode"
            config_dir.mkdir()
            user_agents = "# My Project Rules\n\nUse tabs, not spaces. Commit messages in English only.\n"
            (config_dir / "AGENTS.md").write_text(user_agents, encoding="utf-8")

            rc = install(home=tmp, dry_run=False, yes=True)
            self.assertEqual(rc, 0)

            merged = (config_dir / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn(installer.AGENTS_BEGIN_MARKER, merged)
            self.assertIn(installer.AGENTS_END_MARKER, merged)
            self.assertIn("Global Engineering Persona", merged)
            self.assertIn("# My Project Rules", merged)
            self.assertIn("Use tabs, not spaces", merged)
            self.assertIn("Commit messages in English only", merged)

    def test_install_replaces_only_section_between_markers_on_reinstall(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "opencode"
            config_dir.mkdir()
            user_agents = "# My Project Rules\n\nUse tabs, not spaces.\n"
            (config_dir / "AGENTS.md").write_text(user_agents, encoding="utf-8")

            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)

            # Patch the on-disk template to simulate a kit release that updates
            # the persona body, then re-run install and verify only the
            # marked section is replaced — user content stays untouched.
            original_template = installer._template_dir() / "AGENTS.md"
            backup = original_template.read_text(encoding="utf-8")
            try:
                original_template.write_text("# Global Engineering Persona\n\nUPDATED PERSONA BODY.\n", encoding="utf-8")
                self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            finally:
                original_template.write_text(backup, encoding="utf-8")

            second = (config_dir / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("UPDATED PERSONA BODY", second)
            self.assertNotIn("Operating Identity", second)
            self.assertEqual(second.count(installer.AGENTS_BEGIN_MARKER), 1)
            self.assertEqual(second.count(installer.AGENTS_END_MARKER), 1)
            self.assertIn("# My Project Rules", second)
            self.assertIn("Use tabs, not spaces", second)

    def test_install_agents_md_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "opencode"
            config_dir.mkdir()
            user_agents = "# My Project Rules\n\nUse tabs, not spaces.\n"
            (config_dir / "AGENTS.md").write_text(user_agents, encoding="utf-8")

            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            backups_dir = config_dir / "backups"
            self.assertTrue(backups_dir.exists(), "first install must back up the user's existing AGENTS.md")
            backup_count_before = sum(1 for _ in backups_dir.rglob("*") if _.is_file())
            first = (config_dir / "AGENTS.md").read_text(encoding="utf-8")
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            second = (config_dir / "AGENTS.md").read_text(encoding="utf-8")
            self.assertEqual(first, second)
            backup_count_after = sum(1 for _ in backups_dir.rglob("*") if _.is_file())
            self.assertEqual(backup_count_before, backup_count_after, "idempotent re-install must not add more backups")

    def test_uninstall_strips_persona_section_and_keeps_user_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "opencode"
            config_dir.mkdir()
            user_agents = "# My Project Rules\n\nUse tabs, not spaces.\n"
            (config_dir / "AGENTS.md").write_text(user_agents, encoding="utf-8")

            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            self.assertEqual(uninstall(home=tmp, dry_run=False, yes=True), 0)

            after = (config_dir / "AGENTS.md").read_text(encoding="utf-8")
            self.assertNotIn(installer.AGENTS_BEGIN_MARKER, after)
            self.assertNotIn(installer.AGENTS_END_MARKER, after)
            self.assertEqual(after, user_agents)

    def test_uninstall_deletes_agents_md_when_no_user_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "opencode"
            self.assertEqual(install(home=tmp, dry_run=False, yes=True), 0)
            self.assertTrue((config_dir / "AGENTS.md").exists())

            self.assertEqual(uninstall(home=tmp, dry_run=False, yes=True), 0)
            self.assertFalse((config_dir / "AGENTS.md").exists())


class OpenCodeManifestContractTests(unittest.TestCase):
    def test_manifest_managed_files_exist(self):
        template_dir = installer._template_dir()
        manifest = installer._load_manifest(installer.KitPaths(
            home=Path("/tmp"),
            config_dir=Path("/tmp/opencode"),
            manifest_path=Path("/tmp/opencode/.vibe-engineering-manifest.json"),
            template_dir=template_dir,
        ))
        for rel in manifest["managed_files"]:
            self.assertTrue(
                (template_dir / rel).exists(),
                f"managed file {rel} not present at {template_dir / rel}",
            )

    def test_manifest_includes_persona_rules_agents_commands_skill(self):
        template_dir = installer._template_dir()
        manifest = installer._load_manifest(installer.KitPaths(
            home=Path("/tmp"),
            config_dir=Path("/tmp/opencode"),
            manifest_path=Path("/tmp/opencode/.vibe-engineering-manifest.json"),
            template_dir=template_dir,
        ))
        managed = manifest["managed_files"]
        self.assertIn("AGENTS.md", managed)
        self.assertIn("rules/operating-model.md", managed)
        self.assertIn("rules/go-backend-engineering.md", managed)
        self.assertIn("rules/security-and-data-safety.md", managed)
        self.assertIn("rules/database-and-operations.md", managed)
        self.assertIn("rules/testing-and-verification.md", managed)
        for agent in (
            "backend-tech-lead",
            "go-backend-implementer",
            "security-data-reviewer",
            "db-operations-reviewer",
            "tdd-test-engineer",
        ):
            self.assertIn(f"agents/{agent}.md", managed)
        for cmd in ("trd", "review-go", "clone-setup"):
            self.assertIn(f"commands/{cmd}.md", managed)
        self.assertIn("skills/vibe-engineering/SKILL.md", managed)


class JsoncParsingTests(unittest.TestCase):
    def test_strip_jsonc_comments_handles_line_block_and_strings(self):
        raw = """{
            // line comment
            "a": 1, /* block */
            "b": "hello // not a comment",
            "c": "/* also not */"
        }"""
        parsed = installer._parse_jsonc(raw)
        self.assertEqual(parsed["a"], 1)
        self.assertEqual(parsed["b"], "hello // not a comment")
        self.assertEqual(parsed["c"], "/* also not */")

    def test_strip_jsonc_handles_trailing_commas(self):
        raw = """{
            "a": 1,
            "b": 2,
        }"""
        parsed = installer._parse_jsonc(raw)
        self.assertEqual(parsed, {"a": 1, "b": 2})

    def test_secret_key_detection(self):
        for key in ("apiKey", "API_TOKEN", "client_secret", "dbPassword", "authHeader", "userCredential"):
            self.assertTrue(installer._is_secret_key(key))
        for key in ("model", "plugin", "theme", "lsp", "provider"):
            self.assertFalse(installer._is_secret_key(key))


if __name__ == "__main__":
    unittest.main()
