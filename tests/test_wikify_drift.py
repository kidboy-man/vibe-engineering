import unittest

from agents.wikify import citations, drift, gitview, state
from tests.test_wikify_state import git
from tests.wikify_drift_helpers import CITE, PAGE, SVC, DriftCase, quiet, svc_source

LINES = [f"line {n}" for n in range(1, 21)]


class HashTests(unittest.TestCase):
    def test_range_hash_is_12_hex_and_stable(self):
        digest = drift.range_hash(LINES, 3, 5)
        self.assertRegex(digest, r"^[0-9a-f]{12}$")
        self.assertEqual(digest, drift.range_hash(LINES, 3, 5))

    def test_range_hash_ignores_line_endings(self):
        crlf = citations.split_lines("".join(f"{ln}\r\n" for ln in LINES))
        lf = citations.split_lines("".join(f"{ln}\n" for ln in LINES))
        self.assertEqual(drift.range_hash(crlf, 2, 4), drift.range_hash(lf, 2, 4))

    def test_range_hash_changes_with_content_and_bounds(self):
        base = drift.range_hash(LINES, 3, 5)
        self.assertNotEqual(base, drift.range_hash(LINES, 3, 6))
        edited = list(LINES)
        edited[3] = "changed"
        self.assertNotEqual(base, drift.range_hash(edited, 3, 5))

    def test_citation_key(self):
        cite = citations.Citation("a/b.py", 4, 9, "func", 7)
        self.assertEqual(drift.citation_key("p.md", cite), "p.md|a/b.py:4-9|func")
        bare = citations.Citation("a/b.py", 4, 4, None, 1)
        self.assertEqual(drift.citation_key("p.md", bare), "p.md|a/b.py:4-4|")


class WindowTests(unittest.TestCase):
    def digest(self, lines, start, end):
        return drift.range_hash(lines, start, end)

    def test_exactly_one_match_after_shift(self):
        shifted = ["new"] * 3 + LINES
        found = drift.find_windows(shifted, 3, self.digest(LINES, 5, 7))
        self.assertEqual(found, [8])

    def test_zero_matches(self):
        self.assertEqual(drift.find_windows(LINES, 3, "0" * 12), [])

    def test_several_matches(self):
        doubled = LINES + LINES
        self.assertEqual(
            drift.find_windows(doubled, 3, self.digest(LINES, 5, 7)), [5, 25]
        )

    def test_anchor_limits_candidates_but_not_results(self):
        shifted = ["new"] * 3 + LINES
        digest = self.digest(LINES, 5, 7)
        self.assertEqual(drift.find_windows(shifted, 3, digest, anchor="line 6"), [8])
        # an anchor that is not in the window cannot produce a match
        self.assertEqual(drift.find_windows(shifted, 3, digest, anchor="absent"), [])

    def test_over_budget_returns_none(self):
        big = [f"l{n}" for n in range(5000)]
        self.assertIsNone(drift.find_windows(big, 2500, "0" * 12))

    def test_window_longer_than_file(self):
        self.assertEqual(drift.find_windows(LINES, 50, "0" * 12), [])


class ReaderTests(DriftCase):
    def test_pages_worktree_and_head_agree_when_clean(self):
        tree = drift.read_pages(self.root, at_head=False)
        head = drift.read_pages(self.root, at_head=True)
        self.assertEqual(set(tree), {"index.md", "svc.md"})
        self.assertEqual(tree, head)

    def test_dirty_page_changes_worktree_only(self):
        self.page("Edited " + CITE + "\n")
        self.assertIn("Edited", drift.read_pages(self.root, at_head=False)["svc.md"])
        self.assertIn("Handle adds", drift.read_pages(self.root, at_head=True)["svc.md"])

    def test_control_files_and_non_markdown_are_skipped(self):
        for rel in ("docs/wiki/notes.txt", "docs/wiki/sub/deep.md"):
            self.commit(rel, "x\n")
        for at_head in (False, True):
            pages = drift.read_pages(self.root, at_head=at_head)
            self.assertNotIn("WIKIFY.md", pages)
            self.assertNotIn("notes.txt", pages)
            self.assertIn("sub/deep.md", pages)

    def test_head_mode_skips_symlinks(self):
        link = self.root / "docs/wiki/link.md"
        link.symlink_to("svc.md")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "link")
        self.assertNotIn("link.md", drift.read_pages(self.root, at_head=True))

    def test_state_head_ignores_dirty_state(self):
        recorded = drift.read_state(self.root, at_head=True)["citations"]
        self.assertTrue(recorded)
        state.save(self.root, "dirty", citations={})
        self.assertEqual(drift.read_state(self.root, at_head=True)["citations"], recorded)
        self.assertEqual(drift.read_state(self.root, at_head=False)["citations"], {})

    def test_log_names_since(self):
        base = gitview.head(self.root)
        self.write_code("x = 1\n", rel="app/other.py", msg="other")
        self.insert_lines_above(1)
        commits = gitview.log_names_since(self.root, base)
        self.assertEqual([names for _, names in commits], [["app/svc.py"], ["app/other.py"]])
        self.assertIsNone(gitview.log_names_since(self.root, "deadbeef"))

    def test_ls_tree_files(self):
        self.assertIn(PAGE, gitview.ls_tree_files(self.root, "docs/wiki/"))
        self.assertEqual(gitview.ls_tree_files(self.root, "nothing/"), [])


