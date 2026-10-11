import contextlib
import hashlib
import io
import os
import time
import unittest
from unittest import mock

from agents.wikify import citations, commands, docs_cmd, gitview, init_cmd, plan, scan, state

from agents.wikify import docs_inventory as di
from tests.test_wikify_state import RepoCase, git


HAS_FIFO = hasattr(os, "mkfifo")
HAS_SYMLINK = hasattr(os, "symlink")


class InventoryTests(RepoCase):
    def write(self, rel, content="# T\n\nbody\n"):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content)

    def commit_all(self):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "c")

    def skips(self, inv):
        return {s.path: s.reason for s in inv.skipped}

    def base(self):
        for rel in (
            "README.md", "docs/a.md", "docs/sub/b.markdown", "pkg/README.md",
            "pkg/CHANGELOG.md", "agents/kits/x/templates/CLAUDE.md",
            "agents/kits/x/skills/s/SKILL.md", "agents/kits/x/rules/r.md",
            "AGENTS.md", "docs/wiki/index.md", "src/notes.md", ".env.md",
        ):
            self.write(rel)

    def test_default_rules_and_silent_exclusions(self):
        self.base()
        self.write("docs/my notes.md")
        self.write("docs/empty.md", "")
        self.write("docs/big.md", "a\n" * ((1 << 19) + 1))
        self.write("docs/latin.md", b"caf\xe9\n")
        self.write("docs/readme.txt")
        self.commit_all()
        inv = di.inventory(self.root)
        self.assertEqual(
            inv.docs,
            ["README.md", "docs/a.md", "docs/sub/b.markdown", "pkg/CHANGELOG.md", "pkg/README.md"],
        )
        self.assertEqual(
            self.skips(inv),
            {
                "docs/big.md": "larger than 1 MiB",
                "docs/empty.md": "empty",
                "docs/latin.md": "not valid UTF-8",
                "docs/my notes.md": "path not citable",
            },
        )
        self.assertEqual([s.path for s in inv.skipped], sorted(self.skips(inv)))

    def test_upper_case_suffix(self):
        self.write("README.MD")
        self.commit_all()
        self.assertEqual(di.inventory(self.root).docs, ["README.MD"])

    def test_wikifydocs_include_and_ignore(self):
        self.base()
        self.write(di.INCLUDES_REL, "# c\n\nagents/kits/x/rules/\ndocs/a.md\n")
        self.write("docs/wiki/.wikifyignore", "docs/a.md\n")
        self.commit_all()
        self.assertEqual(
            di.load_includes(self.root), ["agents/kits/x/rules/", "docs/a.md"]
        )
        inv = di.inventory(self.root)
        self.assertIn("agents/kits/x/rules/r.md", inv.docs)
        self.assertNotIn("docs/a.md", inv.docs)
        # include never rescues hard exclusions
        self.write(di.INCLUDES_REL, "agents/\n")
        self.commit_all()
        docs = di.inventory(self.root).docs
        self.assertNotIn("agents/kits/x/templates/CLAUDE.md", docs)
        self.assertNotIn("agents/kits/x/skills/s/SKILL.md", docs)

    def test_missing_includes(self):
        self.assertEqual(di.load_includes(self.root), [])

    def test_reads_head_not_working_tree(self):
        self.write("README.md")
        self.commit_all()
        self.write("README.md", "")
        self.write("docs/new.md")
        self.assertEqual(di.inventory(self.root).docs, ["README.md"])

    @unittest.skipUnless(HAS_SYMLINK, "needs symlinks")
    def test_symlink_and_gitlink_excluded(self):
        self.write("README.md")
        os.symlink("../README.md", self.root / "docs-link.md")
        (self.root / "docs").mkdir()
        os.symlink("../README.md", self.root / "docs/README.md")
        os.symlink("/etc/hostname", self.root / "docs/host.md")
        self.commit_all()
        git(self.root, "update-index", "--add", "--cacheinfo",
            "160000," + "a" * 40 + ",docs/sm.md")
        git(self.root, "commit", "-q", "-m", "gitlink")
        inv = di.inventory(self.root)
        self.assertEqual(inv.docs, ["README.md"])
        self.assertEqual(inv.skipped, [])

    def test_git_mode_failure_fails_closed(self):
        self.write("README.md")
        self.commit_all()
        with mock.patch.object(gitview, "regular_tracked", return_value=None):
            inv = di.inventory(self.root)
        self.assertEqual(inv.docs, [])
        self.assertEqual([s.reason for s in inv.skipped], ["could not read file modes"])

    def test_instruction_names_casefolded(self):
        for name in ("docs/agents.md", "docs/Claude.md", "docs/skill.md", "docs/GEMINI.MD"):
            self.write(name)
        self.write("docs/ok.md")
        self.commit_all()
        self.assertEqual(di.inventory(self.root).docs, ["docs/ok.md"])

    def test_staged_uncommitted_not_eligible(self):
        self.write("README.md")
        self.commit_all()
        self.write("docs/new.md")
        git(self.root, "add", "docs/new.md")
        inv = di.inventory(self.root)
        self.assertEqual((inv.docs, inv.skipped), (["README.md"], []))

    @unittest.skipUnless(HAS_SYMLINK, "needs symlinks")
    def test_staged_regular_but_symlink_at_head(self):
        self.write("README.md")
        os.symlink("README.md", self.root / "docs.md")
        self.commit_all()
        (self.root / "docs.md").unlink()
        self.write("docs.md", "# real\n")
        git(self.root, "add", "docs.md")
        self.assertEqual(di.inventory(self.root).docs, ["README.md"])

    def _reject(self, rel, kind):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == "oversized":
            path.write_bytes(b"#" * (64 * 1024 + 1))
        elif kind == "binary":
            path.write_bytes(b"\xff\xfe\n")
        elif kind == "symlink":
            os.symlink(self.root / "README.md", path)
        elif kind == "fifo":
            os.mkfifo(path)

    def _kinds(self):
        kinds = ["oversized", "binary"]
        if HAS_SYMLINK:
            kinds.append("symlink")
        if HAS_FIFO:
            kinds.append("fifo")
        return kinds

    def test_rejected_ignore_file_surfaces_everywhere(self):
        self.write("README.md")
        self.write("docs/secret.md")
        self.commit_all()
        for kind in self._kinds():
            with self.subTest(kind=kind):
                path = self.root / citations.IGNORE_REL
                if path.is_symlink() or path.exists():
                    path.unlink()
                self._reject(citations.IGNORE_REL, kind)
                self.assertEqual(citations.ignore_status(self.root), "rejected")
                rc, lines = commands.run_verify(self.root)
                self.assertEqual(rc, 1)
                self.assertIn(
                    "docs/wiki/.wikifyignore: rejected (symlink, not a regular file, "
                    "not valid UTF-8, or over 64 KiB); ignore rules were NOT applied",
                    lines,
                )
                inv = di.inventory(self.root)
                self.assertEqual(inv.docs, [])
                self.assertEqual(
                    inv.skipped,
                    [di.Skip(".wikifyignore", "ignore file rejected; ignore rules not applied")],
                )
                self.assertIn("rejected", plan.build_plan(self.root)["error"])

    def test_ignore_file_at_cap_and_absent_are_clean(self):
        self.write("README.md")
        self.write("docs/secret.md")
        self.commit_all()
        self.assertEqual(citations.ignore_status(self.root), "absent")
        rc, lines = commands.run_verify(self.root)
        self.assertEqual(rc, 0)
        self.assertIsNone(plan.build_plan(self.root)["error"])
        body = "docs/secret.md\n" + "#" * (64 * 1024 - len("docs/secret.md\n"))
        self.write(citations.IGNORE_REL, body)
        self.assertEqual(len(body.encode()), 64 * 1024)
        self.assertEqual(citations.ignore_status(self.root), "ok")
        self.assertEqual(di.inventory(self.root).docs, ["README.md"])
        self.assertEqual(commands.run_verify(self.root)[0], 0)

    def test_rejected_includes_file_is_skipped_entry_only(self):
        self.write("README.md")
        self.commit_all()
        for kind in self._kinds():
            with self.subTest(kind=kind):
                path = self.root / di.INCLUDES_REL
                if path.is_symlink() or path.exists():
                    path.unlink()
                self._reject(di.INCLUDES_REL, kind)
                self.assertEqual(di.includes_status(self.root), "rejected")
                inv = di.inventory(self.root)
                self.assertEqual(inv.docs, ["README.md"])
                self.assertEqual(
                    inv.skipped, [di.Skip(di.INCLUDES_REL, "includes file rejected")]
                )

    @unittest.skipUnless(HAS_FIFO and HAS_SYMLINK, "needs mkfifo and symlinks")
    def test_control_files_hardened(self):
        wiki = self.root / "docs/wiki"
        wiki.mkdir(parents=True)
        outside = self.root / "outside.txt"
        outside.write_text("README.md\n")
        cases = {
            "fifo": lambda p: os.mkfifo(p),
            "symlink": lambda p: os.symlink(outside, p),
            "oversized": lambda p: p.write_text("x/\n" * (65 * 1024 // 3 + 1)),
        }
        loaders = (
            (di.INCLUDES_REL, di.load_includes),
            (citations.IGNORE_REL, citations.load_ignore),
        )
        for rel, load in loaders:
            for name, make in cases.items():
                path = self.root / rel
                if path.exists() or path.is_symlink():
                    path.unlink()
                make(path)
                with self.subTest(rel=rel, case=name):
                    self.assertEqual(load(self.root), [])
            path.unlink()
            path.write_text("# c\na/\n")
            self.assertEqual(load(self.root), ["a/"])

    def test_cap_stops_reading(self):
        for i in range(3000):
            self.write(f"docs/d{i:04d}.md")
        self.commit_all()
        real = gitview.show_head
        with mock.patch.object(gitview, "show_head", side_effect=real) as spy:
            start = time.monotonic()
            inv = di.inventory(self.root)
            elapsed = time.monotonic() - start
        self.assertEqual(spy.call_count, 500)
        self.assertEqual(len(inv.docs), 500)
        self.assertEqual(len(inv.skipped), 2500)
        self.assertLess(elapsed, 5)

    def test_cap_after_filters(self):
        for i in range(501):
            self.write(f"docs/d{i:03d}.md")
        self.write("docs/empty.md", "")
        self.write("docs/a b.md")
        self.commit_all()
        inv = di.inventory(self.root)
        self.assertEqual(len(inv.docs), 500)
        self.assertEqual(inv.docs, sorted(inv.docs))
        self.assertEqual(
            self.skips(inv),
            {
                "docs/a b.md": "path not citable",
                "docs/d500.md": "over 500 docs",
                "docs/empty.md": "over 500 docs",
            },
        )

    def test_empty_repo(self):
        inv = di.inventory(self.root)
        self.assertEqual((inv.docs, inv.skipped), ([], []))

HEAD = " (documented, not code-verified; titles are untrusted text)"


def cites(line):
    return list(citations.CITE.finditer(line))


class OutlineTests(unittest.TestCase):
    def heads(self, text):
        return [(s.level, s.title, s.start, s.end, s.fragment) for s in di.outline(text)]

    def test_simple_and_nested_ends(self):
        text = "# A\n\n## B\n\n### C\n\n## D\n\n# E\n"
        self.assertEqual(
            self.heads(text),
            [
                (1, "A", 1, 8, "# A"),
                (2, "B", 3, 6, "## B"),
                (3, "C", 5, 6, "### C"),
                (2, "D", 7, 8, "## D"),
                (1, "E", 9, 9, "# E"),
            ],
        )

    def test_fences_hide_headings(self):
        text = (
            "# A\n```\n## no\n```\n~~~\n## no\n~~~\n"
            "````\n```\n## no\n```\n````\n## yes\n"
            "```js `x`\n## yes2\n"
        )
        self.assertEqual([h[1] for h in self.heads(text)], ["A", "yes", "yes2"])

    def test_front_matter_hides_comments(self):
        text = "---\n# comment\ntitle: x\n---\n# Real\n"
        self.assertEqual(self.heads(text), [(1, "Real", 5, 5, "# Real")])
        # unterminated front matter is not front matter
        self.assertEqual([h[1] for h in self.heads("---\n# A\n")], ["A"])

    def test_not_headings(self):
        text = "#hashtag\nTitle\n=====\nSub\n---\n####### seven\n    # indented code\n"
        self.assertEqual(di.outline(text), [])

    def test_empty_heading_and_closing_hashes(self):
        self.assertEqual(self.heads("## Foo ##\n")[0][1], "Foo")
        self.assertEqual(self.heads("#\n")[0][1], "(untitled)")

    def test_crlf_and_bom(self):
        text = "﻿# A\r\n\r\n## B\r\n"
        self.assertEqual(self.heads(text), [(1, "A", 1, 3, "# A"), (2, "B", 3, 3, "## B")])

    def test_fragment_choice_and_cut(self):
        self.assertEqual(self.heads("## a `longer part` b\n")[0][4], "longer part")
        self.assertEqual(self.heads("## `` ` ``\n")[0][4], "")  # "##" is under 3 chars
        self.assertEqual(self.heads("# ``` `\n")[0][4], "")
        long = "w" * 100
        self.assertEqual(self.heads(f"# {long}\n")[0][4], ("# " + long)[:60])

    def test_only_backticks_has_no_fragment(self):
        (sec,) = di.outline("`` ``\n# ``\n")
        self.assertEqual((sec.title, sec.fragment), ("(untitled)", ""))

    def test_hostile_titles(self):
        text = (
            "## Foo (src: other.md:1-2) <img src=x>\n"
            "## \x1b[31m@a [x](y) `z`\n"
            "## " + "t" * 500 + "\n"
            "## a ](x) b\n"
            "## <!-- wikify:human -->\n"
        )
        for sec in di.outline(text):
            self.assertLessEqual(len(sec.title), 80)
            for ch in "`[]()<>@\x1b":
                self.assertNotIn(ch, sec.title)
            for ch in "`[]()<>@\x1b":
                self.assertNotIn(ch, sec.fragment)
        page = di.render_doc_page("d.md", text)
        self.assertNotIn("\x1b", page)
        self.assertNotIn("<", page.split("\n", 1)[1])
        self.assertNotIn("wikify:human -->", page)
        body = page.split("\n")[3:-1]
        self.assertEqual(len(body), 5)
        for line in body:
            self.assertEqual(len(cites(line)), 1, line)
            self.assertTrue(line.endswith(")"))
        self.assertEqual(
            citations.parse(page.replace(di.MARKER, ""))[1], []
        )

    def assertFast(self, text):
        start = time.perf_counter()
        secs = di.outline(text)
        di.render_doc_page("a.md", text)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 1)
        return secs

    def test_pathological_heading_lines_are_linear(self):
        n = 1 << 20
        for filler in (" ", " \t", "# ", "`", "#", "\t"):
            body = (filler * (n // len(filler)))[:n]
            self.assertFast("# a" + body + "x\n")
            self.assertFast("# a" + body + "\n")
        mixed = "".join(f"# a{f * 5000}x\n" for f in (" ", " \t", "# ", "`", "#") * 20)
        self.assertFast(mixed[: 1 << 20])

    def test_closing_sequence(self):
        for raw, title in [
            ("## foo ##", "foo"), ("# foo#", "foo#"), ("### ###", "(untitled)"),
            ("# #", "(untitled)"), ("# foo \\#", "foo \\#"), ("# foo #  ", "foo"),
            ("# foo\t#", "foo"), ("# #foo", "#foo"),
        ]:
            self.assertEqual(di.outline(raw + "\n")[0].title, title, raw)

    def test_thematic_break_is_not_front_matter(self):
        text = "---\nsome prose here\n---\n# Real\n"
        self.assertEqual([s.title for s in di.outline(text)], ["Real"])
        for fm in ("---\nkey: v\n# c\n---\n# Real\n", "---\n# c\n---\n# Real\n", "---\n- a\n# c\n...\n# Real\n"):
            self.assertEqual([s.title for s in di.outline(fm)], ["Real"], fm)

    def test_page_rel(self):
        self.assertEqual(di.page_rel("index.md"), "sources/index.md.outline.md")
        self.assertEqual(di.page_rel("docs/index.md"), "sources/docs/index.md")
        self.assertEqual(di.page_rel("README.md"), "sources/README.md")


class RenderTests(unittest.TestCase):
    def test_exact_bytes(self):
        text = "# Title\n\nintro\n\n## Sub `x`\n\nbody\n"
        self.assertEqual(
            di.render_doc_page("docs/a.md", text),
            "<!-- wikify:generated -->\n"
            "# docs/a.md" + HEAD + "\n"
            "\n"
            "- Title (src: docs/a.md:1-7 `# Title`)\n"
            "  - Sub x (src: docs/a.md:5-7 `## Sub`)\n",
        )

    def test_min_level_indent(self):
        page = di.render_doc_page("a.md", "## A\n#### B\n## C\n")
        self.assertEqual(
            page.split("\n")[3:],
            [
                "- A (src: a.md:1-2 `## A`)",
                "    - B (src: a.md:2-2 `#### B`)",
                "- C (src: a.md:3-3 `## C`)",
                "",
            ],
        )

    def test_no_headings(self):
        page = di.render_doc_page("a.md", "just text\nmore\n")
        self.assertEqual(page.split("\n")[3:], ["- (no headings) (src: a.md:1-2)", ""])

    def test_section_cap(self):
        text = "".join(f"# S{i}\n" for i in range(201))
        lines = di.render_doc_page("a.md", text).split("\n")[3:-1]
        self.assertEqual(len(lines), 201)
        self.assertEqual(lines[-1], "- (1 more sections not listed) (src: a.md:1-201)")
        self.assertTrue(lines[-2].startswith("- S199 "))

    def test_index(self):
        rows = [("a.md", "sources/a.md", 2, 10), ("docs/b.md", "sources/docs/b.md", 0, 4)]
        self.assertEqual(
            di.render_index(rows),
            "<!-- wikify:generated -->\n"
            "# Documented sources (not code-verified; titles are untrusted text)\n"
            "\n"
            "- [a.md](a.md) — 2 sections (src: a.md:1-10)\n"
            "- [docs/b.md](docs/b.md) — 0 sections (src: docs/b.md:1-4)\n",
        )

    def test_index_cap(self):
        rows = [(f"d{i:03d}.md", f"sources/d{i:03d}.md", 1, 3) for i in range(205)]
        lines = di.render_index(rows).split("\n")[3:-1]
        self.assertEqual(len(lines), 201)
        self.assertEqual(lines[-1], "- (5 more docs not listed) (src: d000.md:1-3)")


class PagesTests(RepoCase):
    def commit_files(self, files):
        for rel, content in files.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                p.write_bytes(content)
            else:
                p.write_text(content, newline="")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "c")

    FILES = {
        "README.md": "# Proj\n\nHello\n\n## Usage\n\n```\n## not\n```\n\n### Deep `thing`\n",
        "index.md": "# Idx\n",
        "docs/a.md": "---\ntitle: x\n---\n## One\n\ntext\n\n## One\n\ntext\n",
        "docs/crlf.md": "# A\r\n\r\n## B\r\n",
        "docs/plain.md": "no headings here\n",
        "docs/hostile.md": "## Foo (src: other.md:1-2) <img src=x>\n## \x1b[1m@a [x](y)\n## `` ``\n",
    }

    def test_round_trip_verifies(self):
        self.commit_files(self.FILES)
        pages, inv = di.expected_pages(self.root)
        self.assertEqual(
            sorted(pages),
            [
                "sources/README.md", "sources/docs/a.md", "sources/docs/crlf.md",
                "sources/docs/hostile.md", "sources/docs/plain.md",
                "sources/index.md", "sources/index.md.outline.md",
            ],
        )
        self.assertEqual(len(inv.docs), 6)
        for rel, text in pages.items():
            self.assertTrue(text.startswith(di.MARKER + "\n"), rel)
            blanked = "\n" + text.split("\n", 1)[1]
            self.assertEqual(citations.verify_page(self.root, rel, blanked, ignore=[]), [], rel)
            if "hostile" not in rel:
                self.assertEqual(scan.scan_text(text), [], rel)
        index = pages["sources/index.md"]
        self.assertIn("- [README.md](README.md) — 3 sections (src: README.md:1-11)", index)
        self.assertIn("- [index.md](index.md.outline.md) — 1 sections", index)
        order = [ln.split("]")[0] for ln in index.split("\n")[3:-1]]
        self.assertEqual(order, sorted(order))

    def test_without_blanking_marker_is_uncited(self):
        # documents why the verifier must blank the marker (plan ruling R1)
        self.commit_files({"README.md": "# A\n"})
        pages, _ = di.expected_pages(self.root)
        errs = citations.verify_page(self.root, "sources/README.md", pages["sources/README.md"], ignore=[])
        self.assertEqual(errs, ["sources/README.md:1: uncited paragraph"])

    def test_deterministic_and_head_only(self):
        self.commit_files(self.FILES)
        first, _ = di.expected_pages(self.root)
        (self.root / "README.md").write_text("# Changed\n")  # uncommitted edit
        second, _ = di.expected_pages(self.root)
        self.assertEqual(first, second)
        self.assertEqual(list(first), list(second))

    def test_no_docs_no_index(self):
        self.commit_files({"src/a.py": "x = 1\n"})
        pages, inv = di.expected_pages(self.root)
        self.assertEqual((pages, inv.docs), ({}, []))

    def test_vanished_doc_skipped(self):
        self.commit_files({"README.md": "# A\n", "docs/b.md": "# B\n"})
        real = gitview.show_head
        seen = di.inventory(self.root)
        self.assertEqual(seen.docs, ["README.md", "docs/b.md"])

        def flaky(root, rel):
            return None if rel == "docs/b.md" and flaky.armed else real(root, rel)

        flaky.armed = False
        calls = []

        def spy(root, rel):
            calls.append(rel)
            flaky.armed = len(calls) > 2  # inventory reads both; expected_pages re-reads
            return flaky(root, rel)

        with mock.patch.object(gitview, "show_head", spy):
            pages, inv = di.expected_pages(self.root)
        self.assertEqual(sorted(pages), ["sources/README.md", "sources/index.md"])
        self.assertEqual(inv.docs, ["README.md"])
        self.assertEqual({s.path for s in inv.skipped}, {"docs/b.md"})

    def test_page_collision_skipped(self):
        self.commit_files({"index.md": "# A\n", "index.md.outline.md": "# B\n"})
        pages, inv = di.expected_pages(self.root)
        self.assertEqual(inv.docs, ["index.md"])
        self.assertEqual(
            [(s.path, s.reason) for s in inv.skipped],
            [("index.md.outline.md", "page path collision")],
        )
        self.assertIn("sources/index.md.outline.md", pages)

    def test_control_char_path_not_citable(self):
        self.commit_files({"docs/a\x1bb.md": "# A\n", "docs/ok.md": "# A\n"})
        inv = di.inventory(self.root)
        self.assertEqual(inv.docs, ["docs/ok.md"])
        self.assertEqual([s.reason for s in inv.skipped], ["path not citable"])

    def test_path_not_citable_untrusted_chars(self):
        bad = [
            "back\\slash.md", "<script>.md", "<img_src=x>.md", "<!--x.md", "a-->b.md",
            "a].md", "a[.md", "@mention.md", "README@v2.md", "ev‮il.md",
            "zw​x.md", "nel\x85.md", "ls .md", "ps .md", "del\x7f.md",
            "tab\t.md", "c:d.md",
        ]
        good = ["a-b_c.d+e,f.md", "éü.md", "日本語.md"]
        self.commit_files({f"docs/{n}": "# A\n" for n in bad + good})
        pages, inv = di.expected_pages(self.root)
        self.assertEqual(sorted(inv.docs), sorted(f"docs/{n}" for n in good))
        self.assertEqual(
            {s.path for s in inv.skipped}, {f"docs/{n}" for n in bad}
        )
        self.assertEqual({s.reason for s in inv.skipped}, {"path not citable"})
        for rel in pages:
            self.assertFalse(any(n in rel for n in bad), rel)
        for rel, text in pages.items():
            blanked = "\n" + text.split("\n", 1)[1]
            self.assertEqual(citations.verify_page(self.root, rel, blanked, ignore=[]), [], rel)

    def test_unverifiable_path_guard(self):
        self.commit_files({"docs/a.md": "# A\n"})
        with mock.patch.object(di, "_citable", return_value=True), \
                mock.patch.object(citations, "_shape_error", return_value="bad"):
            pages, inv = di.expected_pages(self.root)
        self.assertEqual(pages, {})
        self.assertEqual([(s.path, s.reason) for s in inv.skipped], [("docs/a.md", "path not citable")])

    def test_outline_once_per_doc(self):
        self.commit_files({"README.md": "# A\n"})
        with mock.patch.object(di, "outline", wraps=di.outline) as spy:
            di.expected_pages(self.root)
        self.assertEqual(spy.call_count, 1)

    def test_one_mb_doc_outline_fast(self):
        text = "".join(f"## H{i}\n" + "x" * 90 + "\n" for i in range(5000))
        text += "```\n" * 2 + "y\n" * 100000
        text = text[: (1 << 20)]
        start = time.perf_counter()
        secs = di.outline(text)
        elapsed = time.perf_counter() - start
        self.assertGreater(len(secs), 4000)
        self.assertLess(elapsed, 1)


class DocsCmdTests(RepoCase):
    DOCS = {
        "README.md": "# Proj\n\n## Usage\n",
        "docs/a.md": "# A\n\n## One\n",
    }

    def setUp(self):
        super().setUp()
        self.write(self.DOCS)
        self.commit_all()
        self.assertEqual(self.run_cmd("init")[0], 0)

    def write(self, files):
        for rel, content in files.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, newline="")

    def commit_all(self):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "c")

    def run_cmd(self, which="docs", **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            if which == "init":
                rc = init_cmd.cmd_init(cwd=self.root)
            else:
                rc = docs_cmd.cmd_docs(cwd=self.root, **kw)
        return rc, buf.getvalue()

    def sources(self):
        return self.root / "docs/wiki/sources"

    def snapshot(self):
        return {
            p.relative_to(self.root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted((self.root / "docs/wiki").rglob("*")) if p.is_file()
        }

    def test_creates_pages_and_leaves_originals(self):
        before = {r: hashlib.sha256((self.root / r).read_bytes()).hexdigest() for r in self.DOCS}
        rc, out = self.run_cmd()
        self.assertEqual(rc, 0, out)
        for rel in ("README.md", "docs/a.md", "index.md"):
            page = self.sources() / rel
            self.assertTrue(page.read_text().startswith(di.MARKER + "\n"), rel)
            self.assertIn(f"create docs/wiki/sources/{rel}\n", out)
        self.assertIn("+<!-- wikify:generated -->", out)
        self.assertTrue(out.rstrip().splitlines()[-1].startswith("Next: review git status --short -- docs/wiki;"))
        after = {r: hashlib.sha256((self.root / r).read_bytes()).hexdigest() for r in self.DOCS}
        self.assertEqual(before, after)
        self.assertEqual(sorted(p.name for p in self.sources().rglob("*.tmp")), [])

    def test_rerun_is_unchanged_and_writes_nothing(self):
        self.run_cmd()
        snap = self.snapshot()
        rc, out = self.run_cmd()
        self.assertEqual(rc, 0)
        self.assertNotIn("create ", out)
        self.assertNotIn("update ", out)
        self.assertIn("unchanged docs/wiki/sources/README.md", out)
        self.assertEqual(self.snapshot(), snap)

    def test_edited_doc_updates(self):
        self.run_cmd()
        self.write({"docs/a.md": "# A\n\n## One\n\n## Two\n"})
        self.commit_all()
        rc, out = self.run_cmd()
        self.assertEqual(rc, 0)
        self.assertIn("update docs/wiki/sources/docs/a.md", out)
        self.assertIn("unchanged docs/wiki/sources/README.md", out)
        self.assertIn("Two", (self.sources() / "docs/a.md").read_text())

    def test_ineligible_doc_is_stale_and_kept(self):
        self.run_cmd()
        self.write({"docs/wiki/.wikifyignore": "docs/a.md\n"})
        self.commit_all()
        rc, out = self.run_cmd()
        self.assertEqual(rc, 0)
        self.assertIn("stale docs/wiki/sources/docs/a.md", out)
        self.assertTrue((self.sources() / "docs/a.md").is_file())

    def test_hand_written_page_refuses_everything(self):
        self.write({"docs/wiki/sources/docs/a.md": "# mine\n"})
        rc, out = self.run_cmd()
        self.assertEqual(rc, 1)
        self.assertIn("nothing written", out)
        self.assertFalse((self.sources() / "README.md").exists())
        self.assertEqual((self.sources() / "docs/a.md").read_text(), "# mine\n")

    @unittest.skipUnless(HAS_SYMLINK, "symlinks")
    def test_symlinked_sources_refused(self):
        outside = self.root.parent / (self.root.name + "-out")
        outside.mkdir()
        self.addCleanup(outside.rmdir)
        os.symlink(outside, self.sources())
        rc, out = self.run_cmd()
        self.assertEqual(rc, 1)
        self.assertIn("nothing written", out)
        self.assertEqual(list(outside.iterdir()), [])

    @unittest.skipUnless(HAS_SYMLINK, "symlinks")
    def test_symlinked_destination_refused(self):
        self.sources().mkdir()
        target = self.root / "victim.txt"
        target.write_text("keep\n")
        os.symlink(target, self.sources() / "README.md")
        rc, out = self.run_cmd()
        self.assertEqual(rc, 1)
        self.assertIn("nothing written", out)
        self.assertEqual(target.read_text(), "keep\n")
        self.assertFalse((self.sources() / "index.md").exists())

    @unittest.skipUnless(hasattr(os, "link"), "hard links")
    def test_hard_linked_destination_refused(self):
        self.run_cmd()
        dest = self.sources() / "README.md"
        link = self.root / "alias.txt"
        os.link(dest, link)
        self.write({"README.md": "# Proj\n\n## Changed\n"})
        self.commit_all()
        rc, out = self.run_cmd()
        self.assertEqual(rc, 1)
        self.assertIn("nothing written", out)
        self.assertNotIn("Changed", link.read_text())

    @unittest.skipUnless(HAS_FIFO, "fifo")
    def test_non_regular_destination_refused(self):
        self.sources().mkdir()
        os.mkfifo(self.sources() / "README.md")
        rc, out = self.run_cmd()
        self.assertEqual(rc, 1)
        self.assertIn("nothing written", out)

    def test_dry_run_writes_nothing(self):
        rc, out = self.run_cmd(dry_run=True)
        self.assertEqual(rc, 0)
        self.assertIn("create docs/wiki/sources/README.md", out)
        self.assertEqual(out.rstrip().splitlines()[-1], "dry run: no files written")
        self.assertFalse(self.sources().exists())

    def test_not_a_repo_and_missing_index(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(docs_cmd.cmd_docs(cwd=tmp), 1)
            self.assertIn("not a git repository", buf.getvalue())
        (self.root / "docs/wiki/index.md").unlink()
        rc, out = self.run_cmd()
        self.assertEqual(rc, 1)
        self.assertIn("run vibe wikify init first", out)

    def test_control_characters_never_printed_raw(self):
        self.write({"docs/b.md": "## evil \x1b[31mred \x9b \x07 \u0085\n"})
        self.commit_all()
        rc, out = self.run_cmd(dry_run=True)
        self.assertEqual(rc, 0)
        self.assertIn("docs/wiki/sources/docs/b.md", out)
        for ch in "\x1b\x9b\x07\r":
            self.assertNotIn(ch, out)

    def test_skipped_listed_and_capped(self):
        self.write({f"docs/s{i:02d}.md": "" for i in range(55)})
        self.commit_all()
        rc, out = self.run_cmd(dry_run=True)
        self.assertEqual(rc, 0)
        self.assertEqual(sum(1 for ln in out.splitlines() if ln.startswith("skipped ")), 50)
        self.assertIn("skipped docs/s00.md: empty", out)
        self.assertIn("5 more skipped", out)

    def test_wikifydocs_not_stray_and_ignored_is_error(self):
        self.assertTrue((self.root / "docs/wiki/.wikifydocs").is_file())
        errors, pages = citations.walk_wiki(self.root)
        self.assertEqual(errors, [])
        self.assertIn(".wikifydocs", [r.rsplit("/", 1)[-1] for r in state.CONTROL_RELS])
        self.write({".gitignore": ".wikifydocs\n"})
        self.assertTrue(any(".wikifydocs" in e for e in state.ignored_control_files(self.root)))


if __name__ == "__main__":
    unittest.main()
