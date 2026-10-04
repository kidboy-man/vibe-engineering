import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "agents" / "kits" / "workflow" / "templates" / "workflow"
SCRIPT = TEMPLATES / "shared" / "skills" / "vibe-flow" / "scripts" / "check_trace.py"
TARGETS = ("claude", "opencode")

spec = importlib.util.spec_from_file_location("check_trace_contract", SCRIPT)
ct = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ct
spec.loader.exec_module(ct)

MANIFEST = json.loads((TEMPLATES / "manifest.json").read_text(encoding="utf-8"))


def source(target: str, rel: str) -> Path:
    variant = TEMPLATES / target / rel
    return variant if variant.exists() else TEMPLATES / "shared" / rel


def files_under(directory: Path) -> set[str]:
    return {
        str(p.relative_to(directory))
        for p in directory.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }


def markdown_files() -> list[tuple[str, str, str]]:
    return [
        (target, rel, source(target, rel).read_text(encoding="utf-8"))
        for target in TARGETS
        for rel in MANIFEST["managed_files"]
        if rel.endswith(".md")
    ]


class ManifestTests(unittest.TestCase):
    def test_kit_name(self):
        self.assertEqual(MANIFEST["kit"], "workflow")

    def test_every_managed_file_resolves_for_every_target(self):
        for target in TARGETS:
            for rel in MANIFEST["managed_files"]:
                with self.subTest(target=target, rel=rel):
                    self.assertTrue(source(target, rel).is_file())

    def test_no_template_file_is_missing_from_the_manifest(self):
        on_disk = set()
        for directory in ("shared", *TARGETS):
            on_disk |= files_under(TEMPLATES / directory)
        self.assertEqual(on_disk, set(MANIFEST["managed_files"]))

    def test_targets_have_the_same_variant_files(self):
        self.assertEqual(files_under(TEMPLATES / "claude"), files_under(TEMPLATES / "opencode"))

    def test_shared_files_are_not_also_overridden_per_target(self):
        shared = files_under(TEMPLATES / "shared")
        for target in TARGETS:
            self.assertFalse(shared & files_under(TEMPLATES / target))


class PromptContentTests(unittest.TestCase):
    def test_every_markdown_file_has_frontmatter_description(self):
        for target, rel, text in markdown_files():
            with self.subTest(target=target, rel=rel):
                match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
                self.assertIsNotNone(match, "missing frontmatter block")
                self.assertRegex(match.group(1), r"(?m)^description:")

    def test_shipped_skill_frontmatter_parses_with_the_validator_parser(self):
        # Regression: the parser once rejected the folded `description: >` block of our own skill.
        for target in TARGETS:
            with self.subTest(target=target):
                text = source(target, "skills/vibe-flow/SKILL.md").read_text(encoding="utf-8")
                meta, errors = ct.parse_frontmatter(text)
                self.assertEqual(errors, [])
                self.assertEqual(meta["name"], "vibe-flow")
                self.assertIn("business requirement", meta["description"])

    def test_skill_is_named_vibe_flow(self):
        text = source("claude", "skills/vibe-flow/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: vibe-flow", text.split("---")[1])

    def test_targets_do_not_reference_each_others_paths_or_tools(self):
        for target, rel, text in markdown_files():
            with self.subTest(target=target, rel=rel):
                if target == "opencode":
                    self.assertNotIn("~/.claude", text)
                    self.assertNotIn("AskUserQuestion", text)
                    self.assertNotIn("argument-hint", text)
                else:
                    self.assertNotIn("~/.config/opencode", text)

    def test_commands_that_run_the_validator_point_at_their_own_install_path(self):
        expected = {"claude": "~/.claude/skills/vibe-flow/scripts/check_trace.py",
                    "opencode": "${XDG_CONFIG_HOME:-$HOME/.config}/opencode/skills/vibe-flow/scripts/check_trace.py"}
        for target in TARGETS:
            for rel in ("commands/implement-ticket.md", "commands/push-tickets.md", "skills/vibe-flow/SKILL.md"):
                with self.subTest(target=target, rel=rel):
                    self.assertIn(expected[target], source(target, rel).read_text(encoding="utf-8"))

    def test_skill_documents_every_convention_the_validator_relies_on(self):
        text = source("claude", "skills/vibe-flow/SKILL.md").read_text(encoding="utf-8")
        for needle in ("R-001", "Priority:", "## Traceability", "id: T-01", "implements:", "blocked_by:",
                       "status:", "check_trace.py", "--next", "docs/prd/", "docs/trd/", ".vibe/issues/"):
            with self.subTest(needle):
                self.assertIn(needle, text)

    def test_destructive_steps_are_gated_on_approval(self):
        push = source("claude", "commands/push-tickets.md").read_text(encoding="utf-8").lower()
        self.assertIn("explicit approval", push)
        self.assertIn("gh issue create", push)
        implement = source("claude", "commands/implement-ticket.md").read_text(encoding="utf-8")
        self.assertIn("Do NOT commit", implement)
        flow = source("claude", "commands/flow.md").read_text(encoding="utf-8")
        self.assertIn("Never commit, push, or create issues", flow)


