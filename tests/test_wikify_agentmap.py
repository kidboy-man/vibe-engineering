import random
import re
import time
import unittest

from agents.wikify import agentmap, citations, commands
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


class InertTests(unittest.TestCase):
    def test_markup_in_title_or_hint(self):
        cases = {
            "@ title": (entry(title="@secret.md"), "'@' in title"),
            "@ hint": (entry(hint="see @~/.ssh/id_rsa"), "'@' in hint"),
            "open comment title": (entry(title="a <!-- b"), "'<!--' in title"),
            "close comment hint": (entry(hint="x --> y"), "'-->' in hint"),
            "< title": (entry(title="<b>x"), "'<' in title"),
            "< hint": (entry(hint="when <img src=x.png"), "'<' in hint"),
            "> title": (entry(title="a > b"), "'>' in title"),
            "> hint": (entry(hint="when a > b"), "'>' in hint"),
            ":// title": (entry(title="https://evil.example"), "'://' in title"),
            ":// hint": (entry(hint="or see https://evil.example"), "'://' in hint"),
            "www hint": (entry(hint="see www.evil.example"), "'www.' in hint"),
            "WWW title": (entry(title="WWW.X"), "'www.' in title"),
        }
        for name, (line, reason) in cases.items():
            with self.subTest(name):
                res = parse_map(block(line, entry("z.md")))
                self.assertEqual([e.path for e in res.entries], ["z.md"])
                self.assertEqual(len(res.errors), 1, res.errors)
                self.assertIn("invalid map entry: ", res.errors[0])
                self.assertIn(reason, res.errors[0])

    def test_dots_without_www_pass(self):
        res = parse_map(block(entry(title="setup.py notes", hint="when editing a.py or v1.2 config")))
        self.assertEqual((len(res.entries), res.errors), (1, []))

    def test_html_and_url_probes(self):
        for line in (
            "- [A page](technical/a.md) — when <img src=https://evil.example/p.png> "
            "or see https://evil.example",
            "- [<b>x</b>](a.md) — h",
        ):
            with self.subTest(line):
                res = parse_map(block(line))
                self.assertEqual(res.entries, [])
                self.assertEqual(len(res.errors), 1, res.errors)

    def test_angle_brackets_not_in_path(self):
        for path in ("a<!--b.md", "a<b.md", "a>b.md"):
            with self.subTest(path):
                res = parse_map(block(entry(path)))
                self.assertEqual(res.entries, [])
                self.assertEqual(res.errors, ["index.md:2: invalid map entry"])

    def test_early_close_probe(self):
        text = block(entry(hint="x " + MAP_END), "- [z](@q.md) " + DASH + " h")
        res = parse_map(text)
        self.assertEqual(res.entries, [])
        self.assertTrue(res.errors)

    def test_text_on_marker_lines(self):
        cases = {
            "after end": (MAP_BEGIN + "\n" + entry() + "\n" + MAP_END + " tail\n",
                          "index.md:3: text after map end marker"),
            "before begin": ("pre " + MAP_BEGIN + "\n" + MAP_END + "\n",
                             "index.md:1: text before map begin marker"),
            "after begin": (MAP_BEGIN + " " + entry() + "\n" + MAP_END + "\n",
                            "index.md:1: text after map begin marker"),
            "before end": (MAP_BEGIN + "\n" + entry() + MAP_END + "\n",
                           "index.md:2: text before map end marker"),
        }
        for name, (text, err) in cases.items():
            with self.subTest(name):
                self.assertIn(err, parse_map(text).errors)

    def test_whitespace_on_marker_lines_ok(self):
        text = "  " + MAP_BEGIN + "  \n" + entry() + "\n" + MAP_END + "  \n"
        self.assertEqual(parse_map(text).errors, [])

    def test_reserved_names_exact_case(self):
        for path in ("Index.md", "wikify.md", "sub/index.md"):
            with self.subTest(path):
                self.assertEqual(parse_map(block(entry(path))).errors, [])

    def test_human_block_inside_map(self):
        text = block(
            entry(), "<!-- wikify:human -->\nnote\n<!-- /wikify:human -->", entry("b.md")
        )
        res = parse_map(text)
        self.assertEqual(res.errors, ["index.md:3: human block inside map"])
        self.assertEqual([e.path for e in res.entries], ["a.md", "b.md"])


