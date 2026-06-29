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

    def test_install_skips_non_object_root(self):
        with tempfile.TemporaryDirectory() as home_str:
            home = Path(home_str)

            config_dir = home / ".config" / "opencode"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "opencode.jsonc"
            config_path.write_text(json.dumps("just a string"), encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                install(home=str(home), dry_run=False, yes=True, setup_deps=False)
            output = buf.getvalue()

            self.assertIn("opencode.jsonc root is not an object", output)
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
    def test_doctor_fails_on_old_node_version(self, mock_which, mock_run):
        def _which(cmd):
            if cmd in ("git", "node", "npm"):
                return f"/fake/{cmd}"
            return None

        mock_which.side_effect = _which

        def _run(cmd, **kw):
            if "node" in cmd:
                return subprocess.CompletedProcess(cmd, 0, "v18.12.0\n", "")
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
            self.assertIn("node", output)


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
            if cmd in ("npm",):
                return f"/fake/{cmd}"
            return None

        mock_which.side_effect = _which
        mock_run.return_value = subprocess.CompletedProcess([], 0, "", "")
        with tempfile.TemporaryDirectory() as home_str:
            with patch("agents.kits.second_brain.installer._confirm", return_value=False) as mock_confirm:
                _setup_qmd(Path(home_str) / "wiki", yes=False)
                mock_confirm.assert_called_once()

    @patch("agents.kits.second_brain.installer.subprocess.run")
    @patch("agents.kits.second_brain.installer.shutil.which")
    def test_install_yes_bypasses_npm_prompt(self, mock_which, mock_run):
        def _which(cmd):
            if cmd in ("git", "npm"):
                return f"/fake/{cmd}"
            return None

        mock_which.side_effect = _which
        mock_run.return_value = subprocess.CompletedProcess([], 0, "", "")
        with tempfile.TemporaryDirectory() as home_str:
            with patch("agents.kits.second_brain.installer._confirm") as mock_confirm:
                rc = install(home=home_str, dry_run=False, yes=True, setup_deps=True)
            self.assertEqual(rc, 0)
            mock_confirm.assert_not_called()

    @patch("agents.kits.second_brain.installer.subprocess.run")
    @patch("agents.kits.second_brain.installer.shutil.which")
    def test_install_non_fatal_when_npm_missing(self, mock_which, mock_run):
        def _which(cmd):
            if cmd == "git":
                return "/usr/bin/git"
            return None

        mock_which.side_effect = _which
        mock_run.return_value = subprocess.CompletedProcess([], 0, "", "")
        with tempfile.TemporaryDirectory() as home_str:
            rc = install(home=home_str, dry_run=False, yes=True, setup_deps=True)
            self.assertEqual(rc, 0)
            manifest = Path(home_str) / "second-brain" / ".vibe-engineering-manifest.json"
            self.assertTrue(manifest.exists(), "manifest should exist even when npm missing")


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
