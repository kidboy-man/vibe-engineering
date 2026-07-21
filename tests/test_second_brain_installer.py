import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import merge_strategies as ms  # noqa: E402

try:
    from agents.kits.second_brain.installer import (  # noqa: E402
        _paths,
        install,
        doctor,
        diff_kit,
        uninstall,
        _setup_qmd,
        OPENCODE_QMD_MCP_ENTRY,
        _is_legacy_kit_owned_qmd_mcp,
        _is_expected_opencode_qmd_mcp,
        _merge_opencode_qmd_mcp,
        _merge_cursor_config,
        QMD_MCP_SNIPPET_JSON,
        _hook_command,
        _hook_already_installed,
        _enable_proactive_context,
        _offer_proactive_context,
        _codex_hook_command,
        _codex_hook_already_installed,
        _cursor_hook_command,
        _cursor_hook_already_installed,
        enable_hook,
        HOOK_SCRIPT_REL,
        SESSIONSTART_EVENT,
        CURSOR_SESSIONSTART_EVENT,
        CURSOR_RULE_REL,
        CLAUDE_MD_BEGIN_MARKER,
        CLAUDE_MD_END_MARKER,
        CODEX_INSTRUCTIONS_BEGIN_MARKER,
        CODEX_INSTRUCTIONS_END_MARKER,
        OPENCODE_AGENTS_BEGIN_MARKER,
        OPENCODE_AGENTS_END_MARKER,
    )
