import unittest

from agents.wikify import agentmap
from agents.wikify.agentmap import MAP_BEGIN, MAP_END, parse_map, strip_map, validate_map

DASH = "—"


def entry(path="a.md", title="A", hint="about a", dash=DASH):
    return f"- [{title}]({path}) {dash} {hint}"


def block(*lines):
    return "\n".join([MAP_BEGIN, *lines, MAP_END]) + "\n"


class ParseTests(unittest.TestCase):
    def test_valid_single_entry(self):
        res = parse_map("# Wiki\n\n" + block(entry()))
        self.assertEqual(res.errors, [])
        self.assertEqual(res.blocks, 1)
        self.assertEqual(
            res.entries, [agentmap.Entry("a.md", "A", "about a", 4)]
        )

    def test_no_block_is_opt_in(self):
        res = parse_map("# Wiki\n- [x](a.md) not a map\n")
        self.assertEqual((res.entries, res.errors, res.blocks), ([], [], 0))

    def test_entry_cap(self):
        for n, ok in ((60, True), (61, False)):
            with self.subTest(n=n):
                lines = [entry(f"p{i}.md", "T", "h") for i in range(n)]
                res = parse_map(block(*lines))
                self.assertEqual(not res.errors, ok, res.errors)
                if not ok:
                    self.assertTrue(any("map exceeds 60 entries" in e for e in res.errors))

    def test_byte_cap_is_exact(self):
        # Body between markers: "\n" + lines + "\n"; pad with blank-line newlines.
        line = entry()
        base = len(("\n" + line + "\n").encode())
        for total, ok in ((6144, True), (6145, False)):
            with self.subTest(total=total):
                text = MAP_BEGIN + "\n" + line + "\n" * (total - base + 1) + MAP_END
                res = parse_map(text)
                self.assertEqual(not res.errors, ok, res.errors)
                if not ok:
                    self.assertTrue(any("map exceeds 6144 bytes" in e for e in res.errors))

    def test_byte_cap_counts_utf8_bytes(self):
        text = block(entry(hint="é" * 80)) * 1
        self.assertEqual(parse_map(text).errors, [])
        lines = [entry(f"p{i}.md", "T" * 60, "é" * 80) for i in range(40)]
        res = parse_map(block(*lines))
        self.assertTrue(any("6144 bytes" in e for e in res.errors))

    def test_bad_entries(self):
        cases = {
            "missing hint": f"- [A](a.md) {DASH} ",
            "no hint at all": "- [A](a.md)",
            "hint 81": entry(hint="h" * 81),
            "title 61": entry(title="t" * 61),
            "empty title": entry(title=""),
            "@": entry("@a.md"),
            "..": entry("../a.md"),
            "abs": entry("/a.md"),
            "scheme": entry("http://x/a.md"),
            "colon": entry("a:b.md"),
            "backslash": entry("a\\b.md"),
            "txt": entry("a.txt"),
            "index": entry("index.md"),
            "wikify": entry("WIKIFY.md"),
            "paren title": entry(title="a(b)"),
            "bracket title": entry(title="a[b]"),
            "paren hint": entry(hint="a(b)"),
            "bracket hint": entry(hint="a[b]"),
            "hyphen dash": entry(dash="-"),
            "en dash": entry(dash="–"),
            "prose": "some stray prose",
        }
        for name, line in cases.items():
            with self.subTest(name):
                res = parse_map(block(line))
                self.assertEqual(res.entries, [])
                self.assertEqual(len(res.errors), 1, res.errors)
                self.assertTrue(res.errors[0].startswith("index.md:2: "), res.errors)

    def test_good_nested_path_and_uppercase_ext(self):
        res = parse_map(block(entry("sub/dir/b.MD"), entry("sub/index.md")))
        self.assertEqual(res.errors, [])
        self.assertEqual(len(res.entries), 2)

    def test_two_blocks(self):
        res = parse_map(block(entry()) + block(entry("b.md")))
        self.assertEqual(res.blocks, 2)
        self.assertTrue(any("more than one map block" in e for e in res.errors))

    def test_unterminated(self):
        res = parse_map("x\n" + MAP_BEGIN + "\n" + entry() + "\n")
        self.assertEqual(res.blocks, 1)
        self.assertEqual(len(res.errors), 1)
        self.assertTrue(res.errors[0].startswith("index.md:2: "))

    def test_block_inside_human_ignored(self):
        text = "<!-- wikify:human -->\n" + block(entry("@bad.md")) + "<!-- /wikify:human -->\n"
        res = parse_map(text)
        self.assertEqual((res.entries, res.errors, res.blocks), ([], [], 0))

    def test_line_numbers_with_human_block_above(self):
        text = "<!-- wikify:human -->\nnote\nmore\n<!-- /wikify:human -->\n" + block(
            entry(), "prose"
        )
        res = parse_map(text)
        self.assertEqual(res.entries[0].line, 6)
        self.assertEqual(res.errors, ["index.md:7: invalid map entry"])

    def test_strip_map_keeps_line_count(self):
        text = "# T\n\n" + block(entry(), "", entry("b.md")) + "\ntail\n"
        out = strip_map(text)
        self.assertEqual(out.count("\n"), text.count("\n"))
        self.assertNotIn(MAP_BEGIN, out)
        self.assertNotIn("a.md", out)
        self.assertTrue(out.startswith("# T\n\n") and out.endswith("tail\n"))

    def test_strip_map_no_block_or_human_only(self):
        self.assertEqual(strip_map("hello\n"), "hello\n")
        human = "<!-- wikify:human -->\n" + block(entry()) + "<!-- /wikify:human -->\n"
        self.assertEqual(strip_map(human), human)


class ValidateTests(unittest.TestCase):
    def test_no_block_returns_empty(self):
        self.assertEqual(validate_map(parse_map("hi\n"), {"index.md", "a.md"}), [])

    def test_ok(self):
        res = parse_map(block(entry("a.md"), entry("d/b.md")))
        self.assertEqual(validate_map(res, {"index.md", "a.md", "d/b.md"}), [])

    def test_missing_target(self):
        res = parse_map(block(entry("a.md"), entry("gone.md")))
        self.assertEqual(
            validate_map(res, {"index.md", "a.md"}),
            ["index.md:3: link target missing: gone.md"],
        )

    def test_duplicate(self):
        res = parse_map(block(entry("a.md"), entry("a.md")))
        self.assertEqual(
            validate_map(res, {"index.md", "a.md"}),
            ["index.md:3: duplicate entry: a.md"],
        )

    def test_orphan(self):
        res = parse_map(block(entry("a.md")))
        self.assertEqual(
            validate_map(res, {"index.md", "a.md", "d/c.md"}),
            ["index.md:1: page not reachable from the map: d/c.md"],
        )

    def test_nested_index_must_be_listed(self):
        res = parse_map(block(entry("a.md")))
        errs = validate_map(res, {"index.md", "a.md", "sub/index.md"})
        self.assertEqual(len(errs), 1)
        self.assertIn("sub/index.md", errs[0])

    def test_empty_block_requires_pages(self):
        res = parse_map(block())
        self.assertEqual(validate_map(res, {"index.md"}), [])
        self.assertEqual(len(validate_map(res, {"index.md", "a.md"})), 1)


if __name__ == "__main__":
    unittest.main()
