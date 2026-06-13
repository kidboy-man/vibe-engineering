import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.kits.claude_code import installer as claude_installer
from agents.kits.opencode import installer as opencode_installer


class ClaudeSettingsMergeContractTests(unittest.TestCase):
    """Characterization tests for Claude Code settings.json merge behavior.

    The installer must treat the fragment as defaults and never overwrite:
      - env (always machine-specific)
      - model / provider / autonomy choices
      - any key in SECRET_SETTING_KEYS
    """

    def test_merge_never_overwrites_existing_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude_dir = Path(tmp) / ".claude"
            claude_dir.mkdir()
            existing = {
                "env": {
                    "ANTHROPIC_AUTH_TOKEN": "secret-token",
                    "ANTHROPIC_BASE_URL": "https://proxy.example.invalid",
                },
            }
            (claude_dir / "settings.json").write_text(
                json.dumps(existing), encoding="utf-8"
            )

            paths = claude_installer._paths(home=tmp)
            message, changed = claude_installer._merge_settings(paths, dry_run=False)

            merged = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(merged["env"]["ANTHROPIC_AUTH_TOKEN"], "secret-token")
            self.assertEqual(merged["env"]["ANTHROPIC_BASE_URL"], "https://proxy.example.invalid")

    def test_merge_never_overwrites_existing_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude_dir = Path(tmp) / ".claude"
            claude_dir.mkdir()
            existing = {"model": "opus", "effortLevel": "high"}
            (claude_dir / "settings.json").write_text(
                json.dumps(existing), encoding="utf-8"
            )

            paths = claude_installer._paths(home=tmp)
            message, changed = claude_installer._merge_settings(paths, dry_run=False)

            merged = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(merged["model"], "opus")
            self.assertEqual(merged["effortLevel"], "high")

    def test_merge_applies_defaults_for_missing_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude_dir = Path(tmp) / ".claude"
            claude_dir.mkdir()
            existing = {"model": "opus"}
            (claude_dir / "settings.json").write_text(
                json.dumps(existing), encoding="utf-8"
            )

            paths = claude_installer._paths(home=tmp)
            message, changed = claude_installer._merge_settings(paths, dry_run=False)

            merged = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(merged["model"], "opus")
            self.assertIn("effortLevel", merged)

    def test_merge_skips_secret_setting_keys(self):
        for secret_key in claude_installer.SECRET_SETTING_KEYS:
            with self.subTest(key=secret_key):
                with tempfile.TemporaryDirectory() as tmp:
                    claude_dir = Path(tmp) / ".claude"
                    claude_dir.mkdir()
                    existing = {secret_key: "user-value"}
                    (claude_dir / "settings.json").write_text(
                        json.dumps(existing), encoding="utf-8"
                    )

                    paths = claude_installer._paths(home=tmp)
                    message, changed = claude_installer._merge_settings(paths, dry_run=False)

                    merged = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
                    self.assertEqual(merged.get(secret_key), "user-value")


class OpenCodeJsoncParsingContractTests(unittest.TestCase):
    """Characterization tests for OpenCode JSONC parser behavior.

    The parser must preserve strings that contain // or /* */ as literal
    content, not treat them as comments.
    """

    def test_preserve_string_with_double_slash(self):
        raw = '{"url": "https://example.invalid/path//segment"}'
        parsed = opencode_installer._parse_jsonc(raw)
        self.assertEqual(parsed["url"], "https://example.invalid/path//segment")

    def test_preserve_string_with_block_comment_syntax(self):
        raw = '{"pattern": "foo /* bar */ baz"}'
        parsed = opencode_installer._parse_jsonc(raw)
        self.assertEqual(parsed["pattern"], "foo /* bar */ baz")

    def test_preserve_string_with_escaped_quotes(self):
        raw = '{"msg": "say \\"hello\\""}'
        parsed = opencode_installer._parse_jsonc(raw)
        self.assertEqual(parsed["msg"], 'say "hello"')

    def test_strip_actual_comments_outside_strings(self):
        raw = """{
            // real line comment
            "a": 1,
            /* real block comment */
            "b": 2
        }"""
        parsed = opencode_installer._parse_jsonc(raw)
        self.assertEqual(parsed, {"a": 1, "b": 2})

    def test_strip_trailing_commas(self):
        raw = '{"a": 1, "b": 2,}'
        parsed = opencode_installer._parse_jsonc(raw)
        self.assertEqual(parsed, {"a": 1, "b": 2})


