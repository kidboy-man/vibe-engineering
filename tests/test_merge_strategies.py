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


if __name__ == "__main__":
    unittest.main()
