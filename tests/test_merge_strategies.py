import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import merge_strategies as ms


class JsonDefaultsStrategyTests(unittest.TestCase):
    def test_applies_defaults_for_missing_keys(self):
        fragment = {"effortLevel": "xhigh", "autoUpdate": True}
        current = {"model": "opus"}
        secret_keys = set()
        merged, changed = ms.json_defaults_strategy(fragment, current, secret_keys)
        self.assertTrue(changed)
        self.assertEqual(merged["model"], "opus")
        self.assertEqual(merged["effortLevel"], "xhigh")
        self.assertEqual(merged["autoUpdate"], True)

    def test_never_overwrites_existing_keys(self):
        fragment = {"model": "sonnet", "effortLevel": "xhigh"}
        current = {"model": "opus", "effortLevel": "high"}
        merged, changed = ms.json_defaults_strategy(fragment, current, set())
        self.assertFalse(changed)
        self.assertEqual(merged["model"], "opus")
        self.assertEqual(merged["effortLevel"], "high")

    def test_skips_env_key(self):
        fragment = {"env": {"FOO": "bar"}, "effortLevel": "xhigh"}
        current = {}
        merged, changed = ms.json_defaults_strategy(fragment, current, set())
        self.assertTrue(changed)
        self.assertNotIn("env", merged)
        self.assertEqual(merged["effortLevel"], "xhigh")

    def test_skips_secret_keys(self):
        fragment = {"ANTHROPIC_API_KEY": "leak", "effortLevel": "xhigh"}
        current = {}
        secret_keys = {"ANTHROPIC_API_KEY"}
        merged, changed = ms.json_defaults_strategy(fragment, current, secret_keys)
        self.assertTrue(changed)
        self.assertNotIn("ANTHROPIC_API_KEY", merged)
        self.assertEqual(merged["effortLevel"], "xhigh")

    def test_returns_unchanged_when_nothing_to_add(self):
        fragment = {"effortLevel": "xhigh"}
        current = {"effortLevel": "xhigh"}
        merged, changed = ms.json_defaults_strategy(fragment, current, set())
        self.assertFalse(changed)


class JsoncParsingTests(unittest.TestCase):
    def test_strip_line_comments(self):
        raw = '{"a": 1, // comment\n"b": 2}'
        cleaned = ms.strip_jsonc_comments(raw)
        parsed = json.loads(cleaned)
        self.assertEqual(parsed, {"a": 1, "b": 2})

    def test_strip_block_comments(self):
        raw = '{"a": 1, /* block */ "b": 2}'
        cleaned = ms.strip_jsonc_comments(raw)
        parsed = json.loads(cleaned)
        self.assertEqual(parsed, {"a": 1, "b": 2})

    def test_preserves_strings_with_comment_syntax(self):
        raw = '{"url": "https://example.invalid/path//segment", "pattern": "foo /* bar */ baz"}'
        parsed = ms.parse_jsonc(raw)
        self.assertEqual(parsed["url"], "https://example.invalid/path//segment")
        self.assertEqual(parsed["pattern"], "foo /* bar */ baz")

    def test_preserves_escaped_quotes(self):
        raw = '{"msg": "say \\"hello\\""}'
        parsed = ms.parse_jsonc(raw)
        self.assertEqual(parsed["msg"], 'say "hello"')

    def test_strip_trailing_commas(self):
        raw = '{"a": 1, "b": 2,}'
        parsed = ms.parse_jsonc(raw)
        self.assertEqual(parsed, {"a": 1, "b": 2})

    def test_parse_jsonc_falls_back_on_plain_json(self):
        raw = '{"a": 1}'
        parsed = ms.parse_jsonc(raw)
        self.assertEqual(parsed, {"a": 1})


class JsoncDefaultsStrategyTests(unittest.TestCase):
    def test_applies_defaults_for_missing_keys(self):
        fragment = {"$schema": "https://example.invalid/schema", "lsp": True}
        current = {"model": "anthropic"}
        merged, changed = ms.jsonc_defaults_strategy(fragment, current, {"model"}, lambda k: False)
        self.assertTrue(changed)
        self.assertEqual(merged["model"], "anthropic")
        self.assertEqual(merged["$schema"], "https://example.invalid/schema")
        self.assertTrue(merged["lsp"])

    def test_skips_local_only_keys(self):
        fragment = {"model": "sonnet", "lsp": True}
        current = {}
        local_only = {"model"}
        merged, changed = ms.jsonc_defaults_strategy(fragment, current, local_only, lambda k: False)
        self.assertTrue(changed)
        self.assertNotIn("model", merged)
        self.assertTrue(merged["lsp"])

    def test_skips_secret_keys(self):
        fragment = {"apiKey": "secret", "lsp": True}
        current = {}
        merged, changed = ms.jsonc_defaults_strategy(
            fragment, current, set(), lambda k: "key" in k.lower()
        )
        self.assertTrue(changed)
        self.assertNotIn("apiKey", merged)
        self.assertTrue(merged["lsp"])

    def test_never_overwrites_existing(self):
        fragment = {"lsp": True}
        current = {"lsp": False}
        merged, changed = ms.jsonc_defaults_strategy(fragment, current, set(), lambda k: False)
        self.assertFalse(changed)
        self.assertEqual(merged["lsp"], False)


