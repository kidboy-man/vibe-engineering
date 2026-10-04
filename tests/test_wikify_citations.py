import subprocess
import tempfile
import unittest
from pathlib import Path

from agents.wikify import citations

SRC = "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n"


def git(root, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout.strip()


class RepoCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        self.commit("src/a.py", SRC)

    def write(self, rel, content):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    def commit(self, rel, content):
        self.write(rel, content)
        git(self.root, "add", rel)
        git(self.root, "commit", "-q", "-m", "c")

    def verify(self, text, page="p.md", ignore=()):
        return citations.verify_page(self.root, page, text, list(ignore))


class ParseTests(unittest.TestCase):
    def test_citation_fields(self):
        cites, unc = citations.parse("Text (src: src/a.py:1-2 `alpha`) and (src: b.py:7).\n")
        self.assertEqual(
            cites,
            [citations.Citation("src/a.py", 1, 2, "alpha", 1), citations.Citation("b.py", 7, 7, None, 1)],
        )
        self.assertEqual(unc, [])

    def test_uncited_and_exempt_blocks(self):
        text = (
            "# Heading\n\nplain words\n\n```\ncode\n\nmore code\n```\n\n"
            "- [a](a.md)\n- [[b]]\n\ncited (src: x.py:1)\n"
        )
        self.assertEqual(citations.parse(text)[1], [3])

    def test_human_block_excluded_and_numbering_kept(self):
        text = (
            "<!-- wikify:human -->\nnote (src: ../bad:1)\nuncited\n<!-- /wikify:human -->\n\n"
            "after (src: x.py:1)\n\nbare\n"
        )
        cites, unc = citations.parse(text)
        self.assertEqual([(c.path, c.line) for c in cites], [("x.py", 6)])
        self.assertEqual(unc, [8])


class VerifyTests(RepoCase):
    def test_ok(self):
        self.assertEqual(self.verify("ok (src: src/a.py:1-2 `alpha`)\n"), [])
        self.assertEqual(self.verify("ok (src: src/a.py:5)\n"), [])

    def test_symbol_and_range_table(self):
        cases = [
            ("symbol missing in range", "x (src: src/a.py:1-2 `beta`)\n", "symbol"),
            ("out of range", "x (src: src/a.py:1-99)\n", "range"),
            ("start zero", "x (src: src/a.py:0-2)\n", "range"),
            ("start after end", "x (src: src/a.py:3-2)\n", "range"),
            ("missing file", "x (src: src/none.py:1)\n", "not tracked"),
        ]
        for name, text, word in cases:
            with self.subTest(name):
                errs = self.verify(text)
                self.assertEqual(len(errs), 1, errs)
                self.assertTrue(errs[0].startswith("p.md:1: "), errs)
                self.assertIn(word, errs[0])

    def test_untracked_working_tree_file_rejected(self):
        self.write("src/new.py", "x = 1\n")
        self.assertIn("not tracked", self.verify("x (src: src/new.py:1)\n")[0])

    def test_staged_but_uncommitted_rejected(self):
        self.write("src/staged.py", "x = 1\n")
        git(self.root, "add", "src/staged.py")
        self.assertEqual(len(self.verify("x (src: src/staged.py:1)\n")), 1)

    def test_uncommitted_edit_does_not_satisfy_symbol(self):
        self.write("src/a.py", SRC + "def gamma():\n    pass\n")
        self.assertEqual(len(self.verify("x (src: src/a.py:7-8 `gamma`)\n")), 1)
        self.write("src/a.py", SRC.replace("beta", "delta"))
        self.assertEqual(self.verify("x (src: src/a.py:5 `beta`)\n"), [])

    def test_unsafe_paths_rejected(self):
        cases = {
            "absolute": "(src: /etc/passwd:1)",
            "dotdot": "(src: ../x:1)",
            "dotdot mid": "(src: src/../src/a.py:1)",
            "backslash": "(src: src\\a.py:1)",
            "windows drive": "(src: C:\\x:1)",
        }
        for name, cite in cases.items():
            with self.subTest(name):
                self.assertEqual(len(self.verify(f"x {cite}\n")), 1)

    def test_shape_reasons(self):
        self.assertIn("absolute", self.verify("x (src: /etc/passwd:1)\n")[0])
        self.assertIn("..", self.verify("x (src: ../x:1)\n")[0])
        self.assertIn("backslash", self.verify("x (src: src\\a.py:1)\n")[0])

    def test_secret_path_rejected(self):
        self.commit(".env", "A=1\n")
        self.assertIn("secret", self.verify("x (src: .env:1)\n")[0])

    def test_ignore_globs(self):
        self.assertIn("ignored", self.verify("x (src: src/a.py:1)\n", ignore=["src/*.py"])[0])
        self.assertEqual(self.verify("x (src: src/a.py:1)\n", ignore=["other/*"]), [])

    def test_human_block_bad_citation_skipped(self):
        text = "<!-- wikify:human -->\nx (src: ../bad:1)\n<!-- /wikify:human -->\n"
        self.assertEqual(self.verify(text), [])

    def test_uncited_paragraph_flagged_heading_not(self):
        errs = self.verify("# Title\n\nno cite here\n")
        self.assertEqual(errs, ["p.md:3: uncited paragraph"])

    def test_index_exempt_only_at_top_level(self):
        self.assertEqual(self.verify("prose\n", page="index.md"), [])
        self.assertEqual(self.verify("prose\n", page="Index.md"), ["Index.md:1: uncited paragraph"])
        self.assertEqual(self.verify("prose\n", page="sub/index.md"), ["sub/index.md:1: uncited paragraph"])

    def test_line_number_is_original_after_human_block(self):
        text = "<!-- wikify:human -->\na\nb\n<!-- /wikify:human -->\n\nx (src: src/a.py:1-99)\n"
        self.assertTrue(self.verify(text)[0].startswith("p.md:6: "))


class HardeningTests(RepoCase):
    def test_huge_and_unicode_digits_do_not_raise(self):
        for name, text in {
            "huge": "x (src: a.py:" + "1" * 5000 + ")\n",
            "unicode": "x (src: a.py:\u0661)\n",
        }.items():
            with self.subTest(name):
                cites, unc = citations.parse(text)
                self.assertEqual((cites, unc), ([], [1]))
                self.assertEqual(self.verify(text), ["p.md:1: uncited paragraph"])
        self.write("docs/wiki/bad.md", "x (src: a.py:" + "1" * 5000 + ")\n")
        self.write("docs/wiki/ok.md", "x (src: src/a.py:1)\n")
        self.assertEqual(citations.index(self.root)["ok.md"], {"src/a.py"})

    def test_heading_rule(self):
        cases = [
            ("heading then uncited prose", "# H\nprose under heading\n", ["p.md:2: uncited paragraph"]),
            ("heading alone", "## H\n", []),
            ("hashtag claim", "#hashtag claim\n", ["p.md:1: uncited paragraph"]),
            ("heading then cited", "# H\nok (src: src/a.py:1)\n", []),
        ]
        for name, text, want in cases:
            with self.subTest(name):
                self.assertEqual(self.verify(text), want)

    def test_ignore_directory_patterns(self):
        self.commit("vendor/a.py", "x\n")
        self.commit("internal/x.py", "x\n")
        self.commit("docs2/x.py", "x\n")
        cases = [
            ("vendor/", "vendor/a.py", True),
            ("internal", "internal/x.py", True),
            ("docs", "docs2/x.py", False),
            ("vendor/*", "vendor/a.py", True),
        ]
        for glob, path, rejected in cases:
            with self.subTest(glob=glob, path=path):
                errs = self.verify(f"x (src: {path}:1)\n", ignore=[glob])
                self.assertEqual(len(errs) == 1, rejected, errs)

    def test_line_numbering_matches_git(self):
        self.commit("src/odd.txt", "a\x0cb\nsecond\u2028x\nthird\n")
        self.assertEqual(self.verify("x (src: src/odd.txt:3 `third`)\n"), [])
        self.assertEqual(len(self.verify("x (src: src/odd.txt:4)\n")), 1)
        p = self.root / "src/crlf.txt"
        p.write_bytes(b"one\r\ntwo\r\n")
        git(self.root, "add", "src/crlf.txt")
        git(self.root, "commit", "-q", "-m", "crlf")
        self.assertEqual(self.verify("x (src: src/crlf.txt:2 `two`)\n"), [])
        self.assertEqual(len(self.verify("x (src: src/crlf.txt:3)\n")), 1)


class LoadIgnoreTests(RepoCase):
    def test_missing(self):
        self.assertEqual(citations.load_ignore(self.root), [])

    def test_parsed_from_wiki_dir_only(self):
        self.write(".wikifyignore", "root/*\n")
        self.assertEqual(citations.load_ignore(self.root), [])
        self.write("docs/wiki/.wikifyignore", "# c\n\nvendor/*\n  gen/**  \n")
        self.assertEqual(citations.load_ignore(self.root), ["vendor/*", "gen/**"])


class IndexTests(RepoCase):
    def test_overlap_human_wikify_and_unsafe(self):
        self.write("docs/wiki/domain/x/lifecycle.md", "a (src: src/a.py:1) b (src: ../x:1)\n")
        self.write("docs/wiki/y.md", "c (src: src/a.py:2) (src: src/b.py:1)\n"
                   "<!-- wikify:human -->\n(src: src/h.py:1)\n<!-- /wikify:human -->\n")
        self.write("docs/wiki/WIKIFY.md", "(src: src/w.py:1)\n")
        self.assertEqual(
            citations.index(self.root),
            {"domain/x/lifecycle.md": {"src/a.py"}, "y.md": {"src/a.py", "src/b.py"}},
        )

    def test_absent_wiki(self):
        self.assertEqual(citations.index(self.root), {})


if __name__ == "__main__":
    unittest.main()