class OpenCodeAgentsMdMergeContractTests(unittest.TestCase):
    """Characterization tests for OpenCode AGENTS.md marker merge behavior.

    The installer must keep user content before the begin marker and after
    the end marker untouched during install, reinstall, and uninstall.
    """

    def test_merge_prepends_marked_section_when_no_markers_exist(self):
        template = "# Global Engineering Persona\n"
        existing = "# My Project Rules\n\nUse tabs.\n"
        merged, action = opencode_installer._merge_agents_md(template, existing)
        self.assertEqual(action, "merge")
        self.assertIn(opencode_installer.AGENTS_BEGIN_MARKER, merged)
        self.assertIn(opencode_installer.AGENTS_END_MARKER, merged)
        self.assertIn("# My Project Rules", merged)
        self.assertIn("Use tabs.", merged)
        self.assertTrue(merged.index("# My Project Rules") > merged.index(opencode_installer.AGENTS_END_MARKER))

    def test_merge_replaces_only_between_markers_on_reinstall(self):
        template = "# Global Engineering Persona\n\nUPDATED BODY.\n"
        existing = (
            "# My Project Rules\n"
            + opencode_installer.AGENTS_BEGIN_MARKER
            + "# Old Persona\n"
            + opencode_installer.AGENTS_END_MARKER
            + "# After Rules\n"
        )
        merged, action = opencode_installer._merge_agents_md(template, existing)
        self.assertEqual(action, "merge")
        self.assertIn("UPDATED BODY", merged)
        self.assertNotIn("Old Persona", merged)
        self.assertIn("# My Project Rules", merged)
        self.assertIn("# After Rules", merged)
        self.assertEqual(merged.count(opencode_installer.AGENTS_BEGIN_MARKER), 1)
        self.assertEqual(merged.count(opencode_installer.AGENTS_END_MARKER), 1)

    def test_merge_returns_unchanged_when_content_identical(self):
        template = "# Global Engineering Persona\n"
        wrapped = opencode_installer.AGENTS_BEGIN_MARKER + template + opencode_installer.AGENTS_END_MARKER
        merged, action = opencode_installer._merge_agents_md(template, wrapped)
        self.assertEqual(action, "unchanged")
        self.assertEqual(merged, wrapped)

    def test_uninstall_strips_section_and_returns_remaining(self):
        existing = (
            "# My Project Rules\n"
            + opencode_installer.AGENTS_BEGIN_MARKER
            + "# Persona\n"
            + opencode_installer.AGENTS_END_MARKER
            + "# After Rules\n"
        )
        remaining, fully_owned = opencode_installer._strip_agents_md_section(existing)
        self.assertFalse(fully_owned)
        self.assertIsNotNone(remaining)
        assert remaining is not None  # for type narrowing
        self.assertNotIn(opencode_installer.AGENTS_BEGIN_MARKER, remaining)
        self.assertNotIn(opencode_installer.AGENTS_END_MARKER, remaining)
        self.assertIn("# My Project Rules", remaining)
        self.assertIn("# After Rules", remaining)

    def test_uninstall_returns_none_when_only_kit_content(self):
        existing = (
            opencode_installer.AGENTS_BEGIN_MARKER
            + "# Persona\n"
            + opencode_installer.AGENTS_END_MARKER
        )
        remaining, fully_owned = opencode_installer._strip_agents_md_section(existing)
        self.assertTrue(fully_owned)
        self.assertIsNone(remaining)


class OldManifestCompatibilityTests(unittest.TestCase):
    """Characterization tests for manifest backward compatibility.

    The installer must continue to read manifests produced by earlier
    versions of the kit so that uninstall works across upgrades.
    """

    def _old_manifest(self, kit_name: str, managed_files: list[str]) -> dict:
        return {
            "tool": "vibe-engineering",
            "kit": kit_name,
            "installed_at": "2024-01-01T00:00:00+00:00",
            "managed_files": managed_files,
            "notes": "Only files listed here are managed by vibe. Uninstall removes unchanged managed files and leaves modified files in place.",
        }

    def test_claude_uninstall_reads_old_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude_dir = Path(tmp) / ".claude"
            claude_dir.mkdir()
            old_manifest = self._old_manifest("claude-code", ["CLAUDE.md", "settings.json"])
            (claude_dir / ".vibe-engineering-manifest.json").write_text(
                json.dumps(old_manifest), encoding="utf-8"
            )
            # Create a managed file that matches the template so it can be removed
            template = claude_installer._template_dir() / "CLAUDE.md"
            if template.exists():
                (claude_dir / "CLAUDE.md").write_text(
                    template.read_text(encoding="utf-8"), encoding="utf-8"
                )

            rc = claude_installer.uninstall(home=tmp, dry_run=False, yes=True)
            self.assertEqual(rc, 0)
            self.assertFalse((claude_dir / ".vibe-engineering-manifest.json").exists())

    def test_opencode_uninstall_reads_old_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "opencode"
            config_dir.mkdir()
            old_manifest = self._old_manifest("opencode", ["AGENTS.md", "opencode.jsonc"])
            (config_dir / ".vibe-engineering-manifest.json").write_text(
                json.dumps(old_manifest), encoding="utf-8"
            )
            # Create a managed file that matches the template so it can be removed
            template = opencode_installer._template_dir() / "AGENTS.md"
            if template.exists():
                wrapped = (
                    opencode_installer.AGENTS_BEGIN_MARKER
                    + template.read_text(encoding="utf-8")
                    + opencode_installer.AGENTS_END_MARKER
                )
                (config_dir / "AGENTS.md").write_text(wrapped, encoding="utf-8")

            rc = opencode_installer.uninstall(home=tmp, dry_run=False, yes=True)
            self.assertEqual(rc, 0)
            self.assertFalse((config_dir / ".vibe-engineering-manifest.json").exists())

    def test_manifest_shape_has_required_keys(self):
        """Current manifest shape must contain keys the uninstaller relies on."""
        for installer, kit_name in (
            (claude_installer, "claude-code"),
            (opencode_installer, "opencode"),
        ):
            with self.subTest(kit=kit_name):
                paths = installer._paths(home="/tmp")
                manifest = installer._manifest_state(paths, ["dummy.md"])
                self.assertIn("tool", manifest)
                self.assertIn("kit", manifest)
                self.assertIn("installed_at", manifest)
                self.assertIn("managed_files", manifest)
                self.assertIn("notes", manifest)
                self.assertEqual(manifest["tool"], "vibe-engineering")
                self.assertEqual(manifest["kit"], kit_name)


if __name__ == "__main__":
    unittest.main()
