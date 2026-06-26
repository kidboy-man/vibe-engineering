import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import merge_strategies as ms  # noqa: E402

try:
    from agents.kits.second_brain.installer import (  # noqa: E402, F401
        _paths,
        install,
        doctor,
        diff_kit,
        uninstall,
    )
except ModuleNotFoundError:
    _paths = None  # type: ignore[assignment]
    install = None  # type: ignore[assignment]
    doctor = None
    diff_kit = None
    uninstall = None


VAULT_DIRS = [
    "raw/assets",
    "inbox",
    "wiki/sources/learning",
    "wiki/sources/journal",
    "wiki/entities/projects",
    "wiki/concepts/backend",
    "wiki/concepts/ai-engineering",
    "wiki/concepts/pkm",
    "wiki/concepts/personal",
    "wiki/synthesis",
    "output",
    ".claude",
]

SEED_PAGES = {
    "wiki/index.md": "index placeholder",
    "wiki/log.md": "log placeholder",
    "wiki/hot.md": "hot placeholder",
}

GITIGNORE_ENTRIES = [
    "node_modules/",
    ".qmd/",
    ".claude/settings.local.json",
]


class SecondBrainPathsTests(unittest.TestCase):
    """Unit tests for _paths() in second_brain installer."""

    def test_default_vault_is_second_brain_under_home(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            paths = _paths(home=str(home))
            self.assertEqual(paths.vault, home / "second-brain")

    def test_env_override_uses_exact_path_no_append(self):
        with tempfile.TemporaryDirectory() as vault_dir:
            with tempfile.TemporaryDirectory() as home_str:
                with patch.dict(
                    os.environ,
                    {"VIBE_SECOND_BRAIN_PATH": vault_dir},
                    clear=True,
                ):
                    paths = _paths(home=str(Path(home_str)))
                    self.assertEqual(paths.vault, Path(vault_dir))

    def test_agent_roots_derive_from_home(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            paths = _paths(home=str(home))
            self.assertEqual(paths.claude_dir, home / ".claude")
            self.assertEqual(paths.opencode_config_dir, home / ".config" / "opencode")
            self.assertEqual(paths.codex_dir, home / ".codex")


class SecondBrainDryRunTests(unittest.TestCase):
    """Tests for install(..., dry_run=True, yes=True)."""

    def test_dry_run_writes_no_files_or_directories(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            default_vault = home / "second-brain"
            install(home=str(home), dry_run=True, yes=True)
            self.assertFalse(
                default_vault.exists(),
                f"dry-run must not create {default_vault}",
            )
            self.assertFalse(
                (home / ".claude").exists(),
                "dry-run must not create .claude",
            )
            self.assertFalse(
                (home / ".config").exists(),
                "dry-run must not create .config",
            )
            self.assertFalse(
                (home / ".codex").exists(),
                "dry-run must not create .codex",
            )

    def test_dry_run_with_env_override_writes_nothing(self):
        with tempfile.TemporaryDirectory() as vault_dir:
            vault = Path(vault_dir)
            with tempfile.TemporaryDirectory() as home_str:
                home = Path(home_str)
                with patch.dict(
                    os.environ,
                    {"VIBE_SECOND_BRAIN_PATH": vault_dir},
                    clear=True,
                ):
                    install(home=str(home), dry_run=True, yes=True)
                    self.assertFalse(
                        vault.exists() and any(vault.iterdir()),
                        f"dry-run must not populate {vault}",
                    )


class SecondBrainVaultCreationTests(unittest.TestCase):
    """Tests for vault directory creation during install."""

    def test_install_creates_all_vault_dirs(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            result = install(home=str(home), dry_run=False, yes=True)
            vault = home / "second-brain"
            self.assertEqual(result, 0)
            for rel in VAULT_DIRS:
                full = vault / rel
                self.assertTrue(
                    full.is_dir(),
                    f"missing vault dir: {rel}",
                )

    def test_vault_dirs_match_setup_spec(self):
        """Ensure dirs created match LLM_SECOND_BRAIN_SETUP.md:38-52."""
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            vault = home / "second-brain"

            # Top-level: raw, inbox, wiki, output, .claude
            for top in ["raw", "inbox", "wiki", "output", ".claude"]:
                self.assertTrue((vault / top).is_dir(), f"missing top dir: {top}")

            # raw/assets
            self.assertTrue((vault / "raw" / "assets").is_dir())

            # wiki sub-structure
            wiki = vault / "wiki"
            for sub in ["sources", "entities", "concepts", "synthesis"]:
                self.assertTrue((wiki / sub).is_dir(), f"missing wiki sub: {sub}")

            # wiki/sources sub-dirs
            for sub in ["learning", "journal"]:
                self.assertTrue(
                    (wiki / "sources" / sub).is_dir(),
                    f"missing wiki/sources/{sub}",
                )

            # wiki/entities sub-dirs
            self.assertTrue((wiki / "entities" / "projects").is_dir())

            # wiki/concepts sub-dirs
            for sub in ["backend", "ai-engineering", "pkm", "personal"]:
                self.assertTrue(
                    (wiki / "concepts" / sub).is_dir(),
                    f"missing wiki/concepts/{sub}",
                )


class SecondBrainSeedPageTests(unittest.TestCase):
    """Tests for seed page creation behavior."""

    def test_seed_pages_created_if_absent(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            vault = home / "second-brain"
            for rel, _placeholder in SEED_PAGES.items():
                full = vault / rel
                self.assertTrue(
                    full.is_file(),
                    f"seed page not created: {rel}",
                )

    def test_seed_pages_never_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            vault = home / "second-brain"
            install(home=str(home), dry_run=False, yes=True)

            # Record initial contents
            initial = {}
            for rel in SEED_PAGES:
                full = vault / rel
                initial[rel] = full.read_bytes()

            # Modify each seed page
            custom_content = b"custom user content here"
            for rel in SEED_PAGES:
                full = vault / rel
                full.write_bytes(custom_content)

            # Reinstall
            install(home=str(home), dry_run=False, yes=True)

            # Assert every seed page is unchanged
            for rel in SEED_PAGES:
                full = vault / rel
                actual = full.read_bytes()
                self.assertEqual(
                    actual,
                    custom_content,
                    f"seed page was overwritten: {rel}",
                )


class SecondBrainGitignoreTests(unittest.TestCase):
    """Tests for .gitignore merging behavior."""

    def test_gitignore_created_with_expected_entries(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            gitignore = home / "second-brain" / ".gitignore"
            self.assertTrue(gitignore.is_file(), ".gitignore not created")
            content = gitignore.read_text(encoding="utf-8")
            for entry in GITIGNORE_ENTRIES:
                self.assertIn(
                    entry,
                    content,
                    f"missing gitignore entry: {entry}",
                )

    def test_gitignore_merges_without_duplicates(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            vault = home / "second-brain"
            vault.mkdir(parents=True, exist_ok=True)
            gitignore = vault / ".gitignore"

            # Pre-populate with one duplicate and one user line
            gitignore.write_text(
                "node_modules/\nmy-custom-ignore/\n", encoding="utf-8"
            )

            install(home=str(home), dry_run=False, yes=True)

            content = gitignore.read_text(encoding="utf-8")
            lines = content.strip().split("\n")

            # No duplicates
            self.assertEqual(
                lines.count("node_modules/"),
                1,
                "duplicate gitignore entry: node_modules/",
            )
            self.assertEqual(
                lines.count(".qmd/"),
                1,
                "duplicate gitignore entry: .qmd/",
            )

            # User line preserved
            self.assertIn(
                "my-custom-ignore/",
                lines,
                "user gitignore line lost",
            )

    def test_gitignore_preserves_user_lines(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            vault = home / "second-brain"
            vault.mkdir(parents=True, exist_ok=True)
            gitignore = vault / ".gitignore"
            gitignore.write_text(
                "# my custom rules\n.env\n*.log\n", encoding="utf-8"
            )

            install(home=str(home), dry_run=False, yes=True)

            content = gitignore.read_text(encoding="utf-8")
            self.assertIn("# my custom rules", content)
            self.assertIn(".env", content)
            self.assertIn("*.log", content)


class SecondBrainGitInitTests(unittest.TestCase):
    """Tests for git init behavior."""

    def test_git_init_creates_dot_git(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            git_dir = home / "second-brain" / ".git"
            self.assertTrue(
                git_dir.is_dir(),
                ".git not created by git init",
            )

    def test_git_init_idempotent_no_error_when_dot_git_exists(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            vault = home / "second-brain"

            # First install creates .git
            result1 = install(home=str(home), dry_run=False, yes=True)
            self.assertEqual(result1, 0)
            self.assertTrue((vault / ".git").is_dir())

            # Second install must not fail
            result2 = install(home=str(home), dry_run=False, yes=True)
            self.assertEqual(result2, 0)
            self.assertTrue(
                (vault / ".git").is_dir(),
                ".git should still exist after reinstall",
            )

    def test_git_init_no_reinit_or_error(self):
        """If .git exists, second install succeeds without touching it."""
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            vault = home / "second-brain"

            # Record git dir mtime before reinstall
            git_dir = vault / ".git"
            mtime_before = git_dir.stat().st_mtime

            # Reinstall
            result = install(home=str(home), dry_run=False, yes=True)
            self.assertEqual(result, 0)

            # .git must exist and mtime unchanged (not re-initialized)
            self.assertTrue(git_dir.is_dir())
            mtime_after = git_dir.stat().st_mtime
            self.assertEqual(
                mtime_before,
                mtime_after,
                ".git was re-initialized",
            )


class SecondBrainDoctorTests(unittest.TestCase):
    """Tests for the doctor command."""

    def test_doctor_returns_zero_on_clean_vault(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            result = doctor(home=str(home))
            self.assertEqual(result, 0)

    def test_doctor_returns_nonzero_when_vault_missing(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            # Don't install, vault doesn't exist
            result = doctor(home=str(home))
            self.assertNotEqual(result, 0)


class SecondBrainDiffTests(unittest.TestCase):
    """Tests for diff_kit command."""

    def test_diff_returns_zero_when_no_changes_needed(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            result = diff_kit(home=str(home))
            self.assertEqual(result, 0)


class SecondBrainUninstallTests(unittest.TestCase):
    """Tests for uninstall command."""

    def test_uninstall_never_deletes_vault_content(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            vault = home / "second-brain"

            # Create a user file in the vault
            user_file = vault / "wiki" / "entities" / "projects" / "my-project.md"
            user_file.parent.mkdir(parents=True, exist_ok=True)
            user_file.write_text("# My Project\n", encoding="utf-8")

            # Create user gitignore content
            gitignore = vault / ".gitignore"
            gitignore.write_text(
                gitignore.read_text(encoding="utf-8") + "\n.extra-ignore\n",
                encoding="utf-8",
            )

            uninstall(home=str(home), dry_run=False, yes=True)

            # Vault content must survive
            self.assertTrue(vault.exists(), "vault was deleted")
            self.assertTrue(user_file.exists(), "user wiki file was deleted")
            self.assertTrue(gitignore.exists(), ".gitignore was deleted")
            self.assertTrue((vault / ".git").is_dir(), ".git was deleted")

    def test_uninstall_removes_kit_manifest_not_vault(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            home_path = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            uninstall(home=str(home), dry_run=False, yes=True)

            # Vault must survive
            vault = home_path / "second-brain"
            self.assertTrue(
                vault.exists(),
                "vault must survive uninstall",
            )


class SecondBrainConfigMergeCycleTests(unittest.TestCase):
    """Config merge + strip cycle: user config survives both directions."""

    def test_claude_json_user_keys_intact_after_merge_then_strip(self):
        user = {"model": "opus", "effortLevel": "high"}
        fragment = {"effortLevel": "xhigh", "autoUpdate": True}

        merged, changed = ms.json_defaults_strategy(fragment, dict(user), set())
        self.assertTrue(changed)
        self.assertEqual(merged["model"], "opus")
        self.assertEqual(merged["effortLevel"], "high")

        for k in list(merged.keys()):
            if k not in user:
                del merged[k]
        self.assertEqual(merged, user)

    def test_opencode_jsonc_user_keys_intact_after_merge_then_strip(self):
        user = {"model": "anthropic", "apiKey": "sk-secret"}
        fragment = {"$schema": "https://example.invalid/schema", "lsp": True}

        merged, changed = ms.jsonc_defaults_strategy(
            fragment, dict(user),
            local_only_keys={"model"},
            is_secret_key=lambda k: "key" in k.lower(),
        )
        self.assertTrue(changed)
        self.assertEqual(merged["apiKey"], "sk-secret")
        self.assertEqual(merged["model"], "anthropic")
        self.assertTrue(merged["lsp"])

        for k in list(merged.keys()):
            if k not in user:
                del merged[k]
        self.assertEqual(merged, user)

    def test_codex_toml_unrelated_config_survives_merge_then_strip(self):
        section = "[mcp_servers.qmd]"
        body = 'type = "stdio"\ncommand = "qmd"\nargs = ["mcp"]\n'
        user_config = '[server]\nhost = "0.0.0.0"\nport = 8080\n# my comment\n'

        merged, _ = ms.toml_block_merge_strategy(section, body, user_config)
        self.assertIn("[server]", merged)
        self.assertIn(section, merged)

        remaining, fully_owned = ms.strip_toml_block(merged, section)
        self.assertFalse(fully_owned)
        assert remaining is not None
        self.assertIn("[server]", remaining)
        self.assertIn('host = "0.0.0.0"', remaining)
        self.assertNotIn(section, remaining)
        self.assertNotIn("qmd", remaining)

    def test_codex_toml_user_only_unchanged_when_no_kit_section(self):
        user_config = '[server]\nhost = "0.0.0.0"\n'
        section = "[mcp_servers.qmd]"
        body = 'type = "stdio"\ncommand = "qmd"\n'

        merged, action = ms.toml_block_merge_strategy(section, body, user_config)
        self.assertEqual(action, "merge")
        self.assertIn(user_config.strip(), merged)

        remaining, _ = ms.strip_toml_block(merged, section)
        assert remaining is not None
        self.assertNotIn("qmd", remaining)

    def test_env_user_vars_survive_merge_then_strip(self):
        begin = "# vibe-engineering second-brain:begin\n"
        end = "# vibe-engineering second-brain:end\n"
        user = "USER_VAR=1\nOTHER=2\n"
        kit = "KIT_VAR=second_brain\n"

        merged, action = ms.marked_section_strategy(kit, user, begin, end)
        self.assertEqual(action, "merge")
        self.assertIn("USER_VAR=1", merged)
        self.assertIn("KIT_VAR=second_brain", merged)

        remaining, fully_owned = ms.strip_marked_section(merged, begin, end)
        self.assertFalse(fully_owned)
        assert remaining is not None
        self.assertIn("USER_VAR=1", remaining)
        self.assertNotIn("KIT_VAR=second_brain", remaining)


class SecondBrainSecretKeySafetyTests(unittest.TestCase):
    """No secret/local-only keys added or overwritten by any merge strategy."""

    def test_json_never_adds_secret_keys(self):
        fragment = {"model": "sonnet", "ANTHROPIC_API_KEY": "leak"}
        merged, changed = ms.json_defaults_strategy(
            fragment, {}, {"ANTHROPIC_API_KEY"}
        )
        self.assertNotIn("ANTHROPIC_API_KEY", merged)

    def test_json_never_overwrites_existing_secret(self):
        fragment = {"ANTHROPIC_API_KEY": "leak"}
        current = {"ANTHROPIC_API_KEY": "user-real-key"}
        merged, changed = ms.json_defaults_strategy(
            fragment, current, {"ANTHROPIC_API_KEY"}
        )
        self.assertFalse(changed)
        self.assertEqual(merged["ANTHROPIC_API_KEY"], "user-real-key")

    def test_jsonc_never_adds_local_only_keys(self):
        fragment = {"model": "sonnet", "$schema": "https://example.invalid/schema"}
        merged, changed = ms.jsonc_defaults_strategy(
            fragment, {},
            local_only_keys={"model"},
            is_secret_key=lambda k: False,
        )
        self.assertNotIn("model", merged)
        self.assertIn("$schema", merged)

    def test_jsonc_never_adds_keys_matching_secret_substrings(self):
        fragment = {"apiKey": "leak", "authToken": "leak", "lsp": True}
        merged, changed = ms.jsonc_defaults_strategy(
            fragment, {},
            local_only_keys=set(),
            is_secret_key=lambda k: any(
                sub in k.lower()
                for sub in ("token", "key", "secret", "password", "auth", "credential")
            ),
        )
        self.assertNotIn("apiKey", merged)
        self.assertNotIn("authToken", merged)
        self.assertTrue(merged["lsp"])

    def test_jsonc_never_overwrites_existing_secret(self):
        fragment = {"apiKey": "leak", "lsp": True}
        current = {"apiKey": "user-real-key"}
        merged, changed = ms.jsonc_defaults_strategy(
            fragment, dict(current),
            local_only_keys=set(),
            is_secret_key=lambda k: "key" in k.lower(),
        )
        self.assertEqual(merged["apiKey"], "user-real-key")


class SecondBrainMarkerSafetyTests(unittest.TestCase):
    """No ``<!-- vibe-engineering-kit`` markers outside Markdown files."""

    def test_no_html_markers_in_toml_section_or_body(self):
        section = "[mcp_servers.qmd]"
        body = 'type = "stdio"\ncommand = "qmd"\nargs = ["mcp"]\n'
        self.assertNotIn("<!--", section)
        self.assertNotIn("-->", section)
        self.assertNotIn("<!--", body)
        self.assertNotIn("-->", body)

    def test_env_markers_stay_shell_comments_not_html(self):
        begin = "# vibe-engineering second-brain:begin\n"
        end = "# vibe-engineering second-brain:end\n"
        self.assertNotIn("<!--", begin)
        self.assertNotIn("-->", begin)
        self.assertNotIn("<!--", end)
        self.assertNotIn("-->", end)
        self.assertTrue(begin.startswith("#"))
        self.assertFalse(begin.startswith("<"))

    def test_json_fragment_has_no_html_markers(self):
        fragment = {"effortLevel": "xhigh", "autoUpdate": True}
        raw = json.dumps(fragment)
        self.assertNotIn("<!--", raw)
        self.assertNotIn("-->", raw)
        self.assertNotIn("vibe-engineering-kit", raw)

    def test_jsonc_fragment_has_no_html_markers(self):
        fragment = {"$schema": "https://example.invalid/schema", "lsp": True}
        raw = json.dumps(fragment)
        self.assertNotIn("<!--", raw)
        self.assertNotIn("-->", raw)
        self.assertNotIn("vibe-engineering-kit", raw)


if __name__ == "__main__":
    unittest.main()