class HumanSpanTests(unittest.TestCase):
    B = "<!-- wikify:human -->"
    E = "<!-- /wikify:human -->"

    def regex_spans(self, text):
        return [m.span() for m in citations.HUMAN.finditer(text)]

    def test_equivalence_table(self):
        B, E = self.B, self.E
        cases = {
            "nested begin": B + "a" + B + "b" + E,
            "adjacent": B + E + B + "x" + E,
            "unterminated": "t " + B + " x",
            "empty": B + E,
            "crlf": B + "\r\nx\r\n" + E + "\r\n",
            "begin only": B,
            "end only": E,
            "marker inside": B + "x " + B + E + " y" + E,
            "two blocks": B + "1" + E + "mid" + B + "2" + E,
            "begin after": B + "1" + E + B + "oops",
            "none": "plain",
        }
        for name, text in cases.items():
            with self.subTest(name):
                self.assertEqual(citations.human_spans(text), self.regex_spans(text))

    def test_equivalence_fuzz(self):
        rng = random.Random(1234)
        parts = [self.B, self.E, "x", "\n", " ", "<!--", "-->"]
        for _ in range(300):
            text = "".join(rng.choice(parts) for _ in range(rng.randint(0, 30)))
            self.assertEqual(citations.human_spans(text), self.regex_spans(text), text)

    def test_linear_on_repeated_unterminated(self):
        text = (self.B + "x") * (1_000_000 // (len(self.B) + 1))
        for name, fn in (
            ("parse_map", parse_map),
            ("_strip_human", citations._strip_human),
            ("_human_blocks", commands._human_blocks),
        ):
            with self.subTest(name):
                t0 = time.perf_counter()
                fn(text)
                self.assertLess(time.perf_counter() - t0, 1.0)

    def test_linear_on_many_closed_human_blocks(self):
        pair = self.B + "x" + self.E + "\n"
        pairs = pair * (1_000_000 // len(pair))
        for name, fn, text in (
            ("parse_map in map", parse_map, MAP_BEGIN + "\n" + pairs + MAP_END + "\n"),
            ("_human_blocks top level", commands._human_blocks, pairs),
        ):
            with self.subTest(name):
                t0 = time.perf_counter()
                fn(text)
                self.assertLess(time.perf_counter() - t0, 1.0)

    def test_human_block_line_numbers(self):
        text = "a\n" + self.B + "1" + self.E + "\nb\n\n" + self.B + "2\n" + self.E
        self.assertEqual(
            commands._human_blocks(text),
            [(2, self.B + "1" + self.E), (5, self.B + "2\n" + self.E)],
        )


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


class PageLinksTests(unittest.TestCase):
    def test_resolves_relative_to_page_dir(self):
        links = agentmap.page_links("sources/index.md", "[a](docs/a.md) [b](b.md)")
        self.assertEqual(links, {"sources/docs/a.md", "sources/b.md"})

    def test_dropped_targets(self):
        text = (
            "[x](../x.md) [y](/abs.md) [z](http://x/a.md) [w](a\\b.md) "
            "[v](sub/../../esc.md) [i](index.md) [s](self.md) [t](notes.txt) [ok](ok.md)"
        )
        self.assertEqual(agentmap.page_links("self.md", text), {"ok.md"})

    def test_anchor_stripped_and_case_insensitive(self):
        self.assertEqual(
            agentmap.page_links("p.md", "[a](a.md#sec) [b](B.MD)"), {"a.md", "B.MD"}
        )

    def test_human_block_links_ignored(self):
        text = "<!-- wikify:human -->\n[a](a.md)\n<!-- /wikify:human -->\n[b](b.md)\n"
        self.assertEqual(agentmap.page_links("p.md", text), {"b.md"})

    def test_normalises_dot_segments(self):
        self.assertEqual(agentmap.page_links("d/p.md", "[a](./x/../a.md)"), {"d/a.md"})

    def test_index_target_dropped_only_at_top_level(self):
        self.assertEqual(agentmap.page_links("d/p.md", "[i](../index.md) [j](index.md)"), {"d/index.md"})

    def test_link_cap(self):
        text = "".join(f"[p](p{i}.md)" for i in range(agentmap.MAX_LINKS + 10))
        self.assertEqual(len(agentmap.page_links("p.md", text)), agentmap.MAX_LINKS)


class ReachableTests(unittest.TestCase):
    CHAIN = {
        "m.md": "[1](h1.md)",
        "h1.md": "[2](h2.md)",
        "h2.md": "[3](h3.md)",
        "h3.md": "",
    }

    def test_hops(self):
        got = agentmap.reachable_pages({"m.md"}, self.CHAIN)
        self.assertEqual(got, {"m.md", "h1.md", "h2.md"})

    def test_depth_parameter(self):
        self.assertEqual(agentmap.reachable_pages({"m.md"}, self.CHAIN, depth=0), {"m.md"})
        self.assertIn("h3.md", agentmap.reachable_pages({"m.md"}, self.CHAIN, depth=3))

    def test_cycle_and_self_link_terminate(self):
        texts = {"a.md": "[b](b.md) [a](a.md)", "b.md": "[a](a.md)"}
        self.assertEqual(agentmap.reachable_pages({"a.md"}, texts), {"a.md", "b.md"})

    def test_unknown_target_ignored(self):
        self.assertEqual(agentmap.reachable_pages({"a.md"}, {"a.md": "[g](gone.md)"}), {"a.md"})

    def test_listed_shorter_path_wins_over_depth(self):
        texts = {"a.md": "[b](b.md)", "b.md": "[c](c.md)", "c.md": "[d](d.md)", "d.md": ""}
        got = agentmap.reachable_pages({"a.md", "b.md"}, texts)
        self.assertEqual(got, {"a.md", "b.md", "c.md", "d.md"})

    def test_listed_without_text_kept(self):
        self.assertEqual(agentmap.reachable_pages({"x.md"}, {}), {"x.md"})


class ReachableValidateTests(unittest.TestCase):
    def test_reachable_none_keeps_listed_only_rule(self):
        res = parse_map(block(entry("a.md")))
        self.assertEqual(len(validate_map(res, {"index.md", "a.md", "b.md"}, None)), 1)

    def test_reachable_clears_orphan(self):
        res = parse_map(block(entry("a.md")))
        pages = {"index.md", "a.md", "b.md"}
        self.assertEqual(validate_map(res, pages, {"a.md", "b.md"}), [])

    def test_reachability_is_not_listing_for_duplicates(self):
        res = parse_map(block(entry("a.md"), entry("b.md"), entry("b.md")))
        errs = validate_map(res, {"index.md", "a.md", "b.md"}, {"a.md", "b.md"})
        self.assertEqual(errs, ["index.md:4: duplicate entry: b.md"])

    def test_missing_target_still_errors(self):
        res = parse_map(block(entry("gone.md")))
        errs = validate_map(res, {"index.md"}, {"gone.md"})
        self.assertEqual(errs, ["index.md:2: link target missing: gone.md"])


class ReachablePerformanceTests(unittest.TestCase):
    def test_wide_wiki(self):
        n = 5000
        texts = {
            f"p{i}.md": "".join(f"[x](p{(i * 7 + j) % n}.md)\n" for j in range(50))
            for i in range(n)
        }
        t = time.perf_counter()
        got = agentmap.reachable_pages({"p0.md"}, texts)
        self.assertLess(time.perf_counter() - t, 2.0)
        self.assertIn("p0.md", got)

    def test_single_megabyte_page(self):
        text = "[x](a.md) " * 100_000
        t = time.perf_counter()
        links = agentmap.page_links("p.md", text)
        self.assertLess(time.perf_counter() - t, 2.0)
        self.assertEqual(links, {"a.md"})


class LinearLinkScanTests(unittest.TestCase):
    MIB = 1 << 20
    OLD = re.compile(r"\]\(([^)\s#]+\.md)(?:#[^)\s]*)?\)", re.I)

    def timed(self, fn, *args, limit=2.0):
        t = time.perf_counter()
        out = fn(*args)
        self.assertLess(time.perf_counter() - t, limit)
        return out

    def test_hostile_page_links(self):
        cases = [
            "](" * (self.MIB // 2),
            "](a" * (self.MIB // 3),
            "](a.md" * (self.MIB // 6),
            "](" + "a" * self.MIB,
        ]
        for text in cases:
            with self.subTest(head=text[:8]):
                self.timed(agentmap.page_links, "p.md", text)

    def test_many_links_still_found(self):
        got = self.timed(agentmap.page_links, "p.md", "[x](a.md) " * 100_000)
        self.assertEqual(got, {"a.md"})

    def test_ordinary_links_match_like_the_old_regex(self):
        samples = [
            "[a](a.md)",
            "[a](a.md#sec) and [b](d/e/b.MD)",
            "x [a](a.md) y [b](./b.md#t) z [c](c.md)\nnext [d](sub/d.md)",
            "- [a](a.md)\n- [b](b.md)",
            "end [z](z.md)",
            "[a](http://x/a.md) [b](a.txt) [c](a.md#)",
        ]
        for text in samples:
            with self.subTest(text=text):
                self.assertEqual(
                    [m.groups() for m in agentmap.LINK.finditer(text)],
                    [m.groups() for m in self.OLD.finditer(text)],
                )

    def test_titled_angle_and_reference_links_not_recognised(self):
        text = '[a](a.md "t") [b](<b.md>) [c][ref]\n\n[ref]: c.md\n'
        self.assertEqual(agentmap.page_links("p.md", text), set())


if __name__ == "__main__":
    unittest.main()