class BaselineTests(DriftCase):
    def keys(self):
        return drift.read_state(self.root, at_head=False)["citations"]

    def test_mark_records_a_hash_per_citation(self):
        self.assertEqual(list(self.keys()), ["svc.md|app/svc.py:10-20|handle"])
        lines = citations.split_lines((self.root / "app/svc.py").read_text())
        self.assertEqual(self.keys()["svc.md|app/svc.py:10-20|handle"], drift.range_hash(lines, 10, 20))

    def test_mark_drops_keys_for_removed_citations(self):
        self.page("Plain " + "(src: app/svc.py:1-2)\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "edit")
        from tests.wikify_drift_helpers import quiet
        from agents.wikify import commands
        self.assertEqual(quiet(commands.cmd_mark, self.root)[0], 0)
        self.assertEqual(list(self.keys()), ["svc.md|app/svc.py:1-2|"])

    def test_generated_pages_and_map_blocks_have_no_claims(self):
        index = (
            "<!-- wikify:map -->\n- [T](a.md) — hint\n<!-- /wikify:map -->\n\n"
            "Fact (src: x.py:1-2)\n"
        )
        self.assertEqual([c.path for c in drift.page_citations("index.md", index)], ["x.py"])
        generated = "<!-- wikify:generated -->\nDoc " + CITE + "\n"
        self.assertEqual(drift.page_citations("sources/a.md", generated), [])


class ClassifyTests(DriftCase):
    def classify(self, at_head=False):
        return drift.classify(
            self.root,
            drift.read_pages(self.root, at_head),
            drift.read_state(self.root, at_head),
            set(gitview.tracked_files(self.root)),
            citations.load_ignore(self.root),
        )

    def only(self):
        result = self.classify()
        self.assertEqual(len(result.findings), 1, result.findings)
        return result.findings[0]

    def test_unchanged_is_clean(self):
        result = self.classify()
        self.assertEqual((result.findings, result.unhashed), ([], []))

    def test_small_shift_with_symbol_still_in_old_range_is_moved(self):
        self.insert_lines_above(2)
        finding = self.only()
        self.assertEqual(finding.category, "moved")
        self.assertEqual((finding.new_start, finding.new_end), (12, 22))
        self.assertEqual((finding.page, finding.path, finding.start, finding.end), ("svc.md", SVC, 10, 20))

    def test_large_shift_is_moved(self):
        self.insert_lines_above(15)
        finding = self.only()
        self.assertEqual((finding.category, finding.new_start), ("moved", 25))

    def test_edited_body_is_changed(self):
        self.write_code(svc_source(tag="!"))
        finding = self.only()
        self.assertEqual(finding.category, "changed")
        self.assertIn("body changed", finding.reason)

    def test_deleted_symbol_is_missing(self):
        self.write_code(svc_source().replace("def handle", "def other"))
        self.assertEqual(self.only().category, "missing")

    def test_deleted_file_is_missing(self):
        git(self.root, "rm", "-q", SVC)
        git(self.root, "commit", "-q", "-m", "rm")
        finding = self.only()
        self.assertEqual(finding.category, "missing")
        self.assertIn("not tracked", finding.reason)

    def test_ambiguous_relocation_is_changed_never_moved(self):
        self.write_code(svc_source(top=3) + svc_source())
        finding = self.only()
        self.assertEqual(finding.category, "changed")
        self.assertIn("ambiguous: 2 matches", finding.reason)

    def test_crlf_rewrite_is_clean(self):
        self.write_code(svc_source().replace("\n", "\r\n"))
        self.assertEqual(self.classify().findings, [])

    def test_no_hash_symbol_in_range_is_clean_and_listed(self):
        state.save(self.root, gitview.head(self.root), citations={})
        result = self.classify()
        self.assertEqual(result.findings, [])
        self.assertEqual([(page, cite.path) for page, cite in result.unhashed], [("svc.md", SVC)])

    def test_no_hash_symbol_outside_range_is_changed(self):
        state.save(self.root, gitview.head(self.root), citations={})
        self.insert_lines_above(15)
        finding = self.only()
        self.assertEqual(finding.category, "changed")
        self.assertIn("no range hash yet", finding.reason)

    def test_no_hash_symbol_gone_from_file_is_missing(self):
        state.save(self.root, gitview.head(self.root), citations={})
        self.write_code(svc_source().replace("def handle", "def other"))
        self.assertEqual(self.only().category, "missing")

    def test_cited_file_that_is_not_utf8_does_not_crash(self):
        path = self.root / "app/bin.py"
        path.write_bytes(b"def run():\n    return b'\xff\xfe'\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "bin")
        self.page("Run " + CITE + "\n\nBin (src: app/bin.py:1-2 `run`)\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "page")
        self.assertEqual(quiet(__import__("agents.wikify.commands", fromlist=["x"]).cmd_mark, self.root)[0], 0)
        self.assertEqual(self.classify().findings, [])

    def test_secret_ignored_and_wiki_paths_are_missing_with_reason(self):
        self.page(
            "A (src: .env:1-1)\n\nB (src: docs/wiki/svc.md:1-1)\n\nC (src: ../x.py:1-1)\n"
        )
        reasons = sorted(f.reason for f in self.classify().findings)
        self.assertEqual(len(reasons), 3)
        self.assertTrue(all(f.category == "missing" for f in self.classify().findings))

    def test_head_mode_ignores_a_dirty_page(self):
        self.page("Other (src: app/svc.py:1-2)\n")
        self.assertEqual(self.classify(at_head=True).findings, [])


if __name__ == "__main__":
    unittest.main()