class MarkedSectionStrategyTests(unittest.TestCase):
    BEGIN = "<!-- begin -->\n"
    END = "<!-- end -->\n"

    def test_create_when_no_existing(self):
        merged, action = ms.marked_section_strategy("body", None, self.BEGIN, self.END)
        self.assertEqual(action, "create")
        self.assertIn(self.BEGIN, merged)
        self.assertIn(self.END, merged)
        self.assertIn("body", merged)

    def test_merge_prepends_when_no_markers(self):
        merged, action = ms.marked_section_strategy("body", "user\n", self.BEGIN, self.END)
        self.assertEqual(action, "merge")
        self.assertIn(self.BEGIN, merged)
        self.assertIn(self.END, merged)
        self.assertIn("body", merged)
        self.assertIn("user", merged)
        self.assertTrue(merged.index("user") > merged.index(self.END))

    def test_merge_replaces_between_markers(self):
        existing = self.BEGIN + "old\n" + self.END + "after\n"
        merged, action = ms.marked_section_strategy("new\n", existing, self.BEGIN, self.END)
        self.assertEqual(action, "merge")
        self.assertIn("new", merged)
        self.assertNotIn("old", merged)
        self.assertIn("after", merged)
        self.assertEqual(merged.count(self.BEGIN), 1)
        self.assertEqual(merged.count(self.END), 1)

    def test_unchanged_when_identical(self):
        wrapped = self.BEGIN + "body\n" + self.END
        merged, action = ms.marked_section_strategy("body\n", wrapped, self.BEGIN, self.END)
        self.assertEqual(action, "unchanged")
        self.assertEqual(merged, wrapped)


class StripMarkedSectionTests(unittest.TestCase):
    BEGIN = "<!-- begin -->\n"
    END = "<!-- end -->\n"

    def test_returns_none_when_only_kit_content(self):
        existing = self.BEGIN + "body\n" + self.END
        remaining, fully_owned = ms.strip_marked_section(existing, self.BEGIN, self.END)
        self.assertTrue(fully_owned)
        self.assertIsNone(remaining)

    def test_strips_section_and_returns_remaining(self):
        existing = "before\n" + self.BEGIN + "body\n" + self.END + "after\n"
        remaining, fully_owned = ms.strip_marked_section(existing, self.BEGIN, self.END)
        self.assertFalse(fully_owned)
        self.assertIsNotNone(remaining)
        assert remaining is not None
        self.assertNotIn(self.BEGIN, remaining)
        self.assertNotIn(self.END, remaining)
        self.assertIn("before", remaining)
        self.assertIn("after", remaining)

    def test_returns_existing_when_no_markers(self):
        existing = "user only\n"
        remaining, fully_owned = ms.strip_marked_section(existing, self.BEGIN, self.END)
        self.assertFalse(fully_owned)
        self.assertEqual(remaining, existing)

    def test_adds_trailing_newline_when_needed(self):
        existing = self.BEGIN + "body\n" + self.END + "after"
        remaining, fully_owned = ms.strip_marked_section(existing, self.BEGIN, self.END)
        self.assertFalse(fully_owned)
        assert remaining is not None
        self.assertTrue(remaining.endswith("\n"))


