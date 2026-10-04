"""Freeze the second-brain on-disk contract.

A newer vibe finds, de-duplicates and removes what an older vibe wrote by
matching these exact strings. Changing any of them breaks upgrades for
existing users, so these assertions must only change together with a
migration. Also guards the public names other modules import from the
installer facade.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.kits.second_brain import installer as sb

TEMPLATE = Path(sb.__file__).resolve().parent / "templates" / "second_brain"

FACADE_NAMES = [
    "install", "diff_kit", "doctor", "uninstall", "enable_hook",
    "_paths", "_template_dir", "_confirm", "_setup_qmd",
    "_hook_command", "_hook_already_installed",
    "_codex_hook_command", "_codex_hook_already_installed",
    "_cursor_hook_command", "_cursor_hook_already_installed",
    "_enable_proactive_context", "_offer_proactive_context",
    "_merge_cursor_config", "_merge_opencode_qmd_mcp",
    "_is_legacy_kit_owned_qmd_mcp", "_is_expected_opencode_qmd_mcp",
    "OPENCODE_QMD_MCP_ENTRY", "QMD_MCP_SNIPPET_JSON",
    "HOOK_SCRIPT_REL", "SESSIONSTART_EVENT", "CURSOR_SESSIONSTART_EVENT", "CURSOR_RULE_REL",
    "CLAUDE_MD_BEGIN_MARKER", "CLAUDE_MD_END_MARKER",
    "CODEX_INSTRUCTIONS_BEGIN_MARKER", "CODEX_INSTRUCTIONS_END_MARKER",
    "OPENCODE_AGENTS_BEGIN_MARKER", "OPENCODE_AGENTS_END_MARKER",
    "shutil", "subprocess", "core",
]


class FacadeTests(unittest.TestCase):
    def test_public_and_patched_names_resolve_on_installer_module(self):
        for name in FACADE_NAMES:
            with self.subTest(name=name):
                self.assertTrue(hasattr(sb, name), f"installer facade lost {name}")


class MarkerAndPathContractTests(unittest.TestCase):
    def test_markers_are_byte_stable(self):
        self.assertEqual(sb.CLAUDE_MD_BEGIN_MARKER, "<!-- vibe-engineering second-brain:begin -->\n")
        self.assertEqual(sb.CLAUDE_MD_END_MARKER, "<!-- vibe-engineering second-brain:end -->\n")
        self.assertEqual(sb.CODEX_INSTRUCTIONS_BEGIN_MARKER, "<!-- vibe-engineering second-brain (codex):begin -->\n")
        self.assertEqual(sb.CODEX_INSTRUCTIONS_END_MARKER, "<!-- vibe-engineering second-brain (codex):end -->\n")
        self.assertEqual(sb.OPENCODE_AGENTS_BEGIN_MARKER, "<!-- vibe-engineering second-brain (opencode):begin -->\n")
        self.assertEqual(sb.OPENCODE_AGENTS_END_MARKER, "<!-- vibe-engineering second-brain (opencode):end -->\n")

    def test_relative_paths_and_events(self):
        self.assertEqual(sb.HOOK_SCRIPT_REL, "hooks/second-brain-context.py")
        self.assertEqual(sb.SESSIONSTART_EVENT, "SessionStart")
        self.assertEqual(sb.CURSOR_SESSIONSTART_EVENT, "sessionStart")
        self.assertEqual(sb.CURSOR_RULE_REL, "rules/second-brain.mdc")
        self.assertEqual(sb.SKILL_ROOT_REL, "skills")
        self.assertEqual(sb.QMD_COLLECTION_NAME, "second-brain")

    def test_vault_layout_constants(self):
        self.assertEqual(sb.SEED_PAGES, ["wiki/index.md", "wiki/log.md", "wiki/hot.md"])
        self.assertEqual(sb.GITIGNORE_ENTRIES, ["node_modules/", ".qmd/", ".claude/settings.local.json"])
        self.assertEqual(
            sb.VAULT_DIRS,
            ["raw/assets", "inbox", "wiki/sources/learning", "wiki/sources/journal", "wiki/entities/projects",
             "wiki/concepts/backend", "wiki/concepts/ai-engineering", "wiki/concepts/pkm", "wiki/concepts/personal",
             "wiki/synthesis", "output", ".claude"],
        )

    def test_agent_dirs_and_manifest_location(self):
        paths = sb._paths("/h")
        self.assertEqual(paths.claude_dir, Path("/h/.claude"))
        self.assertEqual(paths.codex_dir, Path("/h/.codex"))
        self.assertEqual(paths.cursor_dir, Path("/h/.cursor"))
        self.assertEqual(paths.opencode_config_dir, Path("/h/.config/opencode"))
        self.assertEqual(paths.manifest.name, ".vibe-engineering-manifest.json")
        self.assertEqual(paths.manifest.parent, paths.vault)


class HookContractTests(unittest.TestCase):
    def setUp(self):
        self.paths = sb._paths("/h")

    def test_hook_commands(self):
        self.assertEqual(sb._hook_command(self.paths), 'python3 "/h/.claude/hooks/second-brain-context.py"')
        self.assertEqual(sb._codex_hook_command(self.paths), 'python3 "/h/.codex/hooks/second-brain-context.py"')
        self.assertEqual(
            sb._cursor_hook_command(self.paths), 'python3 "/h/.cursor/hooks/second-brain-context.py" --format=cursor'
        )

    def test_codex_block_and_identity(self):
        self.assertEqual(
            sb._codex_hook_block(self.paths),
            "[[hooks.SessionStart]]\n\n[[hooks.SessionStart.hooks]]\n"
            'type = "command"\n'
            "command = 'python3 \"/h/.codex/hooks/second-brain-context.py\"'\n",
        )
        self.assertEqual(
            sb._codex_hook_identity(self.paths), "command = 'python3 \"/h/.codex/hooks/second-brain-context.py\"'"
        )


class McpContractTests(unittest.TestCase):
    def test_entries(self):
        self.assertEqual(sb.QMD_MCP_SNIPPET_JSON, {"mcpServers": {"qmd": {"type": "stdio", "command": "qmd", "args": ["mcp"]}}})
        self.assertEqual(sb.OPENCODE_QMD_MCP_ENTRY, {"type": "local", "command": "qmd", "args": ["mcp"], "enabled": True})
        self.assertEqual(sb.CODEX_TOML_SECTION, "[mcp_servers.qmd]")
        self.assertEqual(sb.CODEX_TOML_BODY, 'type = "stdio"\ncommand = "qmd"\nargs = ["mcp"]\n')


class SkillAndManifestContractTests(unittest.TestCase):
    def test_shipped_skill_names(self):
        names = sorted(p.parent.name for p in (TEMPLATE / "skills").glob("*/SKILL.md"))
        self.assertEqual(
            names,
            ["autoresearch", "canvas", "defuddle", "obsidian-bases", "obsidian-markdown", "save", "second-brain",
             "think", "wiki", "wiki-cli", "wiki-fold", "wiki-ingest", "wiki-lint", "wiki-mode", "wiki-query",
             "wiki-retrieve"],
        )

    def test_runtime_manifest_keys(self):
        state = sb._manifest_state([".gitignore"])
        for key in ("tool", "kit", "installed_at", "managed_files", "notes", "status"):
            self.assertIn(key, state)
        self.assertEqual(state["tool"], "vibe-engineering")
        self.assertEqual(state["kit"], "second-brain")
        self.assertEqual(state["managed_files"], [".gitignore"])
        self.assertEqual(state["status"], "complete")
        self.assertNotIn("phase", state)
        self.assertEqual(sb._manifest_state([], status="incomplete", phase="qmd")["phase"], "qmd")
        json.dumps(state)


if __name__ == "__main__":
    unittest.main()