except ModuleNotFoundError as exc:
    raise unittest.SkipTest(f"second_brain installer unavailable: {exc}") from exc


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
            self.assertEqual(paths.cursor_dir, home / ".cursor")


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
        """Ensure dirs created match docs/second-brain-setup.md:38-52."""
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

    def _which_returns_qmd(self, cmd):
        if cmd == "qmd":
            return "/fake/qmd"
        if cmd == "git":
            return "/usr/bin/git"
        return None

    def _which_returns_qmd_and_agents(self, cmd):
        known = {
            "git": "/usr/bin/git",
            "qmd": "/fake/qmd",
            "claude": "/fake/claude",
            "opencode": "/fake/opencode",
            "codex": "/fake/codex",
            "obsidian": "/fake/obsidian",
        }
        return known.get(cmd)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_returns_zero_when_qmd_collection_matches(
        self, mock_run, mock_which
    ):
        mock_which.side_effect = self._which_returns_qmd_and_agents
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")

            mock_run.return_value = subprocess.CompletedProcess(
                args=["qmd", "collection", "list"],
                returncode=0,
                stdout=f"  {wiki_path}\n/some/other\n",
                stderr="",
            )
            result = doctor(home=str(home))
            self.assertEqual(result, 0)

    def test_doctor_returns_nonzero_when_vault_missing(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            result = doctor(home=str(home))
            self.assertNotEqual(result, 0)

    @patch("agents.kits.second_brain.installer.shutil.which")
    def test_doctor_returns_nonzero_when_qmd_missing(self, mock_which):
        def _which(cmd):
            if cmd == "git":
                return "/usr/bin/git"
            if cmd in ("node", "npm"):
                return f"/fake/{cmd}"
            return None

        mock_which.side_effect = _which
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = doctor(home=str(home))
            output = buf.getvalue()
            self.assertIn("qmd not found", output)
            self.assertIn("npm install -g @tobilu/qmd", output)
            self.assertEqual(result, 1)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_returns_nonzero_when_no_matching_collection(
        self, mock_run, mock_which
    ):
        mock_which.side_effect = self._which_returns_qmd
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)

            mock_run.return_value = subprocess.CompletedProcess(
                args=["qmd", "collection", "list"],
                returncode=0,
                stdout="/some/other/collection\n",
                stderr="",
            )
            result = doctor(home=str(home))
            self.assertEqual(result, 1)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_returns_nonzero_when_collection_list_fails(
        self, mock_run, mock_which
    ):
        mock_which.side_effect = self._which_returns_qmd
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)

            mock_run.return_value = subprocess.CompletedProcess(
                args=["qmd", "collection", "list"],
                returncode=1,
                stdout="",
                stderr="error",
            )
            result = doctor(home=str(home))
            self.assertEqual(result, 1)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_output_contains_fix_command(self, mock_run, mock_which):
        mock_which.side_effect = self._which_returns_qmd
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            wiki_path = home.resolve() / "second-brain" / "wiki"

            mock_run.return_value = subprocess.CompletedProcess(
                args=["qmd", "collection", "list"],
                returncode=0,
                stdout="/other/collection\n",
                stderr="",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                doctor(home=str(home))
            output = buf.getvalue()
            self.assertIn("qmd collection add", output)
            self.assertIn(str(wiki_path), output)
            self.assertIn("--name second-brain", output)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_output_lists_agent_statuses(self, mock_run, mock_which):
        mock_which.side_effect = self._which_returns_qmd_and_agents
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")

            mock_run.return_value = subprocess.CompletedProcess(
                args=["qmd", "collection", "list"],
                returncode=0,
                stdout=f"  {wiki_path}\n",
                stderr="",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                doctor(home=str(home))
            output = buf.getvalue()

            self.assertIn("claude", output)
            self.assertIn("opencode", output)
            self.assertIn("codex", output)
            self.assertIn("hermes", output)
            self.assertIn("cursor", output)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_never_creates_files(self, mock_run, mock_which):
        mock_which.side_effect = self._which_returns_qmd_and_agents
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")

            mock_run.return_value = subprocess.CompletedProcess(
                args=["qmd", "collection", "list"],
                returncode=0,
                stdout=f"  {wiki_path}\n",
                stderr="",
            )

            before_files = set()
            for root, dirs, files in os.walk(home_str):
                for f in files:
                    before_files.add(os.path.join(root, f))

            doctor(home=str(home))

            after_files = set()
            for root, dirs, files in os.walk(home_str):
                for f in files:
                    after_files.add(os.path.join(root, f))

            new_files = after_files - before_files
            self.assertEqual(
                new_files, set(), f"doctor created files: {new_files}"
            )

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_returns_nonzero_for_invalid_settings_json(
        self, mock_run, mock_which
    ):
        mock_which.side_effect = self._which_returns_qmd_and_agents
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")

            mock_run.return_value = subprocess.CompletedProcess(
                args=["qmd", "collection", "list"],
                returncode=0,
                stdout=f"  {wiki_path}\n",
                stderr="",
            )

            settings = home / ".claude" / "settings.json"
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text("{not valid json", encoding="utf-8")

            result = doctor(home=str(home))
            self.assertEqual(result, 1)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_returns_nonzero_for_invalid_opencode_jsonc(
        self, mock_run, mock_which
    ):
        mock_which.side_effect = self._which_returns_qmd_and_agents
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")

            mock_run.return_value = subprocess.CompletedProcess(
                args=["qmd", "collection", "list"],
                returncode=0,
                stdout=f"  {wiki_path}\n",
                stderr="",
            )

            opencode_dir = home / ".config" / "opencode"
            opencode_dir.mkdir(parents=True, exist_ok=True)
            (opencode_dir / "opencode.jsonc").write_text(
                "{not valid jsonc", encoding="utf-8"
            )

            result = doctor(home=str(home))
            self.assertEqual(result, 1)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_returns_nonzero_for_invalid_config_toml(
        self, mock_run, mock_which
    ):
        mock_which.side_effect = self._which_returns_qmd_and_agents
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")

            mock_run.return_value = subprocess.CompletedProcess(
                args=["qmd", "collection", "list"],
                returncode=0,
                stdout=f"  {wiki_path}\n",
                stderr="",
            )

            codex_dir = home / ".codex"
            codex_dir.mkdir(parents=True, exist_ok=True)
            (codex_dir / "config.toml").write_text(
                "[[[invalid toml", encoding="utf-8"
            )

            result = doctor(home=str(home))
            self.assertEqual(result, 1)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_warns_when_obsidian_missing(self, mock_run, mock_which):
        mock_which.side_effect = self._which_returns_qmd
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")

            mock_run.return_value = subprocess.CompletedProcess(
                args=["qmd", "collection", "list"],
                returncode=0,
                stdout=f"  {wiki_path}\n",
                stderr="",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = doctor(home=str(home))
            output = buf.getvalue()

            self.assertEqual(result, 0)
            self.assertIn("obsidian not found", output)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_notes_when_memory_compiler_unconfigured(
        self, mock_run, mock_which
    ):
        mock_which.side_effect = self._which_returns_qmd
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")

            mock_run.return_value = subprocess.CompletedProcess(
                args=["qmd", "collection", "list"],
                returncode=0,
                stdout=f"  {wiki_path}\n",
                stderr="",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = doctor(home=str(home))
            output = buf.getvalue()

            self.assertEqual(result, 0)
            self.assertIn("memory compiler", output)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_warns_missing_agent_binaries_but_returns_zero(
        self, mock_run, mock_which
    ):
        mock_which.side_effect = self._which_returns_qmd
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")

            mock_run.return_value = subprocess.CompletedProcess(
                args=["qmd", "collection", "list"],
                returncode=0,
                stdout=f"  {wiki_path}\n",
                stderr="",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = doctor(home=str(home))
            output = buf.getvalue()

            self.assertEqual(result, 0)
            self.assertIn("not found (Claude Code)", output)
            self.assertIn("not found (OpenCode)", output)
            self.assertIn("not found (Codex CLI)", output)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_returns_zero_when_opencode_has_legacy_mcpServers(
        self, mock_run, mock_which
    ):
        mock_which.side_effect = self._which_returns_qmd_and_agents
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")

            mock_run.return_value = subprocess.CompletedProcess(
                args=["qmd", "collection", "list"],
                returncode=0,
                stdout=f"  {wiki_path}\n",
                stderr="",
            )

            opencode_path = home / ".config" / "opencode" / "opencode.jsonc"
            legacy_config = {
                "$schema": "https://opencode.ai/opencode.json",
                "mcpServers": {
                    "qmd": {
                        "type": "stdio",
                        "command": "qmd",
                        "args": ["mcp"],
                    }
                },
            }
            opencode_path.write_text(json.dumps(legacy_config), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = doctor(home=str(home))
            output = buf.getvalue()

            self.assertEqual(result, 0)
            self.assertIn("legacy mcpServers.qmd found", output)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_warns_when_opencode_mcp_not_object(
        self, mock_run, mock_which
    ):
        mock_which.side_effect = self._which_returns_qmd_and_agents
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")

            mock_run.return_value = subprocess.CompletedProcess(
                args=["qmd", "collection", "list"],
                returncode=0,
                stdout=f"  {wiki_path}\n",
                stderr="",
            )

            opencode_path = home / ".config" / "opencode" / "opencode.jsonc"
            config = ms.parse_jsonc(opencode_path.read_text(encoding="utf-8"))
            config["mcp"] = "not-a-dict"
            opencode_path.write_text(json.dumps(config), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = doctor(home=str(home))
            output = buf.getvalue()

            self.assertEqual(result, 0)
            self.assertIn("mcp is not an object", output)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_warns_when_opencode_has_custom_qmd(
        self, mock_run, mock_which
    ):
        mock_which.side_effect = self._which_returns_qmd_and_agents
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")

            mock_run.return_value = subprocess.CompletedProcess(
                args=["qmd", "collection", "list"],
                returncode=0,
                stdout=f"  {wiki_path}\n",
                stderr="",
            )

            opencode_path = home / ".config" / "opencode" / "opencode.jsonc"
            config = ms.parse_jsonc(opencode_path.read_text(encoding="utf-8"))
            config.setdefault("mcp", {})["qmd"] = {
                "type": "local",
                "command": "my-own-qmd",
                "args": ["mcp"],
                "enabled": True,
            }
            opencode_path.write_text(json.dumps(config), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = doctor(home=str(home))
            output = buf.getvalue()

            self.assertEqual(result, 0)
            self.assertIn("qmd MCP is custom", output)


class SecondBrainDiffTests(unittest.TestCase):
    """Tests for diff_kit command."""

    def test_diff_returns_zero_when_no_changes_needed(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            result = diff_kit(home=str(home))
            self.assertEqual(result, 0)

    def test_diff_opencode_qmd_already_present(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = diff_kit(home=str(home))
            output = buf.getvalue()
            self.assertEqual(result, 0)
            self.assertIn("opencode.jsonc: qmd MCP already present", output)

    def test_diff_opencode_would_add_qmd_mcp(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            opencode_path = home / ".config" / "opencode" / "opencode.jsonc"
            config = ms.parse_jsonc(opencode_path.read_text(encoding="utf-8"))
            config.pop("mcp", None)
            config.pop("mcpServers", None)
            opencode_path.write_text(json.dumps(config), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = diff_kit(home=str(home))
            output = buf.getvalue()
            self.assertEqual(result, 0)
            self.assertIn("opencode.jsonc: would add qmd MCP", output)

    def test_diff_opencode_legacy_mcpServers_shows_migration(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            opencode_path = home / ".config" / "opencode" / "opencode.jsonc"
            legacy_config = {
                "$schema": "https://opencode.ai/opencode.json",
                "mcpServers": {
                    "qmd": {
                        "type": "stdio",
                        "command": "qmd",
                        "args": ["mcp"],
                    }
                },
            }
            opencode_path.write_text(json.dumps(legacy_config), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = diff_kit(home=str(home))
            output = buf.getvalue()
            self.assertEqual(result, 0)
            self.assertIn("would migrate legacy", output)

    def test_diff_opencode_mcp_not_object_shows_warning(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            opencode_path = home / ".config" / "opencode" / "opencode.jsonc"
            config = ms.parse_jsonc(opencode_path.read_text(encoding="utf-8"))
            config["mcp"] = "not-a-dict"
            opencode_path.write_text(json.dumps(config), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = diff_kit(home=str(home))
            output = buf.getvalue()
            self.assertEqual(result, 0)
            self.assertIn("mcp is not an object", output)

    def test_diff_opencode_custom_qmd_not_overwritten(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            opencode_path = home / ".config" / "opencode" / "opencode.jsonc"
            config = ms.parse_jsonc(opencode_path.read_text(encoding="utf-8"))
            config.setdefault("mcp", {})["qmd"] = {
                "type": "local",
                "command": "my-own-qmd",
                "args": ["mcp"],
                "enabled": True,
            }
            opencode_path.write_text(json.dumps(config), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = diff_kit(home=str(home))
            output = buf.getvalue()
            self.assertEqual(result, 0)
            self.assertIn("custom; not overwritten", output)

    def test_diff_opencode_absent_config_shows_create_message(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            vault = home / "second-brain"
            for d in [
                "raw/assets", "inbox", "wiki/sources/learning",
                "wiki/sources/journal", "wiki/entities/projects",
                "wiki/concepts/backend", "wiki/concepts/ai-engineering",
                "wiki/concepts/pkm", "wiki/concepts/personal",
                "wiki/synthesis", "output", ".claude",
            ]:
                (vault / d).mkdir(parents=True, exist_ok=True)
            (vault / ".gitignore").write_text("", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = diff_kit(home=str(home))
            output = buf.getvalue()
            self.assertEqual(result, 0)
            self.assertIn("opencode.jsonc: would create with qmd MCP", output)


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

    def test_uninstall_removes_kit_owned_mcp_qmd_preserves_mcp_other(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            config_path = home / ".config" / "opencode" / "opencode.jsonc"
            config = ms.parse_jsonc(config_path.read_text(encoding="utf-8"))
            config.setdefault("mcp", {})["other"] = {"command": "keep-me"}
            config_path.write_text(json.dumps(config), encoding="utf-8")

            uninstall(home=str(home), dry_run=False, yes=True)

            result = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertNotIn("qmd", result.get("mcp", {}))
            self.assertEqual(result["mcp"]["other"], {"command": "keep-me"})

    def test_uninstall_removes_legacy_mcpservers_qmd_preserves_mcpservers_other(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            config_path = home / ".config" / "opencode" / "opencode.jsonc"
            config = ms.parse_jsonc(config_path.read_text(encoding="utf-8"))
            config["mcpServers"] = {
                "qmd": {"type": "stdio", "command": "qmd", "args": ["mcp"]},
                "other": {"command": "keep-me"},
            }
            config_path.write_text(json.dumps(config), encoding="utf-8")

            uninstall(home=str(home), dry_run=False, yes=True)

            result = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertNotIn("qmd", result.get("mcpServers", {}))
            self.assertEqual(result["mcpServers"]["other"], {"command": "keep-me"})

    def test_uninstall_removes_both_new_and_legacy_kit_owned(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            config_path = home / ".config" / "opencode" / "opencode.jsonc"
            config = ms.parse_jsonc(config_path.read_text(encoding="utf-8"))
            config["mcpServers"] = {
                "qmd": {"type": "stdio", "command": "qmd", "args": ["mcp"]},
            }
            config_path.write_text(json.dumps(config), encoding="utf-8")

            uninstall(home=str(home), dry_run=False, yes=True)

            result = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertNotIn("qmd", result.get("mcp", {}))
            self.assertNotIn("mcpServers", result)

    def test_uninstall_preserves_custom_mcp_qmd_with_enabled_false(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            config_path = home / ".config" / "opencode" / "opencode.jsonc"
            custom = {"type": "local", "command": "qmd", "args": ["mcp"], "enabled": False}
            config = ms.parse_jsonc(config_path.read_text(encoding="utf-8"))
            config.setdefault("mcp", {})["qmd"] = custom
            config_path.write_text(json.dumps(config), encoding="utf-8")

            uninstall(home=str(home), dry_run=False, yes=True)

            result = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(result["mcp"]["qmd"], custom)

    def test_uninstall_preserves_nonmatching_mcpservers_qmd(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True)
            config_path = home / ".config" / "opencode" / "opencode.jsonc"
            config = ms.parse_jsonc(config_path.read_text(encoding="utf-8"))
            config["mcpServers"] = {
                "qmd": {"command": "my-own", "args": ["mcp"]},
            }
            config_path.write_text(json.dumps(config), encoding="utf-8")

            uninstall(home=str(home), dry_run=False, yes=True)

            result = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(result["mcpServers"]["qmd"]["command"], "my-own")


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


class SecondBrainOpenCodeMcpTests(unittest.TestCase):
    """_merge_opencode_qmd_mcp and helper matchers."""

    # -- _is_legacy_kit_owned_qmd_mcp tests --

    def test_legacy_matcher_matches_claude_format(self):
        entry = {"type": "stdio", "command": "qmd", "args": ["mcp"]}
        self.assertTrue(_is_legacy_kit_owned_qmd_mcp(entry))

    def test_legacy_matcher_matches_opencode_format(self):
        entry = {"type": "local", "command": "qmd", "args": ["mcp"], "enabled": True}
        self.assertTrue(_is_legacy_kit_owned_qmd_mcp(entry))

    def test_legacy_matcher_rejects_non_dict(self):
        self.assertFalse(_is_legacy_kit_owned_qmd_mcp("string"))

    def test_legacy_matcher_rejects_wrong_command(self):
        self.assertFalse(
            _is_legacy_kit_owned_qmd_mcp({"command": "other", "args": ["mcp"]})
        )

    def test_legacy_matcher_rejects_non_bool_enabled(self):
        entry = {"command": "qmd", "args": ["mcp"], "enabled": "yes"}
        self.assertFalse(_is_legacy_kit_owned_qmd_mcp(entry))

    # -- _is_expected_opencode_qmd_mcp tests --

    def test_expected_matcher_matches_exact(self):
        self.assertTrue(_is_expected_opencode_qmd_mcp(OPENCODE_QMD_MCP_ENTRY))

    def test_expected_matcher_rejects_enabled_false(self):
        entry = {"type": "local", "command": "qmd", "args": ["mcp"], "enabled": False}
        self.assertFalse(_is_expected_opencode_qmd_mcp(entry))

    def test_expected_matcher_rejects_extra_keys(self):
        entry = dict(OPENCODE_QMD_MCP_ENTRY)
        entry["extra"] = True
        self.assertFalse(_is_expected_opencode_qmd_mcp(entry))

    def test_expected_matcher_rejects_missing_enabled(self):
        entry = {"type": "local", "command": "qmd", "args": ["mcp"]}
        self.assertFalse(_is_expected_opencode_qmd_mcp(entry))

    # -- _merge_opencode_qmd_mcp tests --

    def test_adds_mcp_qmd_when_absent(self):
        current = {"model": "sonnet"}
        merged, changed, warnings = _merge_opencode_qmd_mcp(current)
        self.assertTrue(changed)
        self.assertEqual(merged["mcp"]["qmd"], OPENCODE_QMD_MCP_ENTRY)
        self.assertEqual(merged["model"], "sonnet")
        self.assertEqual(warnings, [])

    def test_existing_other_keys_and_mcp_servers_survive(self):
        current = {
            "model": "sonnet",
            "mcp": {"other": {"command": "something"}},
        }
        merged, changed, warnings = _merge_opencode_qmd_mcp(current)
        self.assertTrue(changed)
        self.assertEqual(merged["mcp"]["qmd"], OPENCODE_QMD_MCP_ENTRY)
        self.assertEqual(merged["mcp"]["other"], {"command": "something"})
        self.assertEqual(merged["model"], "sonnet")
        self.assertEqual(warnings, [])

    def test_custom_mcp_qmd_preserved(self):
        custom = {"type": "local", "command": "qmd", "args": ["mcp"], "enabled": False}
        current = {"mcp": {"qmd": custom}}
        merged, changed, warnings = _merge_opencode_qmd_mcp(current)
        self.assertFalse(changed)
        self.assertIs(merged["mcp"]["qmd"], custom)
        self.assertIn("qmd MCP present (custom; not overwritten)", warnings)

    def test_legacy_mcp_servers_qmd_removed(self):
        current = {
            "mcpServers": {
                "qmd": {"type": "stdio", "command": "qmd", "args": ["mcp"]},
                "other": {"command": "something"},
            }
        }
        merged, changed, warnings = _merge_opencode_qmd_mcp(current)
        self.assertTrue(changed)
        self.assertNotIn("qmd", merged.get("mcpServers", {}))
        self.assertEqual(merged["mcpServers"]["other"], {"command": "something"})
        self.assertEqual(warnings, [])

    def test_empty_mcp_servers_removed_after_legacy_cleanup(self):
        current = {
            "mcpServers": {
                "qmd": {"type": "stdio", "command": "qmd", "args": ["mcp"]},
            }
        }
        merged, changed, warnings = _merge_opencode_qmd_mcp(current)
        self.assertTrue(changed)
        self.assertNotIn("mcpServers", merged)
        self.assertEqual(warnings, [])

    def test_non_object_root_unchanged(self):
        current = "not a dict"
        merged, changed, warnings = _merge_opencode_qmd_mcp(current)
        self.assertFalse(changed)
        self.assertIs(merged, current)
        self.assertIn("opencode.jsonc root is not an object", warnings)

    def test_non_object_mcp_unchanged(self):
        current = {"mcp": "not a dict"}
        merged, changed, warnings = _merge_opencode_qmd_mcp(current)
        self.assertFalse(changed)
        self.assertIs(merged, current)
        self.assertIn("existing mcp is not an object", warnings)

    def test_enabled_false_treated_as_custom_not_kit_owned(self):
        custom = {"type": "local", "command": "qmd", "args": ["mcp"], "enabled": False}
        self.assertFalse(_is_expected_opencode_qmd_mcp(custom))
        merged, changed, warnings = _merge_opencode_qmd_mcp({"mcp": {"qmd": custom}})
        self.assertFalse(changed)
        self.assertIn("qmd MCP present (custom; not overwritten)", warnings)

    def test_install_creates_mcp_qmd_from_empty(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            config_path = home / ".config" / "opencode" / "opencode.jsonc"
            self.assertTrue(config_path.exists())
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(config["mcp"]["qmd"], OPENCODE_QMD_MCP_ENTRY)
            self.assertNotIn("mcpServers", config)

    def test_install_preserves_existing_mcp_other_and_top_keys(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)

            seed = {
                "model": "sonnet",
                "mcp": {"other": {"command": "something"}},
            }
            config_dir = home / ".config" / "opencode"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "opencode.jsonc").write_text(
                json.dumps(seed), encoding="utf-8"
            )

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            config = json.loads(
                (config_dir / "opencode.jsonc").read_text(encoding="utf-8")
            )
            self.assertEqual(config["mcp"]["qmd"], OPENCODE_QMD_MCP_ENTRY)
            self.assertEqual(config["mcp"]["other"], {"command": "something"})
            self.assertEqual(config["model"], "sonnet")

    def test_install_removes_legacy_mcp_servers_qmd(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)

            seed = {
                "mcpServers": {
                    "qmd": {"type": "stdio", "command": "qmd", "args": ["mcp"]},
                    "other": {"command": "something"},
                }
            }
            config_dir = home / ".config" / "opencode"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "opencode.jsonc").write_text(
                json.dumps(seed), encoding="utf-8"
            )

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            config = json.loads(
                (config_dir / "opencode.jsonc").read_text(encoding="utf-8")
            )
            self.assertNotIn("qmd", config.get("mcpServers", {}))
            self.assertEqual(config["mcpServers"]["other"], {"command": "something"})
            self.assertEqual(config["mcp"]["qmd"], OPENCODE_QMD_MCP_ENTRY)

    def test_install_skips_invalid_jsonc(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)

            config_dir = home / ".config" / "opencode"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "opencode.jsonc"
            config_path.write_text("{not valid jsonc", encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            output = buf.getvalue()

            self.assertIn("invalid opencode.jsonc", output)
            self.assertEqual(
                config_path.read_text(encoding="utf-8"), "{not valid jsonc"
            )

    def test_install_rejects_non_object_root_before_writes(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)

            config_dir = home / ".config" / "opencode"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "opencode.jsonc"
            config_path.write_text(json.dumps("just a string"), encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            output = buf.getvalue()

            self.assertEqual(rc, 1)
            self.assertIn("invalid opencode.jsonc: root is not an object", output)
            self.assertFalse((home / "second-brain").exists())
            self.assertEqual(
                config_path.read_text(encoding="utf-8"), json.dumps("just a string")
            )

    def test_install_skips_non_object_mcp(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)

            config_dir = home / ".config" / "opencode"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "opencode.jsonc"
            config_path.write_text(
                json.dumps({"mcp": "not a dict"}), encoding="utf-8"
            )

            buf = io.StringIO()
            with redirect_stdout(buf):
                install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            output = buf.getvalue()

            self.assertIn("existing mcp is not an object", output)
            self.assertEqual(
                config_path.read_text(encoding="utf-8"),
                json.dumps({"mcp": "not a dict"}),
            )

    def test_install_returns_1_for_invalid_opencode_jsonc(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)

            config_dir = home / ".config" / "opencode"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "opencode.jsonc"
            config_path.write_text("{not valid jsonc", encoding="utf-8")

            result = install(
                home=str(home), dry_run=False, yes=True, setup_deps=False
            )

            self.assertEqual(result, 1)
            self.assertEqual(
                config_path.read_text(encoding="utf-8"), "{not valid jsonc"
            )

    def test_install_preserves_non_qmd_mcpservers_with_matching_shape(self):
        """Non-qmd key with same shape as legacy qmd MCP survives install."""
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)

            seed = {
                "mcpServers": {
                    "qmd_alias": {
                        "type": "stdio",
                        "command": "qmd",
                        "args": ["mcp"],
                    },
                }
            }
            config_dir = home / ".config" / "opencode"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "opencode.jsonc").write_text(
                json.dumps(seed), encoding="utf-8"
            )

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            config = json.loads(
                (config_dir / "opencode.jsonc").read_text(encoding="utf-8")
            )
            # Non-qmd key with matching shape must survive
            self.assertIn("qmd_alias", config.get("mcpServers", {}))
            self.assertEqual(
                config["mcpServers"]["qmd_alias"],
                {"type": "stdio", "command": "qmd", "args": ["mcp"]},
            )
            # qmd MCP must be added in new location
            self.assertEqual(
                config["mcp"]["qmd"], OPENCODE_QMD_MCP_ENTRY
            )

    def test_diff_opencode_non_object_root_does_not_crash(self):
        """diff_kit handles non-object opencode.jsonc root gracefully."""
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            opencode_path = (
                home / ".config" / "opencode" / "opencode.jsonc"
            )
            opencode_path.write_text(
                json.dumps("not-an-object"), encoding="utf-8"
            )

            buf = io.StringIO()
            with redirect_stdout(buf):
                diff_kit(home=str(home))
            output = buf.getvalue()

            self.assertIn("root is not an object", output)


class SecondBrainCursorMcpTests(unittest.TestCase):
    """_merge_cursor_config wires qmd MCP into ~/.cursor/mcp.json, matching Claude's pattern."""

    def test_install_merges_qmd_mcp_into_cursor_config(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            mcp_path = home / ".cursor" / "mcp.json"
            self.assertTrue(mcp_path.exists())
            config = json.loads(mcp_path.read_text(encoding="utf-8"))
            self.assertEqual(
                config["mcpServers"]["qmd"], QMD_MCP_SNIPPET_JSON["mcpServers"]["qmd"]
            )

    def test_install_preserves_existing_cursor_mcp_entries(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            cursor_dir = home / ".cursor"
            cursor_dir.mkdir(parents=True, exist_ok=True)
            preexisting = {"mcpServers": {"other": {"command": "keep-me"}}}
            (cursor_dir / "mcp.json").write_text(
                json.dumps(preexisting), encoding="utf-8"
            )

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            config = json.loads((cursor_dir / "mcp.json").read_text(encoding="utf-8"))
            self.assertEqual(config["mcpServers"]["other"], {"command": "keep-me"})
            self.assertEqual(
                config["mcpServers"]["qmd"], QMD_MCP_SNIPPET_JSON["mcpServers"]["qmd"]
            )

    def test_install_does_not_overwrite_custom_cursor_qmd_entry(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            cursor_dir = home / ".cursor"
            cursor_dir.mkdir(parents=True, exist_ok=True)
            custom = {"command": "my-own-qmd", "args": ["mcp"]}
            (cursor_dir / "mcp.json").write_text(
                json.dumps({"mcpServers": {"qmd": custom}}), encoding="utf-8"
            )

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            config = json.loads((cursor_dir / "mcp.json").read_text(encoding="utf-8"))
            self.assertEqual(config["mcpServers"]["qmd"], custom)

    def test_install_skips_invalid_cursor_mcp_json(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            cursor_dir = home / ".cursor"
            cursor_dir.mkdir(parents=True, exist_ok=True)
            (cursor_dir / "mcp.json").write_text("{not valid json", encoding="utf-8")

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            self.assertEqual(
                (cursor_dir / "mcp.json").read_text(encoding="utf-8"), "{not valid json"
            )

    def test_merge_cursor_config_direct_call_creates_file(self):
        with tempfile.TemporaryDirectory() as home_str:
            paths = _paths(home=home_str)
            _merge_cursor_config(paths)
            mcp_path = paths.cursor_dir / "mcp.json"
            self.assertTrue(mcp_path.exists())
            config = json.loads(mcp_path.read_text(encoding="utf-8"))
            self.assertEqual(
                config["mcpServers"]["qmd"], QMD_MCP_SNIPPET_JSON["mcpServers"]["qmd"]
            )

    def test_uninstall_removes_cursor_qmd_mcp_preserves_other(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            mcp_path = home / ".cursor" / "mcp.json"
            config = json.loads(mcp_path.read_text(encoding="utf-8"))
            config["mcpServers"]["other"] = {"command": "keep-me"}
            mcp_path.write_text(json.dumps(config), encoding="utf-8")

            uninstall(home=str(home), dry_run=False, yes=True)

            result = json.loads(mcp_path.read_text(encoding="utf-8"))
            self.assertNotIn("qmd", result.get("mcpServers", {}))
            self.assertEqual(result["mcpServers"]["other"], {"command": "keep-me"})

    def test_uninstall_removes_qmd_entry_matching_claude_behavior(self):
        """uninstall's shared _strip_qmd_mcp removes any qmd entry regardless of
        shape, matching Claude's existing (shape-agnostic) uninstall behavior."""
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            mcp_path = home / ".cursor" / "mcp.json"
            config = json.loads(mcp_path.read_text(encoding="utf-8"))
            config["mcpServers"]["qmd"] = {"command": "my-own", "args": ["mcp"]}
            mcp_path.write_text(json.dumps(config), encoding="utf-8")

            uninstall(home=str(home), dry_run=False, yes=True)

            result = json.loads(mcp_path.read_text(encoding="utf-8"))
            self.assertNotIn("qmd", result.get("mcpServers", {}))

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_reports_cursor_qmd_mcp_registered(self, mock_run, mock_which):
        def _which(cmd):
            return f"/fake/{cmd}" if cmd in ("qmd", "git") else None

        mock_which.side_effect = _which
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")
            mock_run.return_value = subprocess.CompletedProcess([], 0, f"  {wiki_path}\n", "")
            buf = io.StringIO()
            with redirect_stdout(buf):
                doctor(home=str(home))
            output = buf.getvalue()
            self.assertIn("qmd MCP", output)
            self.assertIn("Cursor", output)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_reports_cursor_qmd_mcp_absent(self, mock_run, mock_which):
        def _which(cmd):
            return f"/fake/{cmd}" if cmd in ("qmd", "git") else None

        mock_which.side_effect = _which
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(
                home=str(home),
                dry_run=False,
                yes=True,
                setup_deps=False,
                merge_settings=False,
            )
            wiki_path = str(home.resolve() / "second-brain" / "wiki")
            mock_run.return_value = subprocess.CompletedProcess([], 0, f"  {wiki_path}\n", "")
            buf = io.StringIO()
            with redirect_stdout(buf):
                doctor(home=str(home))
            output = buf.getvalue()
            self.assertIn("qmd MCP", output)

    def test_diff_reports_cursor_mcp_would_merge_on_fresh_install(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            vault = home / "second-brain"
            for d in VAULT_DIRS:
                (vault / d).mkdir(parents=True, exist_ok=True)
            (vault / ".gitignore").write_text("", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                install(home=str(home), dry_run=True, yes=True)
            output = buf.getvalue()
            self.assertIn("Claude, OpenCode, Codex, Cursor", output)


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


class SecondBrainVaultConflictTests(unittest.TestCase):
    """Vault conflict detection: warn on foreign vault, silent on our vault."""

    def test_install_warns_on_existing_foreign_vault(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            vault = home / "second-brain"
            vault.mkdir(parents=True, exist_ok=True)
            (vault / "my-notes.md").write_text("user content", encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            output = buf.getvalue()

            self.assertEqual(rc, 0)
            self.assertIn("already contains files", output)
            self.assertIn("VIBE_SECOND_BRAIN_PATH", output)

    def test_install_silent_on_manifest_vault(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            output = buf.getvalue()

            self.assertEqual(rc, 0)
            self.assertNotIn("already contains files", output)

    def test_install_yes_bypasses_vault_prompt(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            vault = home / "second-brain"
            vault.mkdir(parents=True, exist_ok=True)
            (vault / "user-file.md").write_text("content", encoding="utf-8")

            with patch("agents.kits.second_brain.installer._confirm") as mock_confirm:
                rc = install(home=str(home), dry_run=False, yes=True, setup_deps=False)
                mock_confirm.assert_not_called()

            self.assertEqual(rc, 0)

    def test_install_empty_existing_dir_no_warning(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            vault = home / "second-brain"
            vault.mkdir(parents=True, exist_ok=True)

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            output = buf.getvalue()

            self.assertEqual(rc, 0)
            self.assertNotIn("already contains files", output)


class SecondBrainDoctorDepTests(unittest.TestCase):
    """Doctor prerequisite dependency checks."""

    @patch("agents.kits.second_brain.installer.shutil.which")
    def test_doctor_fails_on_missing_git(self, mock_which):
        mock_which.return_value = None
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = doctor(home=str(home))
            output = buf.getvalue()
            self.assertEqual(result, 1)
            self.assertIn("git", output)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_node_npm_not_checked_when_qmd_present(self, mock_run, mock_which):
        def _which(cmd):
            if cmd in ("git", "qmd"):
                return f"/fake/{cmd}"
            return None

        mock_which.side_effect = _which
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")
            mock_run.return_value = subprocess.CompletedProcess(
                [], 0, f"  {wiki_path}\n", ""
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = doctor(home=str(home))
            output = buf.getvalue()
            self.assertEqual(result, 0)
            self.assertNotIn("node:", output)
            self.assertNotIn("npm:", output)

    @patch("agents.kits.second_brain.installer.shutil.which")
    def test_doctor_fails_on_missing_node_when_qmd_absent(self, mock_which):
        def _which(cmd):
            if cmd == "git":
                return "/usr/bin/git"
            return None

        mock_which.side_effect = _which
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = doctor(home=str(home))
            output = buf.getvalue()
            self.assertEqual(result, 1)
            self.assertIn("node", output)

    @patch("agents.kits.second_brain.installer.subprocess.run")
    @patch("agents.kits.second_brain.installer.shutil.which")
    def test_doctor_fails_on_node_20_when_qmd_is_absent(self, mock_which, mock_run):
        def _which(cmd):
            if cmd in ("git", "node", "npm"):
                return f"/fake/{cmd}"
            return None

        mock_which.side_effect = _which

        def _run(cmd, **kw):
            if "node" in cmd:
                return subprocess.CompletedProcess(cmd, 0, "v20.19.0\n", "")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        mock_run.side_effect = _run
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = doctor(home=str(home))
            output = buf.getvalue()
            self.assertEqual(result, 1)
            self.assertIn("node: major version 20 < 22", output)

    @patch("agents.kits.second_brain.installer.subprocess.run")
    @patch("agents.kits.second_brain.installer.shutil.which")
    def test_doctor_surfaces_qmd_runtime_cpu_warning_without_failing(self, mock_which, mock_run):
        mock_which.side_effect = lambda cmd: f"/fake/{cmd}" if cmd in {"git", "qmd"} else None

        with tempfile.TemporaryDirectory() as home_str:
            install(home=home_str, dry_run=False, yes=True, setup_deps=False)
            wiki_path = str(Path(home_str) / "second-brain" / "wiki")

            def _run(cmd, **kwargs):
                if cmd == ["qmd", "collection", "show", "second-brain"]:
                    return subprocess.CompletedProcess(cmd, 0, f"Path: {wiki_path}\n", "")
                self.assertEqual(cmd, ["qmd", "doctor"])
                return subprocess.CompletedProcess(cmd, 0, "⚠ device probe: running on CPU\n", "")

            mock_run.side_effect = _run
            output = io.StringIO()
            with redirect_stdout(output):
                result = doctor(home=home_str)

        self.assertEqual(result, 0)
        self.assertIn("-- qmd runtime --", output.getvalue())
        self.assertIn("running on CPU", output.getvalue())

    @patch("agents.kits.second_brain.installer.subprocess.run")
    @patch("agents.kits.second_brain.installer.shutil.which")
    def test_doctor_warns_when_qmd_runtime_probe_fails_without_failing(self, mock_which, mock_run):
        mock_which.side_effect = lambda cmd: f"/fake/{cmd}" if cmd in {"git", "qmd"} else None

        with tempfile.TemporaryDirectory() as home_str:
            install(home=home_str, dry_run=False, yes=True, setup_deps=False)
            wiki_path = str(Path(home_str) / "second-brain" / "wiki")

            def _run(cmd, **kwargs):
                if cmd == ["qmd", "collection", "show", "second-brain"]:
                    return subprocess.CompletedProcess(cmd, 0, f"Path: {wiki_path}\n", "")
                self.assertEqual(cmd, ["qmd", "doctor"])
                return subprocess.CompletedProcess(cmd, 1, "", "GPU probe unavailable")

            mock_run.side_effect = _run
            output = io.StringIO()
            with redirect_stdout(output):
                result = doctor(home=home_str)

        self.assertEqual(result, 0)
        self.assertIn("qmd runtime unavailable", output.getvalue())


class SecondBrainQmdAutoInstallTests(unittest.TestCase):
    """qmd auto-install behavior during install."""

    @patch("agents.kits.second_brain.installer._setup_qmd")
    def test_install_skips_qmd_when_setup_deps_false(self, mock_setup):
        with tempfile.TemporaryDirectory() as home_str:
            rc = install(home=home_str, dry_run=False, yes=True, setup_deps=False)
            self.assertEqual(rc, 0)
            mock_setup.assert_not_called()

    @patch("agents.kits.second_brain.installer._setup_qmd")
    def test_install_calls_setup_qmd_when_setup_deps_true(self, mock_setup):
        mock_setup.return_value = 0
        with tempfile.TemporaryDirectory() as home_str:
            rc = install(home=home_str, dry_run=False, yes=True, setup_deps=True)
            self.assertEqual(rc, 0)
            mock_setup.assert_called_once()

    @patch("agents.kits.second_brain.installer._setup_qmd", return_value=1)
    def test_install_returns_failure_when_qmd_setup_fails(self, mock_setup):
        with tempfile.TemporaryDirectory() as home_str:
            rc = install(home=home_str, dry_run=False, yes=True, setup_deps=True)
            manifest = Path(home_str) / "second-brain" / ".vibe-engineering-manifest.json"
            state = json.loads(manifest.read_text(encoding="utf-8"))

        self.assertEqual(rc, 1)
        mock_setup.assert_called_once()
        self.assertEqual(state["status"], "incomplete")
        self.assertEqual(state["phase"], "qmd")

    @patch("agents.kits.second_brain.installer.subprocess.run")
    @patch("agents.kits.second_brain.installer.shutil.which")
    def test_existing_qmd_registers_missing_collection_and_updates_index(
        self, mock_which, mock_run
    ):
        mock_which.side_effect = lambda cmd: "/fake/qmd" if cmd == "qmd" else None
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, "", ""),
        ]
        vault = Path("/tmp/second-brain")

        rc = _setup_qmd(vault, yes=True)

        self.assertEqual(rc, 0)
        self.assertEqual(
            [call.args[0] for call in mock_run.call_args_list],
            [
                ["qmd", "collection", "show", "second-brain"],
                ["qmd", "collection", "add", str(vault / "wiki"), "--name", "second-brain"],
                ["qmd", "update"],
            ],
        )

    @patch("agents.kits.second_brain.installer.subprocess.run")
    @patch("agents.kits.second_brain.installer.shutil.which")
    def test_existing_named_qmd_collection_is_detected_via_show(self, mock_which, mock_run):
        mock_which.side_effect = lambda cmd: "/fake/qmd" if cmd == "qmd" else None
        vault = Path("/tmp/second-brain")
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                [],
                0,
                f"Collection: second-brain\n  Path:     {vault / 'wiki'}\n",
                "",
            ),
            subprocess.CompletedProcess([], 0, "", ""),
        ]

        rc = _setup_qmd(vault, yes=True)

        self.assertEqual(rc, 0)
        self.assertEqual(
            [call.args[0] for call in mock_run.call_args_list],
            [["qmd", "collection", "show", "second-brain"], ["qmd", "update"]],
        )

    @patch("agents.kits.second_brain.installer.subprocess.run")
    @patch("agents.kits.second_brain.installer.shutil.which")
    def test_install_skips_npm_when_qmd_already_present(self, mock_which, mock_run):
        def _which(cmd):
            if cmd in ("git", "qmd"):
                return f"/fake/{cmd}"
            return None

        mock_which.side_effect = _which
        mock_run.return_value = subprocess.CompletedProcess([], 0, "", "")
        with tempfile.TemporaryDirectory() as home_str:
            rc = install(home=home_str, dry_run=False, yes=True, setup_deps=True)
            self.assertEqual(rc, 0)
            npm_calls = [
                c for c in mock_run.call_args_list
                if c[0][0][:2] == ["npm", "install"]
            ]
            self.assertEqual(npm_calls, [])

    @patch("agents.kits.second_brain.installer.subprocess.run")
    @patch("agents.kits.second_brain.installer.shutil.which")
    def test_setup_qmd_prompts_when_yes_false(self, mock_which, mock_run):
        def _which(cmd):
            if cmd in ("node", "npm"):
                return f"/fake/{cmd}"
            return None

        mock_which.side_effect = _which
        mock_run.return_value = subprocess.CompletedProcess([], 0, "v22.0.0\n", "")
        with tempfile.TemporaryDirectory() as home_str:
            with patch("agents.kits.second_brain.installer._confirm", return_value=False) as mock_confirm:
                _setup_qmd(Path(home_str) / "wiki", yes=False)
                mock_confirm.assert_called_once()

    @patch("agents.kits.second_brain.installer.subprocess.run")
    @patch("agents.kits.second_brain.installer.shutil.which")
    def test_install_yes_bypasses_npm_prompt(self, mock_which, mock_run):
        def _which(cmd):
            if cmd in ("git", "node", "npm"):
                return f"/fake/{cmd}"
            return None

        mock_which.side_effect = _which
        mock_run.return_value = subprocess.CompletedProcess([], 0, "v22.0.0\n", "")
        with tempfile.TemporaryDirectory() as home_str:
            with patch("agents.kits.second_brain.installer._confirm") as mock_confirm:
                rc = install(home=home_str, dry_run=False, yes=True, setup_deps=True)
            self.assertEqual(rc, 0)
            mock_confirm.assert_not_called()

    @patch("agents.kits.second_brain.installer.subprocess.run")
    @patch("agents.kits.second_brain.installer.shutil.which")
    def test_install_fails_when_qmd_and_npm_are_missing(self, mock_which, mock_run):
        def _which(cmd):
            if cmd == "git":
                return "/usr/bin/git"
            return None

        mock_which.side_effect = _which
        mock_run.return_value = subprocess.CompletedProcess([], 0, "", "")
        with tempfile.TemporaryDirectory() as home_str:
            rc = install(home=home_str, dry_run=False, yes=True, setup_deps=True)
            self.assertEqual(rc, 1)
            manifest = Path(home_str) / "second-brain" / ".vibe-engineering-manifest.json"
            state = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "incomplete")
            self.assertEqual(state["phase"], "qmd")

    @patch("agents.kits.second_brain.installer.subprocess.run")
    @patch("agents.kits.second_brain.installer.shutil.which")
    def test_setup_qmd_rejects_node_20_before_npm_install(self, mock_which, mock_run):
        mock_which.side_effect = lambda cmd: f"/fake/{cmd}" if cmd in {"node", "npm"} else None
        mock_run.return_value = subprocess.CompletedProcess([], 0, "v20.19.0\n", "")

        output = io.StringIO()
        with redirect_stdout(output):
            rc = _setup_qmd(Path("/tmp/second-brain"), yes=True)

        self.assertEqual(rc, 1)
        self.assertIn("Node.js 22+", output.getvalue())
        self.assertEqual(mock_run.call_args_list, [unittest.mock.call(["node", "--version"], capture_output=True, text=True, timeout=5)])


class SecondBrainIncompleteInstallDoctorTests(unittest.TestCase):
    def test_doctor_reports_incomplete_qmd_setup_with_resume_command(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=home_str, dry_run=False, yes=True, setup_deps=False)
            manifest = home / "second-brain" / ".vibe-engineering-manifest.json"
            state = json.loads(manifest.read_text(encoding="utf-8"))
            state.update({"status": "incomplete", "phase": "qmd"})
            manifest.write_text(json.dumps(state), encoding="utf-8")

            output = io.StringIO()
            with patch(
                "agents.kits.second_brain.installer.shutil.which",
                side_effect=lambda name: f"/fake/{name}" if name in {"git", "qmd"} else None,
            ), patch(
                "agents.kits.second_brain.installer.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, str(home / "second-brain" / "wiki"), ""),
            ), redirect_stdout(output):
                rc = doctor(home=home_str)

            self.assertEqual(rc, 1)
            self.assertIn("incomplete", output.getvalue())
            self.assertIn("vibe kits second-brain install --yes", output.getvalue())

    def test_install_without_settings_still_installs_hooks(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)

            rc = install(
                home=home_str,
                dry_run=False,
                yes=True,
                setup_deps=False,
                merge_settings=False,
                enable_hooks=True,
            )

            self.assertEqual(rc, 0)
            self.assertTrue((home / ".claude" / HOOK_SCRIPT_REL).is_file())
            settings = json.loads(
                (home / ".claude" / "settings.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("mcpServers", settings)
            self.assertIn("hooks", settings)

    def test_install_backs_up_existing_settings_before_merging(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            settings = home / ".claude" / "settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text('{"theme": "dark"}\n', encoding="utf-8")

            rc = install(
                home=home_str,
                dry_run=False,
                yes=True,
                setup_deps=False,
                enable_hooks=False,
            )

            self.assertEqual(rc, 0)
            backups = list((home / ".claude" / "backups").rglob("settings.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), '{"theme": "dark"}\n')

    def test_invalid_codex_toml_aborts_before_creating_vault(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            config = home / ".codex" / "config.toml"
            config.parent.mkdir(parents=True)
            config.write_text("broken = [\n", encoding="utf-8")

            rc = install(home=home_str, dry_run=False, yes=True, setup_deps=False)

            self.assertEqual(rc, 1)
            self.assertFalse((home / "second-brain").exists())


class SecondBrainSkillInstallTests(unittest.TestCase):
    """The kit ships a discoverable first-party second-brain skill."""

    WIKI_SKILL_NAMES = {
        "autoresearch",
        "canvas",
        "defuddle",
        "obsidian-bases",
        "obsidian-markdown",
        "save",
        "think",
        "wiki",
        "wiki-cli",
        "wiki-fold",
        "wiki-ingest",
        "wiki-lint",
        "wiki-mode",
        "wiki-query",
        "wiki-retrieve",
    }

    def test_skill_allows_hybrid_retrieval_but_keeps_bulk_indexing_explicit(self):
        skill = (
            Path(__file__).resolve().parent.parent
            / "agents/kits/second_brain/templates/second_brain/skills/second-brain/SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("may download local QMD models", skill)
        self.assertIn("Do not run `qmd pull` or `qmd embed` unless the user explicitly asks", skill)

    def test_install_copies_skill_to_agent_and_claude_locations(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            rc = install(home=home_str, dry_run=False, yes=True, setup_deps=False)

            self.assertEqual(rc, 0)
            for path in (
                home / ".agents" / "skills" / "second-brain" / "SKILL.md",
                home / ".claude" / "skills" / "second-brain" / "SKILL.md",
            ):
                self.assertTrue(path.is_file(), path)
                content = path.read_text(encoding="utf-8")
                self.assertIn("name: second-brain", content)
                self.assertIn("inbox/", content)

    def test_install_copies_portable_wiki_skill_suite_to_both_discovery_roots(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)

            rc = install(home=home_str, dry_run=False, yes=True, setup_deps=False)

            self.assertEqual(rc, 0)
            for root in (home / ".agents" / "skills", home / ".claude" / "skills"):
                installed = {
                    path.parent.name
                    for path in root.glob("*/SKILL.md")
                }
                self.assertTrue(self.WIKI_SKILL_NAMES <= installed)
                for name in self.WIKI_SKILL_NAMES:
                    content = (root / name / "SKILL.md").read_text(encoding="utf-8")
                    self.assertIn(f"name: {name}", content)

    def test_portable_wiki_skill_suite_uses_current_vault_contract(self):
        skills_root = (
            Path(__file__).resolve().parent.parent
            / "agents/kits/second_brain/templates/second_brain/skills"
        )
        for name in self.WIKI_SKILL_NAMES:
            content = (skills_root / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn(".raw/", content)
            self.assertNotIn(".vault-meta", content)
            self.assertNotIn("Ollama", content)
            self.assertNotIn("scripts/", content)

        notice = (skills_root / "NOTICE-claude-obsidian.md").read_text(encoding="utf-8")
        self.assertIn("MIT License", notice)
        self.assertIn("00213b720cdc9bb00ec8b3f88f9cc408721c37f9", notice)

    def test_dry_run_reports_skill_without_creating_it(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            output = io.StringIO()
            with redirect_stdout(output):
                rc = install(home=home_str, dry_run=True, yes=True, setup_deps=False)

            self.assertEqual(rc, 0)
            self.assertIn("second-brain skill", output.getvalue())
            self.assertFalse((home / ".agents" / "skills" / "second-brain" / "SKILL.md").exists())

    def test_reinstall_preserves_modified_skill(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=home_str, dry_run=False, yes=True, setup_deps=False)
            skill = home / ".agents" / "skills" / "second-brain" / "SKILL.md"
            skill.write_text("custom skill\n", encoding="utf-8")

            rc = install(home=home_str, dry_run=False, yes=True, setup_deps=False)

            self.assertEqual(rc, 0)
            self.assertEqual(skill.read_text(encoding="utf-8"), "custom skill\n")

    def test_uninstall_removes_unchanged_skill_files(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=home_str, dry_run=False, yes=True, setup_deps=False)

            rc = uninstall(home=home_str, dry_run=False, yes=True)

            self.assertEqual(rc, 0)
            self.assertFalse((home / ".agents" / "skills" / "second-brain" / "SKILL.md").exists())
            self.assertFalse((home / ".claude" / "skills" / "second-brain" / "SKILL.md").exists())
            for root in (home / ".agents" / "skills", home / ".claude" / "skills"):
                for name in self.WIKI_SKILL_NAMES:
                    self.assertFalse((root / name / "SKILL.md").exists())

    def test_uninstall_keeps_modified_skill_file(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=home_str, dry_run=False, yes=True, setup_deps=False)
            skill = home / ".agents" / "skills" / "second-brain" / "SKILL.md"
            skill.write_text("custom skill\n", encoding="utf-8")

            rc = uninstall(home=home_str, dry_run=False, yes=True)

            self.assertEqual(rc, 0)
            self.assertEqual(skill.read_text(encoding="utf-8"), "custom skill\n")

    def test_skill_defines_retrieve_capture_and_curation_flow(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=home_str, dry_run=False, yes=True, setup_deps=False)

            content = (
                home / ".agents" / "skills" / "second-brain" / "SKILL.md"
            ).read_text(encoding="utf-8")

            self.assertIn("Retrieve before re-deriving", content)
            self.assertIn("Capture durable outcomes automatically", content)
            self.assertIn("Curate only on request", content)


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


class SecondBrainSessionHookInstallTests(unittest.TestCase):
    """SessionStart hook script + settings.json registration during install()."""

    def test_install_writes_hook_script_and_registers_command(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            script_path = paths.claude_dir / HOOK_SCRIPT_REL
            self.assertTrue(script_path.is_file(), "hook script not installed")
            settings = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))
            commands = [
                h["command"]
                for g in settings["hooks"][SESSIONSTART_EVENT]
                for h in g["hooks"]
            ]
            self.assertIn(_hook_command(paths), commands)

    def test_install_idempotent_reinstall_no_duplicate_hook_entry(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            settings = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))
            commands = [
                h["command"]
                for g in settings["hooks"][SESSIONSTART_EVENT]
                for h in g["hooks"]
            ]
            self.assertEqual(commands.count(_hook_command(paths)), 1)

    def test_install_preserves_users_preexisting_sessionstart_hook(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            claude_dir = home / ".claude"
            claude_dir.mkdir(parents=True, exist_ok=True)
            other_command = 'node "/home/user/.claude/hooks/caveman-activate.js"'
            preexisting = {
                "hooks": {
                    SESSIONSTART_EVENT: [
                        {"hooks": [{"type": "command", "command": other_command, "timeout": 5}]}
                    ]
                }
            }
            (claude_dir / "settings.json").write_text(json.dumps(preexisting), encoding="utf-8")

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
            commands = [
                h["command"]
                for g in settings["hooks"][SESSIONSTART_EVENT]
                for h in g["hooks"]
            ]
            self.assertIn(other_command, commands)

    def test_install_preserves_unrelated_events_and_top_level_keys(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            claude_dir = home / ".claude"
            claude_dir.mkdir(parents=True, exist_ok=True)
            preexisting = {
                "model": "opus",
                "permissions": {"allow": ["Bash"]},
                "hooks": {"PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "other"}]}]},
            }
            (claude_dir / "settings.json").write_text(json.dumps(preexisting), encoding="utf-8")

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["model"], "opus")
            self.assertEqual(settings["permissions"], {"allow": ["Bash"]})
            self.assertEqual(settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"], "other")

    def test_dry_run_writes_no_hook_files_or_settings_changes(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=True, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            self.assertFalse((paths.claude_dir / HOOK_SCRIPT_REL).exists())
            self.assertFalse((paths.claude_dir / "settings.json").exists())

    def test_install_skips_hook_registration_on_invalid_settings_json(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            claude_dir = home / ".claude"
            claude_dir.mkdir(parents=True, exist_ok=True)
            (claude_dir / "settings.json").write_text("{not valid json", encoding="utf-8")

            result = install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            self.assertEqual(result, 1)
            self.assertEqual(
                (claude_dir / "settings.json").read_text(encoding="utf-8"), "{not valid json"
            )

    def test_hook_command_is_absolute_path_stable_across_reinstall(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            settings1 = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))
            cmd1 = settings1["hooks"][SESSIONSTART_EVENT][-1]["hooks"][0]["command"]

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            settings2 = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))
            cmd2 = settings2["hooks"][SESSIONSTART_EVENT][-1]["hooks"][0]["command"]

            self.assertEqual(cmd1, cmd2)
            self.assertIn(str(paths.claude_dir / HOOK_SCRIPT_REL), cmd1)


class SecondBrainClaudeMdSectionTests(unittest.TestCase):
    """~/.claude/CLAUDE.md marked-section merge during install()."""

    def test_install_creates_claude_md_with_section_when_absent(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            claude_md = (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn(CLAUDE_MD_BEGIN_MARKER, claude_md)
            self.assertIn(CLAUDE_MD_END_MARKER, claude_md)
            self.assertIn("Second-Brain Vault", claude_md)

    def test_install_merges_section_preserving_users_preexisting_content(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            claude_dir = home / ".claude"
            claude_dir.mkdir(parents=True, exist_ok=True)
            (claude_dir / "CLAUDE.md").write_text("# My Personal Rules\nBe terse.\n", encoding="utf-8")

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            claude_md = (claude_dir / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("# My Personal Rules", claude_md)
            self.assertIn("Be terse.", claude_md)
            self.assertIn(CLAUDE_MD_BEGIN_MARKER, claude_md)

    def test_install_idempotent_reinstall_no_duplicate_section(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            claude_md = (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertEqual(claude_md.count(CLAUDE_MD_BEGIN_MARKER), 1)
            self.assertEqual(claude_md.count(CLAUDE_MD_END_MARKER), 1)

    def test_install_updates_stale_section_on_reinstall(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            claude_dir = home / ".claude"
            claude_dir.mkdir(parents=True, exist_ok=True)
            stale = CLAUDE_MD_BEGIN_MARKER + "stale old content\n" + CLAUDE_MD_END_MARKER
            (claude_dir / "CLAUDE.md").write_text(stale, encoding="utf-8")

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            claude_md = (claude_dir / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertNotIn("stale old content", claude_md)
            self.assertIn("Second-Brain Vault", claude_md)

    def test_dry_run_writes_no_claude_md_changes(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=True, yes=True, setup_deps=False)
            self.assertFalse((home / ".claude" / "CLAUDE.md").exists())


class SecondBrainHookPromptTests(unittest.TestCase):
    """Interactive accept/decline behavior for the hook + CLAUDE.md offer."""

    def test_declines_skips_wiring_and_prints_hint(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            paths = _paths(home=str(home))
            paths.claude_dir.mkdir(parents=True, exist_ok=True)
            buf = io.StringIO()
            with patch("agents.kits.second_brain.installer._confirm", return_value=False):
                with redirect_stdout(buf):
                    from agents.kits.second_brain.installer import _offer_proactive_context
                    _offer_proactive_context(paths, yes=False)
            output = buf.getvalue()
            self.assertIn("enable-hook", output)
            self.assertFalse((paths.claude_dir / HOOK_SCRIPT_REL).exists())
            self.assertFalse((paths.claude_dir / "CLAUDE.md").exists())

    def test_accepts_enables_wiring(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            paths = _paths(home=str(home))
            paths.claude_dir.mkdir(parents=True, exist_ok=True)
            with patch("agents.kits.second_brain.installer._confirm", return_value=True):
                from agents.kits.second_brain.installer import _offer_proactive_context
                _offer_proactive_context(paths, yes=False)
            self.assertTrue((paths.claude_dir / HOOK_SCRIPT_REL).exists())
            self.assertTrue((paths.claude_dir / "CLAUDE.md").exists())

    def test_yes_bypasses_prompt_and_enables(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            paths = _paths(home=str(home))
            paths.claude_dir.mkdir(parents=True, exist_ok=True)
            with patch("agents.kits.second_brain.installer._confirm") as mock_confirm:
                from agents.kits.second_brain.installer import _offer_proactive_context
                _offer_proactive_context(paths, yes=True)
                mock_confirm.assert_not_called()
            self.assertTrue((paths.claude_dir / HOOK_SCRIPT_REL).exists())

    def test_already_installed_is_silent_no_prompt(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            with patch("agents.kits.second_brain.installer._confirm") as mock_confirm:
                from agents.kits.second_brain.installer import _offer_proactive_context
                _offer_proactive_context(paths, yes=False)
                mock_confirm.assert_not_called()

    def test_no_hooks_flag_skips_prompt_entirely(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            with patch("agents.kits.second_brain.installer.core.confirm", return_value=True):
                with patch("agents.kits.second_brain.installer._confirm") as mock_confirm:
                    install(home=str(home), dry_run=False, yes=False, setup_deps=False, enable_hooks=False)
                    mock_confirm.assert_not_called()
            paths = _paths(home=str(home))
            self.assertFalse((paths.claude_dir / HOOK_SCRIPT_REL).exists())

    def test_install_prints_fresh_vs_existing_state(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            buf = io.StringIO()
            with redirect_stdout(buf):
                install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            self.assertIn("fresh install", buf.getvalue())

            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            self.assertIn("existing installation detected", buf2.getvalue())


class SecondBrainEnableHookCommandTests(unittest.TestCase):
    """Standalone enable_hook() verb — independent of vault install."""

    def test_enable_hook_works_without_vault_installed(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            result = enable_hook(home=str(home), dry_run=False, yes=True)
            self.assertEqual(result, 0)
            paths = _paths(home=str(home))
            self.assertTrue((paths.claude_dir / HOOK_SCRIPT_REL).exists())
            self.assertTrue((paths.claude_dir / "CLAUDE.md").exists())

    def test_enable_hook_idempotent(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            enable_hook(home=str(home), dry_run=False, yes=True)
            enable_hook(home=str(home), dry_run=False, yes=True)
            paths = _paths(home=str(home))
            claude_md = (paths.claude_dir / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertEqual(claude_md.count(CLAUDE_MD_BEGIN_MARKER), 1)

    def test_enable_hook_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            result = enable_hook(home=str(home), dry_run=True, yes=True)
            self.assertEqual(result, 0)
            paths = _paths(home=str(home))
            self.assertFalse((paths.claude_dir / HOOK_SCRIPT_REL).exists())

    def test_enable_hook_respects_yes_false_decline(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            with patch("agents.kits.second_brain.installer._confirm", return_value=False):
                result = enable_hook(home=str(home), dry_run=False, yes=False)
            self.assertEqual(result, 0)
            paths = _paths(home=str(home))
            self.assertFalse((paths.claude_dir / HOOK_SCRIPT_REL).exists())


class SecondBrainUninstallProactiveWiringTests(unittest.TestCase):
    """uninstall() strips only kit-owned hook/CLAUDE.md wiring."""

    def test_uninstall_strips_only_kit_hook_command_from_settings_json(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            claude_dir = home / ".claude"
            claude_dir.mkdir(parents=True, exist_ok=True)
            other_command = 'node "/home/user/.claude/hooks/caveman-activate.js"'
            preexisting = {
                "hooks": {
                    SESSIONSTART_EVENT: [
                        {"hooks": [{"type": "command", "command": other_command}]}
                    ]
                }
            }
            (claude_dir / "settings.json").write_text(json.dumps(preexisting), encoding="utf-8")

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            uninstall(home=str(home), dry_run=False, yes=True)

            settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
            commands = [
                h["command"]
                for g in settings.get("hooks", {}).get(SESSIONSTART_EVENT, [])
                for h in g["hooks"]
            ]
            self.assertIn(other_command, commands)
            paths = _paths(home=str(home))
            self.assertNotIn(_hook_command(paths), commands)

    def test_uninstall_removes_hook_script_file(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            self.assertTrue((paths.claude_dir / HOOK_SCRIPT_REL).exists())

            uninstall(home=str(home), dry_run=False, yes=True)

            self.assertFalse((paths.claude_dir / HOOK_SCRIPT_REL).exists())

    def test_uninstall_strips_claude_md_section_preserves_user_content(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            claude_dir = home / ".claude"
            claude_dir.mkdir(parents=True, exist_ok=True)
            (claude_dir / "CLAUDE.md").write_text("# My Rules\nBe terse.\n", encoding="utf-8")

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            uninstall(home=str(home), dry_run=False, yes=True)

            claude_md = (claude_dir / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("# My Rules", claude_md)
            self.assertNotIn(CLAUDE_MD_BEGIN_MARKER, claude_md)
            self.assertNotIn("Second-Brain Vault", claude_md)

    def test_uninstall_deletes_claude_md_when_it_was_entirely_kit_content(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            claude_md_path = paths.claude_dir / "CLAUDE.md"
            self.assertTrue(claude_md_path.exists())

            uninstall(home=str(home), dry_run=False, yes=True)

            self.assertFalse(claude_md_path.exists())

    def test_uninstall_never_touches_vault_content_git_or_seed_pages(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            vault = home / "second-brain"
            user_file = vault / "wiki" / "entities" / "projects" / "note.md"
            user_file.parent.mkdir(parents=True, exist_ok=True)
            user_file.write_text("# note\n", encoding="utf-8")

            uninstall(home=str(home), dry_run=False, yes=True)

            self.assertTrue(vault.exists())
            self.assertTrue(user_file.exists())
            self.assertTrue((vault / ".git").is_dir())
            self.assertTrue((vault / "wiki" / "index.md").exists())

    def test_uninstall_dry_run_reports_without_modifying(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            hook_script = paths.claude_dir / HOOK_SCRIPT_REL
            claude_md = paths.claude_dir / "CLAUDE.md"
            before_hook = hook_script.read_bytes()
            before_claude_md = claude_md.read_bytes()

            uninstall(home=str(home), dry_run=True, yes=True)

            self.assertEqual(hook_script.read_bytes(), before_hook)
            self.assertEqual(claude_md.read_bytes(), before_claude_md)


class SecondBrainDoctorProactiveWiringTests(unittest.TestCase):
    """doctor() reports hook/CLAUDE.md state read-only."""

    def _which_returns_qmd(self, cmd):
        if cmd in ("qmd", "git"):
            return f"/fake/{cmd}"
        return None

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_reports_hook_present(self, mock_run, mock_which):
        mock_which.side_effect = self._which_returns_qmd
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")
            mock_run.return_value = subprocess.CompletedProcess([], 0, f"  {wiki_path}\n", "")
            buf = io.StringIO()
            with redirect_stdout(buf):
                doctor(home=str(home))
            output = buf.getvalue()
            self.assertIn("SessionStart hook script:", output)
            self.assertIn("SessionStart hook registered", output)
            self.assertIn("CLAUDE.md second-brain section present", output)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_reports_hook_absent_as_info_not_failure(self, mock_run, mock_which):
        mock_which.side_effect = self._which_returns_qmd
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            with patch("agents.kits.second_brain.installer.core.confirm", return_value=True):
                with patch("agents.kits.second_brain.installer._confirm", return_value=False):
                    install(home=str(home), dry_run=False, yes=False, setup_deps=False)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")
            mock_run.return_value = subprocess.CompletedProcess([], 0, f"  {wiki_path}\n", "")
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = doctor(home=str(home))
            output = buf.getvalue()
            self.assertEqual(result, 0)
            self.assertIn("not installed", output)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_never_executes_the_hook_script(self, mock_run, mock_which):
        mock_which.side_effect = self._which_returns_qmd
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")
            mock_run.return_value = subprocess.CompletedProcess([], 0, f"  {wiki_path}\n", "")
            doctor(home=str(home))
            for call in mock_run.call_args_list:
                args = call.args[0] if call.args else call.kwargs.get("args", [])
                self.assertNotIn(HOOK_SCRIPT_REL, " ".join(str(a) for a in args))


class SecondBrainDiffProactiveWiringTests(unittest.TestCase):
    """diff_kit() reports planned hook/CLAUDE.md state, never writes."""

    def test_diff_reports_would_create_hook_and_section_on_fresh_install(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            vault = home / "second-brain"
            for d in VAULT_DIRS:
                (vault / d).mkdir(parents=True, exist_ok=True)
            (vault / ".gitignore").write_text("", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = diff_kit(home=str(home))
            output = buf.getvalue()
            self.assertEqual(result, 0)
            self.assertIn(f"{HOOK_SCRIPT_REL}: would create", output)
            self.assertIn("settings.json SessionStart hook: would register", output)
            self.assertIn("CLAUDE.md second-brain section: would create", output)

    def test_diff_reports_already_present_after_install(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = diff_kit(home=str(home))
            output = buf.getvalue()
            self.assertEqual(result, 0)
            self.assertIn(f"{HOOK_SCRIPT_REL}: up to date", output)
            self.assertIn("settings.json SessionStart hook: already registered", output)
            self.assertIn("CLAUDE.md second-brain section: already present", output)

    def test_diff_never_writes_anything(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            before_hook = (paths.claude_dir / HOOK_SCRIPT_REL).read_bytes()
            before_claude_md = (paths.claude_dir / "CLAUDE.md").read_bytes()

            diff_kit(home=str(home))

            self.assertEqual((paths.claude_dir / HOOK_SCRIPT_REL).read_bytes(), before_hook)
            self.assertEqual((paths.claude_dir / "CLAUDE.md").read_bytes(), before_claude_md)


class SecondBrainCodexHookInstallTests(unittest.TestCase):
    """SessionStart hook script + config.toml array-of-tables registration."""

    def test_install_writes_hook_script_and_registers_block(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            script_path = paths.codex_dir / HOOK_SCRIPT_REL
            self.assertTrue(script_path.is_file(), "codex hook script not installed")
            config = (paths.codex_dir / "config.toml").read_text(encoding="utf-8")
            self.assertIn(f"command = '{_codex_hook_command(paths)}'", config)
            self.assertIn("[[hooks.SessionStart]]", config)

    def test_install_idempotent_reinstall_no_duplicate_block(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            config = (paths.codex_dir / "config.toml").read_text(encoding="utf-8")
            self.assertEqual(config.count("[[hooks.SessionStart]]"), 1)

    def test_install_preserves_unrelated_config_toml_content(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            codex_dir = home / ".codex"
            codex_dir.mkdir(parents=True, exist_ok=True)
            (codex_dir / "config.toml").write_text(
                '[model_providers.custom]\nname = "custom"\n', encoding="utf-8"
            )

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            config = (codex_dir / "config.toml").read_text(encoding="utf-8")
            self.assertIn("[model_providers.custom]", config)
            self.assertIn("[[hooks.SessionStart]]", config)

    def test_install_coexists_with_qmd_mcp_section(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            config = (paths.codex_dir / "config.toml").read_text(encoding="utf-8")
            self.assertIn("[mcp_servers.qmd]", config)
            self.assertIn("[[hooks.SessionStart]]", config)

    def test_dry_run_writes_no_hook_files_or_config_changes(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=True, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            self.assertFalse((paths.codex_dir / HOOK_SCRIPT_REL).exists())
            self.assertFalse((paths.codex_dir / "config.toml").exists())

    def test_hook_command_is_absolute_path_stable_across_reinstall(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            identity1 = _codex_hook_command(paths)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            identity2 = _codex_hook_command(paths)
            config2 = (paths.codex_dir / "config.toml").read_text(encoding="utf-8")

            self.assertEqual(identity1, identity2)
            self.assertIn(str(paths.codex_dir / HOOK_SCRIPT_REL), identity1)
            self.assertIn(f"command = '{identity2}'", config2)
            self.assertEqual(config2.count("[[hooks.SessionStart]]"), 1)


class SecondBrainCodexAgentsSectionTests(unittest.TestCase):
    """~/.codex/AGENTS.md marked-section merge during install()."""

    def test_install_creates_agents_md_with_section_when_absent(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            agents_md = (home / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn(CODEX_INSTRUCTIONS_BEGIN_MARKER, agents_md)
            self.assertIn(CODEX_INSTRUCTIONS_END_MARKER, agents_md)
            self.assertIn("Second-Brain Vault", agents_md)

    def test_install_merges_section_preserving_users_preexisting_content(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            codex_dir = home / ".codex"
            codex_dir.mkdir(parents=True, exist_ok=True)
            (codex_dir / "AGENTS.md").write_text("# My Rules\nBe terse.\n", encoding="utf-8")

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            agents_md = (codex_dir / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("# My Rules", agents_md)
            self.assertIn(CODEX_INSTRUCTIONS_BEGIN_MARKER, agents_md)

    def test_install_idempotent_reinstall_no_duplicate_section(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            agents_md = (home / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
            self.assertEqual(agents_md.count(CODEX_INSTRUCTIONS_BEGIN_MARKER), 1)

    def test_install_updates_stale_section_on_reinstall(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            codex_dir = home / ".codex"
            codex_dir.mkdir(parents=True, exist_ok=True)
            stale = CODEX_INSTRUCTIONS_BEGIN_MARKER + "stale old content\n" + CODEX_INSTRUCTIONS_END_MARKER
            (codex_dir / "AGENTS.md").write_text(stale, encoding="utf-8")

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            agents_md = (codex_dir / "AGENTS.md").read_text(encoding="utf-8")
            self.assertNotIn("stale old content", agents_md)
            self.assertIn("Second-Brain Vault", agents_md)

    def test_dry_run_writes_no_agents_md_changes(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=True, yes=True, setup_deps=False)
            self.assertFalse((home / ".codex" / "AGENTS.md").exists())


class SecondBrainCursorHookInstallTests(unittest.TestCase):
    """sessionStart hook script + flat hooks.json registration."""

    def test_install_writes_hook_script_and_registers_command(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            script_path = paths.cursor_dir / HOOK_SCRIPT_REL
            self.assertTrue(script_path.is_file(), "cursor hook script not installed")
            hooks_config = json.loads((paths.cursor_dir / "hooks.json").read_text(encoding="utf-8"))
            commands = [e["command"] for e in hooks_config["hooks"][CURSOR_SESSIONSTART_EVENT]]
            self.assertIn(_cursor_hook_command(paths), commands)
            self.assertNotIn("groups", str(hooks_config["hooks"][CURSOR_SESSIONSTART_EVENT][0]))

    def test_command_uses_cursor_output_format(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            paths = _paths(home=str(home))
            self.assertIn("--format=cursor", _cursor_hook_command(paths))

    def test_install_idempotent_reinstall_no_duplicate_entry(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            hooks_config = json.loads((paths.cursor_dir / "hooks.json").read_text(encoding="utf-8"))
            commands = [e["command"] for e in hooks_config["hooks"][CURSOR_SESSIONSTART_EVENT]]
            self.assertEqual(commands.count(_cursor_hook_command(paths)), 1)

    def test_install_preserves_users_preexisting_sessionstart_entry(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            cursor_dir = home / ".cursor"
            cursor_dir.mkdir(parents=True, exist_ok=True)
            preexisting = {"version": 1, "hooks": {CURSOR_SESSIONSTART_EVENT: [{"command": "other-cmd"}]}}
            (cursor_dir / "hooks.json").write_text(json.dumps(preexisting), encoding="utf-8")

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            hooks_config = json.loads((cursor_dir / "hooks.json").read_text(encoding="utf-8"))
            commands = [e["command"] for e in hooks_config["hooks"][CURSOR_SESSIONSTART_EVENT]]
            self.assertIn("other-cmd", commands)

    def test_install_preserves_unrelated_events_and_version(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            cursor_dir = home / ".cursor"
            cursor_dir.mkdir(parents=True, exist_ok=True)
            preexisting = {"version": 2, "hooks": {"stop": [{"command": "other"}]}}
            (cursor_dir / "hooks.json").write_text(json.dumps(preexisting), encoding="utf-8")

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            hooks_config = json.loads((cursor_dir / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(hooks_config["version"], 2)
            self.assertEqual(hooks_config["hooks"]["stop"], [{"command": "other"}])

    def test_dry_run_writes_no_hook_files_or_hooks_json_changes(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=True, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            self.assertFalse((paths.cursor_dir / HOOK_SCRIPT_REL).exists())
            self.assertFalse((paths.cursor_dir / "hooks.json").exists())

    def test_install_rejects_invalid_hooks_json_before_other_writes(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            cursor_dir = home / ".cursor"
            cursor_dir.mkdir(parents=True, exist_ok=True)
            (cursor_dir / "hooks.json").write_text("{not valid json", encoding="utf-8")

            rc = install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            self.assertEqual(rc, 1)
            self.assertEqual((cursor_dir / "hooks.json").read_text(encoding="utf-8"), "{not valid json")
            paths = _paths(home=str(home))
            self.assertFalse((paths.claude_dir / HOOK_SCRIPT_REL).exists())


class SecondBrainCursorRuleFileTests(unittest.TestCase):
    """Fully kit-owned ~/.cursor/rules/second-brain.mdc file."""

    def test_install_creates_rule_file(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            rule_path = paths.cursor_dir / CURSOR_RULE_REL
            self.assertTrue(rule_path.is_file())
            content = rule_path.read_text(encoding="utf-8")
            self.assertIn("alwaysApply: true", content)
            self.assertIn("Second-Brain Vault", content)

    def test_install_updates_stale_rule_file(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            paths = _paths(home=str(home))
            rule_path = paths.cursor_dir / CURSOR_RULE_REL
            rule_path.parent.mkdir(parents=True, exist_ok=True)
            rule_path.write_text("stale content", encoding="utf-8")

            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            self.assertNotEqual(rule_path.read_text(encoding="utf-8"), "stale content")
            self.assertIn("Second-Brain Vault", rule_path.read_text(encoding="utf-8"))

    def test_uninstall_removes_unchanged_rule_file(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            rule_path = paths.cursor_dir / CURSOR_RULE_REL
            self.assertTrue(rule_path.exists())

            uninstall(home=str(home), dry_run=False, yes=True)

            self.assertFalse(rule_path.exists())

    def test_uninstall_keeps_hand_edited_rule_file(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            rule_path = paths.cursor_dir / CURSOR_RULE_REL
            rule_path.write_text("hand-edited content", encoding="utf-8")

            uninstall(home=str(home), dry_run=False, yes=True)

            self.assertTrue(rule_path.exists())
            self.assertEqual(rule_path.read_text(encoding="utf-8"), "hand-edited content")


class SecondBrainOpenCodeAgentsSectionTests(unittest.TestCase):
    """OpenCode AGENTS.md marked-section merge (no hook — no session-start API)."""

    def test_install_creates_agents_md_with_section_when_absent(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            agents_md = (paths.opencode_config_dir / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn(OPENCODE_AGENTS_BEGIN_MARKER, agents_md)
            self.assertIn(OPENCODE_AGENTS_END_MARKER, agents_md)
            self.assertIn("Second-Brain Vault", agents_md)

    def test_install_idempotent_reinstall_no_duplicate_section(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            agents_md = (paths.opencode_config_dir / "AGENTS.md").read_text(encoding="utf-8")
            self.assertEqual(agents_md.count(OPENCODE_AGENTS_BEGIN_MARKER), 1)

    def test_dry_run_writes_no_agents_md_changes(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=True, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            self.assertFalse((paths.opencode_config_dir / "AGENTS.md").exists())

    def test_marker_coexists_with_opencode_kit_own_persona_section(self):
        """Second-brain's AGENTS.md merge must coexist with the `opencode` kit's own."""
        from agents.kits.opencode.installer import AGENTS_BEGIN_MARKER as OC_KIT_BEGIN_MARKER
        from agents.kits.opencode.installer import AGENTS_END_MARKER as OC_KIT_END_MARKER
        from agents.kits.opencode.installer import install as opencode_kit_install

        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            # The opencode kit's own `home` param is its config base dir
            # (like $XDG_CONFIG_HOME), not $HOME — pass home/".config" so it
            # writes into the same AGENTS.md second-brain targets.
            opencode_kit_install(home=str(home / ".config"), dry_run=False, yes=True)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            paths = _paths(home=str(home))
            agents_md_path = paths.opencode_config_dir / "AGENTS.md"
            agents_md = agents_md_path.read_text(encoding="utf-8")
            self.assertIn(OC_KIT_BEGIN_MARKER, agents_md)
            self.assertIn(OPENCODE_AGENTS_BEGIN_MARKER, agents_md)

            uninstall(home=str(home), dry_run=False, yes=True)
            after_second_brain_uninstall = agents_md_path.read_text(encoding="utf-8")
            self.assertIn(OC_KIT_BEGIN_MARKER, after_second_brain_uninstall)
            self.assertNotIn(OPENCODE_AGENTS_BEGIN_MARKER, after_second_brain_uninstall)


class SecondBrainPartialConfigFailureTests(unittest.TestCase):
    """One agent's invalid config must not block proactive wiring for the others."""

    def test_invalid_settings_json_does_not_block_codex_or_cursor(self):
        # Uses enable_hook() (not install()) — install() has its own
        # top-level _validate_configs preflight that intentionally aborts
        # the whole install on invalid settings.json (existing, tested
        # behavior, unrelated to this feature). enable_hook() has no such
        # gate: each agent's config is isolated inside its own install_fn.
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            claude_dir = home / ".claude"
            claude_dir.mkdir(parents=True, exist_ok=True)
            (claude_dir / "settings.json").write_text("{not valid json", encoding="utf-8")

            result = enable_hook(home=str(home), dry_run=False, yes=True)

            self.assertEqual(result, 0)
            self.assertEqual((claude_dir / "settings.json").read_text(encoding="utf-8"), "{not valid json")
            paths = _paths(home=str(home))
            self.assertTrue((paths.codex_dir / HOOK_SCRIPT_REL).exists())
            self.assertTrue((paths.cursor_dir / HOOK_SCRIPT_REL).exists())
            self.assertTrue((paths.opencode_config_dir / "AGENTS.md").exists())

    def test_invalid_cursor_hooks_json_aborts_install_before_other_writes(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            cursor_dir = home / ".cursor"
            cursor_dir.mkdir(parents=True, exist_ok=True)
            (cursor_dir / "hooks.json").write_text("{not valid json", encoding="utf-8")

            result = install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            self.assertEqual(result, 1)
            paths = _paths(home=str(home))
            self.assertFalse((paths.vault).exists())
            self.assertFalse((paths.claude_dir / HOOK_SCRIPT_REL).exists())
            self.assertFalse((paths.codex_dir / HOOK_SCRIPT_REL).exists())


class SecondBrainMultiAgentEnableHookTests(unittest.TestCase):
    """enable_hook() wires Claude, Codex, Cursor, and OpenCode in one shot."""

    def test_enable_hook_wires_all_agents_in_one_shot(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            result = enable_hook(home=str(home), dry_run=False, yes=True)
            self.assertEqual(result, 0)
            paths = _paths(home=str(home))
            self.assertTrue((paths.claude_dir / HOOK_SCRIPT_REL).exists())
            self.assertTrue((paths.codex_dir / HOOK_SCRIPT_REL).exists())
            self.assertTrue((paths.cursor_dir / HOOK_SCRIPT_REL).exists())
            self.assertTrue((paths.cursor_dir / CURSOR_RULE_REL).exists())
            self.assertTrue((paths.opencode_config_dir / "AGENTS.md").exists())

    def test_enable_hook_idempotent_across_all_agents(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            enable_hook(home=str(home), dry_run=False, yes=True)
            enable_hook(home=str(home), dry_run=False, yes=True)
            paths = _paths(home=str(home))
            config = (paths.codex_dir / "config.toml").read_text(encoding="utf-8")
            self.assertEqual(config.count("[[hooks.SessionStart]]"), 1)
            hooks_config = json.loads((paths.cursor_dir / "hooks.json").read_text(encoding="utf-8"))
            commands = [e["command"] for e in hooks_config["hooks"][CURSOR_SESSIONSTART_EVENT]]
            self.assertEqual(commands.count(_cursor_hook_command(paths)), 1)

    def test_enable_hook_partial_state_resumes_correctly(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            paths = _paths(home=str(home))
            paths.claude_dir.mkdir(parents=True, exist_ok=True)
            # Pre-wire only Claude Code; Codex/Cursor/OpenCode remain absent.
            from agents.kits.second_brain.installer import _install_session_hook, _merge_claude_md_section
            _install_session_hook(paths)
            _merge_claude_md_section(paths)

            with patch("agents.kits.second_brain.installer._confirm") as mock_confirm:
                _offer_proactive_context(paths, yes=False)
                # Not fully installed yet (only Claude) -> must still prompt.
                mock_confirm.assert_called_once()

            # Now finish via --yes, and confirm the already-wired Claude side
            # is left untouched (still exactly one CLAUDE.md section) while
            # the remaining three agents get wired.
            _offer_proactive_context(paths, yes=True)
            claude_md = (paths.claude_dir / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertEqual(claude_md.count(CLAUDE_MD_BEGIN_MARKER), 1)
            self.assertTrue((paths.codex_dir / HOOK_SCRIPT_REL).exists())
            self.assertTrue((paths.cursor_dir / HOOK_SCRIPT_REL).exists())
            self.assertTrue((paths.opencode_config_dir / "AGENTS.md").exists())


class SecondBrainMultiAgentUninstallTests(unittest.TestCase):
    """uninstall() strips Codex/Cursor/OpenCode kit-owned wiring."""

    def test_uninstall_strips_codex_hook_block(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            config_path = paths.codex_dir / "config.toml"

            uninstall(home=str(home), dry_run=False, yes=True)

            # config.toml is entirely kit-owned in the default fixture (qmd
            # MCP section + hook block) so uninstall deletes it, matching the
            # existing fully-owned-file deletion behavior used for CLAUDE.md.
            if config_path.exists():
                self.assertNotIn("[[hooks.SessionStart]]", config_path.read_text(encoding="utf-8"))
            self.assertFalse((paths.codex_dir / HOOK_SCRIPT_REL).exists())

    def test_uninstall_preserves_unrelated_codex_config_toml_content(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            codex_dir = home / ".codex"
            codex_dir.mkdir(parents=True, exist_ok=True)
            (codex_dir / "config.toml").write_text(
                '[model_providers.custom]\nname = "custom"\n', encoding="utf-8"
            )
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            uninstall(home=str(home), dry_run=False, yes=True)

            config = (codex_dir / "config.toml").read_text(encoding="utf-8")
            self.assertIn("[model_providers.custom]", config)
            self.assertNotIn("[[hooks.SessionStart]]", config)

    def test_uninstall_strips_codex_agents_section_preserves_user_content(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            codex_dir = home / ".codex"
            codex_dir.mkdir(parents=True, exist_ok=True)
            (codex_dir / "AGENTS.md").write_text("# My Rules\n", encoding="utf-8")
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            uninstall(home=str(home), dry_run=False, yes=True)

            agents_md = (codex_dir / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("# My Rules", agents_md)
            self.assertNotIn(CODEX_INSTRUCTIONS_BEGIN_MARKER, agents_md)

    def test_uninstall_strips_legacy_codex_instructions_section_preserves_user_content(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            codex_dir = home / ".codex"
            codex_dir.mkdir(parents=True, exist_ok=True)
            legacy = (
                "# My Rules\n"
                + CODEX_INSTRUCTIONS_BEGIN_MARKER
                + "legacy second-brain content\n"
                + CODEX_INSTRUCTIONS_END_MARKER
            )
            (codex_dir / "instructions.md").write_text(legacy, encoding="utf-8")

            uninstall(home=str(home), dry_run=False, yes=True)

            instructions = (codex_dir / "instructions.md").read_text(encoding="utf-8")
            self.assertIn("# My Rules", instructions)
            self.assertNotIn(CODEX_INSTRUCTIONS_BEGIN_MARKER, instructions)

    def test_uninstall_strips_cursor_hook_entry_preserves_others(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            cursor_dir = home / ".cursor"
            cursor_dir.mkdir(parents=True, exist_ok=True)
            preexisting = {"version": 1, "hooks": {CURSOR_SESSIONSTART_EVENT: [{"command": "other-cmd"}]}}
            (cursor_dir / "hooks.json").write_text(json.dumps(preexisting), encoding="utf-8")
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            uninstall(home=str(home), dry_run=False, yes=True)

            hooks_config = json.loads((cursor_dir / "hooks.json").read_text(encoding="utf-8"))
            commands = [e["command"] for e in hooks_config["hooks"][CURSOR_SESSIONSTART_EVENT]]
            self.assertIn("other-cmd", commands)
            paths = _paths(home=str(home))
            self.assertNotIn(_cursor_hook_command(paths), commands)
            self.assertFalse((paths.cursor_dir / HOOK_SCRIPT_REL).exists())

    def test_uninstall_strips_opencode_agents_section_preserves_user_content(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            opencode_dir = home / ".config" / "opencode"
            opencode_dir.mkdir(parents=True, exist_ok=True)
            (opencode_dir / "AGENTS.md").write_text("# My Rules\n", encoding="utf-8")
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)

            uninstall(home=str(home), dry_run=False, yes=True)

            agents_md = (opencode_dir / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("# My Rules", agents_md)
            self.assertNotIn(OPENCODE_AGENTS_BEGIN_MARKER, agents_md)

    def test_uninstall_never_touches_vault_content(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            vault = home / "second-brain"

            uninstall(home=str(home), dry_run=False, yes=True)

            self.assertTrue(vault.exists())
            self.assertTrue((vault / ".git").is_dir())


class SecondBrainMultiAgentDoctorDiffTests(unittest.TestCase):
    """doctor()/diff_kit() report Codex/Cursor/OpenCode wiring state, read-only."""

    def _which_returns_qmd(self, cmd):
        if cmd in ("qmd", "git"):
            return f"/fake/{cmd}"
        return None

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_reports_codex_cursor_opencode_present(self, mock_run, mock_which):
        mock_which.side_effect = self._which_returns_qmd
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")
            mock_run.return_value = subprocess.CompletedProcess([], 0, f"  {wiki_path}\n", "")
            buf = io.StringIO()
            with redirect_stdout(buf):
                doctor(home=str(home))
            output = buf.getvalue()
            self.assertIn("SessionStart hook registered in config.toml", output)
            self.assertIn("AGENTS.md second-brain section present", output)
            self.assertIn("sessionStart hook registered in hooks.json", output)
            self.assertIn("rule file up to date", output)
            self.assertIn("opencode AGENTS.md second-brain section present", output)

    @patch("agents.kits.second_brain.installer.shutil.which")
    @patch("agents.kits.second_brain.installer.subprocess.run")
    def test_doctor_reports_absence_as_info_not_failure(self, mock_run, mock_which):
        mock_which.side_effect = self._which_returns_qmd
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            with patch("agents.kits.second_brain.installer.core.confirm", return_value=True):
                with patch("agents.kits.second_brain.installer._confirm", return_value=False):
                    install(home=str(home), dry_run=False, yes=False, setup_deps=False)
            wiki_path = str(home.resolve() / "second-brain" / "wiki")
            mock_run.return_value = subprocess.CompletedProcess([], 0, f"  {wiki_path}\n", "")
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = doctor(home=str(home))
            output = buf.getvalue()
            self.assertEqual(result, 0)
            self.assertIn("not registered in config.toml", output)
            self.assertIn("not registered in hooks.json", output)

    def test_diff_reports_would_create_for_new_agents_on_fresh_install(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            vault = home / "second-brain"
            for d in VAULT_DIRS:
                (vault / d).mkdir(parents=True, exist_ok=True)
            (vault / ".gitignore").write_text("", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = diff_kit(home=str(home))
            output = buf.getvalue()
            self.assertEqual(result, 0)
            self.assertIn("config.toml SessionStart hook: would register", output)
            self.assertIn("AGENTS.md second-brain section: would create", output)
            self.assertIn("hooks.json sessionStart hook: would register", output)
            self.assertIn(f"{CURSOR_RULE_REL}: would create", output)
            self.assertIn("opencode AGENTS.md second-brain section: would create", output)

    def test_diff_reports_already_present_after_install(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = diff_kit(home=str(home))
            output = buf.getvalue()
            self.assertEqual(result, 0)
            self.assertIn("config.toml SessionStart hook: already registered", output)
            self.assertIn("AGENTS.md second-brain section: already present", output)
            self.assertIn("hooks.json sessionStart hook: already registered", output)
            self.assertIn(f"{CURSOR_RULE_REL}: up to date", output)
            self.assertIn("opencode AGENTS.md second-brain section: already present", output)

    def test_diff_never_writes_anything_for_new_agents(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)
            install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            paths = _paths(home=str(home))
            before_config = (paths.codex_dir / "config.toml").read_bytes()
            before_hooks_json = (paths.cursor_dir / "hooks.json").read_bytes()
            before_rule = (paths.cursor_dir / CURSOR_RULE_REL).read_bytes()

            diff_kit(home=str(home))

            self.assertEqual((paths.codex_dir / "config.toml").read_bytes(), before_config)
            self.assertEqual((paths.cursor_dir / "hooks.json").read_bytes(), before_hooks_json)
            self.assertEqual((paths.cursor_dir / CURSOR_RULE_REL).read_bytes(), before_rule)


if __name__ == "__main__":
    unittest.main()