class TomlBlockMergeStrategyTests(unittest.TestCase):
    """Codex TOML merge: insert/replace one kit-owned section/table.

    Uses ``ms.toml_block_merge_strategy(section_header, template_body, current)``
    which returns ``(merged_content, action)`` where action is one of
    ``'create'`` (no existing file), ``'merge'`` (content changed), or
    ``'unchanged'``.
    """

    SECTION = "[mcp_servers.qmd]"
    BODY = 'type = "stdio"\ncommand = "qmd"\nargs = ["mcp"]\n'
    FULL_BLOCK = SECTION + "\n" + BODY

    def test_create_when_none_current(self):
        merged, action = ms.toml_block_merge_strategy(self.SECTION, self.BODY, None)
        self.assertEqual(action, "create")
        self.assertIn(self.SECTION, merged)
        self.assertIn('type = "stdio"', merged)
        self.assertIn('command = "qmd"', merged)

    def test_insert_when_section_absent(self):
        current = '[other]\nkey = "value"\n'
        merged, action = ms.toml_block_merge_strategy(self.SECTION, self.BODY, current)
        self.assertEqual(action, "merge")
        self.assertIn(self.SECTION, merged)
        self.assertIn(self.BODY, merged)
        self.assertIn("[other]", merged)
        self.assertIn('key = "value"', merged)

    def test_preserves_unrelated_tables_byte_for_byte(self):
        current = '[other]\nkey = "value"\n# my comment\n'
        merged, _ = ms.toml_block_merge_strategy(self.SECTION, self.BODY, current)
        self.assertIn('[other]\nkey = "value"\n# my comment\n', merged)

    def test_preserves_comment_before_kit_block(self):
        current = '# user config below\n[other]\nkey = "value"\n'
        merged, _ = ms.toml_block_merge_strategy(self.SECTION, self.BODY, current)
        self.assertIn("# user config below", merged)

    def test_replaces_existing_kit_block(self):
        current = (
            '[other]\nkey = "value"\n\n'
            + self.SECTION + '\n'
            + 'type = "stdio"\ncommand = "old"\n'
        )
        merged, action = ms.toml_block_merge_strategy(self.SECTION, self.BODY, current)
        self.assertEqual(action, "merge")
        self.assertIn('command = "qmd"', merged)
        self.assertNotIn('command = "old"', merged)
        self.assertIn("[other]", merged)
        self.assertIn('key = "value"', merged)
        # Section header appears only once
        self.assertEqual(merged.count(self.SECTION), 1)

    def test_replaces_canonical_block_regardless_of_comment_inside(self):
        """Comments inside kit block may be replaced by canonical kit block."""
        current = (
            '# user header\n'
            + self.SECTION + '\n'
            + '# internal comment\n'
            + 'type = "stdio"\n'
            + 'command = "qmd"\n'
            + 'args = ["mcp"]\n'
            + '[other]\nkey = "val"\n'
        )
        merged, action = ms.toml_block_merge_strategy(self.SECTION, self.BODY, current)
        self.assertEqual(action, "merge")
        self.assertIn("[other]", merged)
        self.assertIn(self.SECTION, merged)
        self.assertIn(self.BODY, merged)
        # The internal comment may be gone after canonical replacement
        self.assertIn("# user header", merged)

    def test_unchanged_when_kit_block_identical(self):
        current = '[other]\nkey = "value"\n\n' + self.FULL_BLOCK
        merged, action = ms.toml_block_merge_strategy(self.SECTION, self.BODY, current)
        self.assertEqual(action, "unchanged")

    def test_inserts_at_end_respecting_trailing_newline(self):
        current = '[other]\nkey = "value"'
        merged, action = ms.toml_block_merge_strategy(self.SECTION, self.BODY, current)
        self.assertIn(self.SECTION, merged)
        self.assertIn(self.BODY, merged)
        self.assertIn("[other]", merged)


