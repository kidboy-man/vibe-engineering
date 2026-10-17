import unittest
from unittest import mock

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

    def test_log_names_since_lists_the_files_a_merge_brought_in(self):
        base = gitview.head(self.root)
        git(self.root, "checkout", "-q", "-b", "side")
        self.write_code("x = 1\n", rel="app/side.py", msg="side work")
        git(self.root, "checkout", "-q", "-")
        self.write_code("y = 1\n", rel="app/main.py", msg="main work")
        git(self.root, "merge", "-q", "--no-ff", "-m", "merge side", "side")
        touched = drift.touched_since(self.root, base)
        self.assertIn("app/side.py", touched)
        self.assertIn("app/main.py", touched)

    def test_a_failed_ls_tree_is_an_error_not_an_empty_wiki(self):
        with mock.patch.object(gitview, "ls_tree_files", return_value=None):
            with self.assertRaises(RuntimeError):
                drift.read_pages(self.root, at_head=True)
        from agents.wikify import check_cmd
        with mock.patch.object(gitview, "ls_tree_files", return_value=None):
            result = check_cmd.run_check(self.root, ci=True)
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)

    def test_diff_hunks_only_accepts_a_full_commit_id(self):
        victim = self.root / "injected.txt"
        for bad in (f"--output={victim}", "-p", "HEAD~1", "abc123", "", "g" * 40):
            self.assertIsNone(gitview.diff_hunks(self.root, bad, "app/svc.py"), bad)
        self.assertFalse(victim.exists())
        self.assertFalse(list(self.root.rglob("*..HEAD")))
        self.assertEqual(gitview.diff_hunks(self.root, gitview.head(self.root), "app/svc.py"), [])

    def test_a_hostile_covered_value_never_reaches_git_as_an_option(self):
        victim = self.root / "injected.txt"
        state.save(self.root, f"--output={victim}", citations=state.load(self.root)["citations"])
        self.insert_lines_above(2)
        from agents.wikify import check_cmd
        rc, text = quiet(check_cmd.cmd_check, self.root)
        self.assertEqual(rc, 0, text)  # fell back to the hash windows: still a plain move
        self.assertFalse(victim.exists())

    def test_log_names_since_gives_up_when_history_is_truncated(self):
        base = gitview.head(self.root)
        self.write_code("x = 1\n", rel="app/a.py", msg="a")
        self.write_code("x = 2\n", rel="app/a.py", msg="b")
        with mock.patch.object(gitview, "MAX_LOG_COMMITS", 1):
            self.assertIsNone(gitview.log_names_since(self.root, base))
        with mock.patch.object(gitview, "MAX_LOG_COMMITS", 2):
            self.assertEqual(len(gitview.log_names_since(self.root, base)), 2)

    def test_head_mode_skips_a_page_that_is_not_utf8_like_the_work_tree(self):
        path = self.root / "docs/wiki/bad.md"
        path.write_bytes(b"Caf\xe9 (src: app/svc.py:10-20 `handle`)\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "bad bytes")
        self.assertNotIn("bad.md", drift.read_pages(self.root, at_head=True))
        self.assertNotIn("bad.md", drift.read_pages(self.root, at_head=False))

    def test_head_pages_use_universal_newlines_like_read_text(self):
        (self.root / "docs/wiki/crlf.md").write_bytes(b"One\r\n\r\nTwo\rThree\r\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "crlf")
        self.assertEqual(drift.read_pages(self.root, True)["crlf.md"], "One\n\nTwo\nThree\n")

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

    def test_marking_twice_survives_secret_looking_symbol_names(self):
        """The first mark writes `...|RefreshToken: <hash>`; the second verify must not flag it."""
        from agents.wikify import commands
        self.write_code("def RefreshToken():\n    return 1\n\ndef ResetPassword():\n    return 2\n", rel="app/auth.py", msg="auth")
        self.page("Refresh (src: app/auth.py:1-2 `RefreshToken`)\n\nReset (src: app/auth.py:4-5 `ResetPassword`)\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "auth page")
        self.assertEqual(quiet(commands.cmd_mark, self.root)[0], 0)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "docs(wiki): mark")
        rc, out = quiet(commands.cmd_mark, self.root)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("secret-assignment", out)

    def test_generated_pages_and_map_blocks_have_no_claims(self):
        index = (
            "<!-- wikify:map -->\n- [T](a.md) — hint\n<!-- /wikify:map -->\n\n"
            "Fact (src: x.py:1-2)\n"
        )
        self.assertEqual([c.path for c in drift.page_citations("index.md", index)], ["x.py"])
        generated = "<!-- wikify:generated -->\nDoc " + CITE + "\n"
        self.assertEqual(drift.page_citations("sources/a.md", generated), [])


def two_blocks_file(top=0):
    """A unique block U at 5-14 and an identical block X at 30-34 and again at 60-64."""
    pad = lambda n, tag: [f"# {tag} {i}" for i in range(n)]
    x = [f"xblk {n}" for n in range(5)]
    u = [f"ublk {n}" for n in range(10)]
    lines = ["# shift"] * top + pad(4, "head") + u + pad(15, "mid") + x + pad(25, "gap") + x + pad(5, "end")
    return "\n".join(lines) + "\n"


def twin_file(first="xblk 0"):
    """Two identical 5-line blocks at 10-14 and 40-44 (the first one's first line is ``first``)."""
    pad = lambda n, tag: [f"# {tag} {i}" for i in range(n)]
    block = lambda head: [head] + [f"xblk {n}" for n in range(1, 5)]
    return "\n".join(pad(9, "head") + block(first) + pad(25, "mid") + block("xblk 0") + pad(5, "end")) + "\n"


class DiffGuidedTests(DriftCase):
    """With the recorded commit available, git's own diff tells moved from edited."""

    def setUp(self):
        super().setUp()
        self.write_code(twin_file(), rel="app/twin.py", msg="twins")
        self.page("X (src: app/twin.py:10-14 `xblk 0`)\n", rel="docs/wiki/twin.md")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "twin page")
        from agents.wikify import commands
        quiet(commands.cmd_mark, self.root)
        git(self.root, "add", "--", "docs/wiki")
        git(self.root, "commit", "-q", "-m", "docs(wiki): mark twins")

    def classify(self, base="auto"):
        return {
            (f.page, f.start): f for f in drift.classify(
                self.root, drift.read_pages(self.root, False), drift.read_state(self.root, False),
                set(gitview.tracked_files(self.root)), citations.load_ignore(self.root),
                base=drift.read_state(self.root, False)["covered"] if base == "auto" else base,
            ).findings
        }

    def twin(self, findings):
        return findings[("twin.md", 10)]

    def test_editing_the_cited_block_is_changed_even_though_a_twin_still_matches(self):
        text = twin_file().replace("xblk 1", "xblk 1 CHANGED", 1)  # edits the first block only
        self.write_code(text, rel="app/twin.py", msg="edit first")
        found = self.classify()
        self.assertEqual(self.twin(found).category, "changed")
        self.assertIn("edited", self.twin(found).reason)

    def test_without_history_the_twin_is_taken_for_a_move_which_is_the_documented_limit(self):
        self.write_code(twin_file().replace("xblk 1", "xblk 1 CHANGED", 1), rel="app/twin.py", msg="edit first")
        self.assertEqual(self.twin(self.classify(base=None)).category, "moved")

    def test_a_shift_is_mapped_through_the_diff_even_with_twins(self):
        self.write_code("# new\n# new\n# new\n" + twin_file(), rel="app/twin.py", msg="shift 3")
        found = self.twin(self.classify())
        self.assertEqual((found.category, found.new_start, found.new_end), ("moved", 13, 17))

    def test_an_insertion_inside_the_range_is_changed(self):
        lines = twin_file().split("\n")
        lines.insert(12, "# inserted inside the block")
        self.write_code("\n".join(lines), rel="app/twin.py", msg="insert inside")
        self.assertEqual(self.twin(self.classify()).category, "changed")

    def test_an_insertion_right_after_the_range_leaves_it_in_place(self):
        lines = twin_file().split("\n")
        lines.insert(14, "# inserted after the block")
        self.write_code("\n".join(lines), rel="app/twin.py", msg="insert after")
        self.assertNotIn(("twin.md", 10), self.classify())

    def test_a_hunk_proven_shift_survives_the_search_budget(self):
        self.write_code("# new\n# new\n# new\n" + twin_file(), rel="app/twin.py", msg="shift 3")
        with mock.patch.object(drift, "MAX_WINDOW_WORK", 1):
            found = self.twin(self.classify())
        self.assertEqual((found.category, found.new_start), ("moved", 13))

    def test_an_edit_below_the_range_does_not_move_it(self):
        self.write_code(twin_file().replace("# mid 5", "# mid changed"), rel="app/twin.py", msg="edit below")
        self.assertNotIn(("twin.md", 10), self.classify())

    def test_check_reports_the_edit_and_reanchor_refuses_it(self):
        from agents.wikify import check_cmd, reanchor
        self.write_code(twin_file().replace("xblk 1", "xblk 1 CHANGED", 1), rel="app/twin.py", msg="edit first")
        rc, out = quiet(check_cmd.cmd_check, self.root)
        self.assertEqual(rc, 1, out)
        rc, out = quiet(reanchor.cmd_reanchor, self.root, True)
        self.assertEqual(rc, 1)
        self.assertIn("refused", out)
        self.assertIn("app/twin.py:10-14", (self.root / "docs/wiki/twin.md").read_text())


class ConsistentShiftTests(DriftCase):
    """An ambiguous block is healed only when the file's other moved citations prove the shift."""

    def setUp(self):
        super().setUp()
        self.write_code(two_blocks_file(), rel="app/blocks.py", msg="blocks")
        self.page(
            "U (src: app/blocks.py:5-14 `ublk 0`)\n\nX (src: app/blocks.py:30-34 `xblk 0`)\n",
            rel="docs/wiki/blocks.md",
        )
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "blocks page")
        from agents.wikify import commands
        quiet(commands.cmd_mark, self.root)

    def findings(self):
        done = drift.classify(
            self.root, drift.read_pages(self.root, False), drift.read_state(self.root, False),
            set(gitview.tracked_files(self.root)), citations.load_ignore(self.root),
        )
        return {(f.page, f.start): f for f in done.findings}

    def test_ambiguous_block_follows_the_shift_of_its_unique_neighbour(self):
        self.write_code(two_blocks_file(top=3), rel="app/blocks.py", msg="shift 3")
        found = self.findings()
        self.assertEqual(found[("blocks.md", 5)].category, "moved")
        x = found[("blocks.md", 30)]
        self.assertEqual((x.category, x.new_start, x.new_end), ("moved", 33, 37))

    def test_without_a_moved_neighbour_it_stays_ambiguous(self):
        self.page("X (src: app/blocks.py:30-34 `xblk 0`)\n", rel="docs/wiki/blocks.md")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "only x")
        from agents.wikify import commands
        quiet(commands.cmd_mark, self.root)
        self.write_code(two_blocks_file(top=3), rel="app/blocks.py", msg="shift 3")
        x = self.findings()[("blocks.md", 30)]
        self.assertEqual(x.category, "changed")
        self.assertIn("ambiguous", x.reason)

    def test_a_candidate_that_does_not_match_the_neighbours_shift_is_not_guessed(self):
        # U shifts by 3, but both X blocks shift by 5 (two lines were inserted between them and U)
        text = two_blocks_file(top=3).replace("xblk 0", "# ins\n# ins\nxblk 0", 1)
        self.write_code(text, rel="app/blocks.py", msg="insert between")
        found = self.findings()
        self.assertEqual(found[("blocks.md", 5)].category, "moved")
        x = found[("blocks.md", 30)]
        self.assertEqual(x.category, "changed")  # start + 3 is not a candidate: never guessed
        self.assertIn("ambiguous", x.reason)

    def test_neighbours_that_disagree_on_the_shift_cancel_the_heal(self):
        """U (above) moved by 3, W (below) moved by 1: X could have moved either way."""
        pad = lambda n, tag: [f"# {tag} {i}" for i in range(n)]
        x = [f"xblk {n}" for n in range(5)]
        u = [f"ublk {n}" for n in range(10)]
        w = [f"wblk {n}" for n in range(10)]
        old = pad(4, "head") + u + pad(15, "mid") + x + pad(25, "gap") + x + pad(20, "far") + w + pad(5, "end")
        self.write_code("\n".join(old) + "\n", rel="app/blocks.py", msg="blocks v2")
        self.page(
            "U (src: app/blocks.py:5-14 `ublk 0`)\n\nX (src: app/blocks.py:30-34 `xblk 0`)\n\n"
            "W (src: app/blocks.py:85-94 `wblk 0`)\n", rel="docs/wiki/blocks.md")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "three cites")
        from agents.wikify import commands
        self.assertEqual(quiet(commands.cmd_mark, self.root)[0], 0)
        new = ["# s"] * 3 + pad(4, "head") + u + pad(15, "mid") + x + pad(25, "gap") + x + pad(18, "far") + w + pad(5, "end")
        self.write_code("\n".join(new) + "\n", rel="app/blocks.py", msg="shift 3 then 1")
        found = self.findings()
        self.assertEqual(found[("blocks.md", 5)].new_start, 8)
        self.assertEqual(found[("blocks.md", 85)].new_start, 86)
        self.assertEqual(found[("blocks.md", 30)].category, "changed")

    def test_reanchor_heals_it(self):
        from agents.wikify import reanchor
        self.write_code(two_blocks_file(top=3), rel="app/blocks.py", msg="shift 3")
        rc, out = quiet(reanchor.cmd_reanchor, self.root, True)
        self.assertEqual(rc, 0, out)
        self.assertIn("app/blocks.py:33-37", (self.root / "docs/wiki/blocks.md").read_text())


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