class SkillExamplesParseTests(unittest.TestCase):
    """The examples shown to the agent must be accepted by the validator shipped with them."""

    def _skill(self) -> str:
        return source("claude", "skills/vibe-flow/SKILL.md").read_text(encoding="utf-8")

    def test_ticket_frontmatter_example_parses(self):
        block = re.search(r"```yaml\n(.*?)```", self._skill(), re.DOTALL).group(1)
        meta, errors = ct.parse_frontmatter(f"---\n{block}---\n")
        self.assertEqual(errors, [])
        self.assertEqual(meta["id"], "T-01")
        self.assertEqual(meta["implements"], ["R-001", "R-003"])
        self.assertEqual(meta["blocked_by"], ["T-00"])
        self.assertEqual(meta["status"], "todo")

    def test_prd_requirement_example_parses(self):
        block = re.search(r"```markdown\n(### R-001.*?)```", self._skill(), re.DOTALL).group(1)
        self.assertEqual(ct.parse_prd(block), {"R-001": "must"})


KIT_TEMPLATES = {
    "claude": ROOT / "agents" / "kits" / "claude_code" / "templates" / "claude",
    "opencode": ROOT / "agents" / "kits" / "opencode" / "templates" / "opencode",
}


class UpgradedExistingStagesTests(unittest.TestCase):
    """/trd and vibe-engineering (owned by the claude-code/opencode kits) chain into this flow."""

    def _text(self, target: str, rel: str) -> str:
        return (KIT_TEMPLATES[target] / rel).read_text(encoding="utf-8")

    def test_trd_command_supports_prd_traceability(self):
        for target in TARGETS:
            with self.subTest(target=target):
                text = self._text(target, "commands/trd.md")
                for needle in ("docs/prd/", "prd:", "Traceability", "R-001", "test cases per requirement"):
                    self.assertIn(needle, text)
                # original behaviour is untouched
                for needle in ("## Create Mode", "## Update Mode", "## Improve Mode", "Gap Analysis", "docs/trd/"):
                    self.assertIn(needle, text)

    def test_vibe_engineering_emits_traceability_fields_and_keeps_checkpoints(self):
        for target in TARGETS:
            with self.subTest(target=target):
                text = self._text(target, "skills/vibe-engineering/SKILL.md")
                for needle in ("implements:", "blocked_by:", "status: todo", '"prd"', "check_trace.py",
                               "CHECKPOINT 1", "CHECKPOINT 2", "Do not push automatically"):
                    self.assertIn(needle, text)

    def test_vibe_engineering_ticket_example_parses_with_the_validator(self):
        for target in TARGETS:
            with self.subTest(target=target):
                text = self._text(target, "skills/vibe-engineering/SKILL.md")
                block = re.search(r"```markdown\n(---\nid: T-01.*?\n---)\n", text, re.DOTALL).group(1)
                meta, errors = ct.parse_frontmatter(block + "\n")
                self.assertEqual(errors, [])
                for key in ("id", "implements", "blocked_by", "size", "status", "title", "labels"):
                    self.assertIn(key, meta)

    def test_upgraded_next_step_line_is_conditional_on_the_workflow_kit(self):
        for target in TARGETS:
            with self.subTest(target=target):
                text = self._text(target, "skills/vibe-engineering/SKILL.md")
                self.assertIn("Kalau workflow kit terpasang", text)
                self.assertIn("push pakai GitHub issue skill lo", text)

    def test_upgraded_validator_path_matches_the_target(self):
        self.assertIn("~/.claude/skills/vibe-flow/scripts/check_trace.py",
                      self._text("claude", "skills/vibe-engineering/SKILL.md"))
        opencode = self._text("opencode", "skills/vibe-engineering/SKILL.md")
        self.assertIn("${XDG_CONFIG_HOME:-$HOME/.config}/opencode/skills/vibe-flow/scripts/check_trace.py", opencode)
        self.assertNotIn("~/.claude", opencode)


if __name__ == "__main__":
    unittest.main()