class StripTomlBlockTests(unittest.TestCase):
    """Codex TOML strip: remove only kit-owned section."""

    SECTION = "[mcp_servers.qmd]"
    BODY = 'type = "stdio"\ncommand = "qmd"\nargs = ["mcp"]\n'
    FULL_BLOCK = SECTION + "\n" + BODY

    def test_returns_none_when_only_kit_content(self):
        existing = self.FULL_BLOCK
        remaining, fully_owned = ms.strip_toml_block(existing, self.SECTION)
        self.assertTrue(fully_owned)
        self.assertIsNone(remaining)

    def test_returns_none_when_only_kit_content_with_trailing_newlines(self):
        existing = self.FULL_BLOCK + "\n\n"
        remaining, fully_owned = ms.strip_toml_block(existing, self.SECTION)
        self.assertTrue(fully_owned)

    def test_strips_kit_block_leaves_unrelated_tables_intact(self):
        existing = '[other]\nkey = "value"\n\n' + self.FULL_BLOCK
        remaining, fully_owned = ms.strip_toml_block(existing, self.SECTION)
        self.assertFalse(fully_owned)
        self.assertIsNotNone(remaining)
        assert remaining is not None
        self.assertNotIn(self.SECTION, remaining)
        self.assertIn("[other]", remaining)
        self.assertIn('key = "value"', remaining)

    def test_returns_existing_when_no_kit_block(self):
        existing = '[other]\nkey = "value"\n'
        remaining, fully_owned = ms.strip_toml_block(existing, self.SECTION)
        self.assertFalse(fully_owned)
        self.assertEqual(remaining, existing)

    def test_strips_only_kit_block_from_middle(self):
        existing = (
            '[first]\na = 1\n\n'
            + self.FULL_BLOCK + '\n'
            + '[last]\nb = 2\n'
        )
        remaining, fully_owned = ms.strip_toml_block(existing, self.SECTION)
        self.assertFalse(fully_owned)
        assert remaining is not None
        self.assertIn("[first]", remaining)
        self.assertIn("a = 1", remaining)
        self.assertIn("[last]", remaining)
        self.assertIn("b = 2", remaining)
        self.assertNotIn(self.SECTION, remaining)
        self.assertNotIn("qmd", remaining)

    def test_user_comments_outside_kit_block_preserved_after_strip(self):
        existing = (
            '# my precious comment\n'
            + '[other]\nkey = "value"\n\n'
            + self.FULL_BLOCK
        )
        remaining, fully_owned = ms.strip_toml_block(existing, self.SECTION)
        self.assertFalse(fully_owned)
        assert remaining is not None
        self.assertIn("# my precious comment", remaining)
        self.assertIn("[other]", remaining)
        self.assertNotIn(self.SECTION, remaining)
        self.assertNotIn("qmd", remaining)


class EnvMarkedMergeTests(unittest.TestCase):
    """ENV merge: uses ``marked_section_strategy`` with shell-comment markers.

    Markers are ``# vibe-engineering second-brain:begin`` / ``end`` — NOT HTML.
    """

    BEGIN = "# vibe-engineering second-brain:begin\n"
    END = "# vibe-engineering second-brain:end\n"

    def test_markers_are_shell_comments_not_html(self):
        self.assertNotIn("<!--", self.BEGIN)
        self.assertNotIn("-->", self.BEGIN)
        self.assertNotIn("<!--", self.END)
        self.assertNotIn("-->", self.END)

    def test_merge_prepends_marked_section_when_no_markers(self):
        merged, action = ms.marked_section_strategy(
            "KIT_VAR=second_brain\n", "USER=1\nOTHER=2\n", self.BEGIN, self.END
        )
        self.assertEqual(action, "merge")
        self.assertIn(self.BEGIN, merged)
        self.assertIn(self.END, merged)
        self.assertIn("KIT_VAR=second_brain", merged)
        self.assertIn("USER=1", merged)
        self.assertIn("OTHER=2", merged)
        # User content appears after kit block
        self.assertTrue(merged.index("USER=1") > merged.index(self.END))

    def test_merge_replaces_between_markers(self):
        existing = (
            self.BEGIN + "OLD_VAR=stale\n" + self.END
            + "USER=1\n"
        )
        merged, action = ms.marked_section_strategy(
            "KIT_VAR=second_brain\n", existing, self.BEGIN, self.END
        )
        self.assertEqual(action, "merge")
        self.assertIn("KIT_VAR=second_brain", merged)
        self.assertNotIn("OLD_VAR=stale", merged)
        self.assertIn("USER=1", merged)

    def test_strip_removes_marked_section_keeps_unrelated_lines(self):
        existing = (
            "USER=1\n"
            + self.BEGIN + "KIT_VAR=second_brain\n" + self.END
            + "OTHER=2\n"
        )
        remaining, fully_owned = ms.strip_marked_section(
            existing, self.BEGIN, self.END
        )
        self.assertFalse(fully_owned)
        assert remaining is not None
        self.assertIn("USER=1", remaining)
        self.assertIn("OTHER=2", remaining)
        self.assertNotIn("KIT_VAR=second_brain", remaining)
        self.assertNotIn(self.BEGIN, remaining)
        self.assertNotIn(self.END, remaining)

    def test_strip_returns_none_when_only_kit_section(self):
        existing = self.BEGIN + "KIT_VAR=second_brain\n" + self.END
        remaining, fully_owned = ms.strip_marked_section(
            existing, self.BEGIN, self.END
        )
        self.assertTrue(fully_owned)
        self.assertIsNone(remaining)

    def test_strip_returns_unchanged_when_no_markers(self):
        existing = "USER=1\nOTHER=2\n"
        remaining, fully_owned = ms.strip_marked_section(
            existing, self.BEGIN, self.END
        )
        self.assertFalse(fully_owned)
        self.assertEqual(remaining, existing)


if __name__ == "__main__":
    unittest.main()
