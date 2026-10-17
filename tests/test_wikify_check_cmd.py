import json
import unittest
from unittest import mock

from agents.wikify import check_cmd, drift, gitview, state
from tests.test_wikify_state import RepoCase, git
from tests.wikify_adopt_helpers import validate
from tests.wikify_drift_helpers import CITE, SVC, DriftCase, quiet, svc_source

STR = {"type": "string"}
INT = {"type": "integer"}
FINDING = {
    "type": "object",
    "required": ["page", "line", "category", "path", "start", "end", "symbol", "reason", "commits"],
    "properties": {
        "page": STR, "line": INT, "category": {"type": "string", "enum": ["moved", "changed", "missing"]},
        "path": STR, "start": INT, "end": INT, "reason": STR,
        "commits": {"type": "array", "items": STR},
    },
}
SCHEMA = {
    "type": "object",
    "required": ["ok", "counts", "drift", "moved", "uncovered_areas", "references", "notices", "error"],
    "properties": {
        "counts": {"type": "object", "required": [
            "moved", "changed", "missing", "uncovered_areas", "references", "unbaselined_changed"]},
        "drift": {"type": "array", "items": FINDING},
        "moved": {"type": "array", "items": FINDING},
        "uncovered_areas": {"type": "array", "items": {
            "type": "object", "required": ["area", "files"], "properties": {"area": STR}}},
        "notices": {"type": "array", "items": STR},
    },
}


class CheckCase(DriftCase):
    def check(self, *, ci=False, as_json=False):
        rc, text = quiet(check_cmd.cmd_check, self.root, ci=ci, as_json=as_json)
        return rc, text

    def data(self, ci=False):
        rc, text = self.check(ci=ci, as_json=True)
        return rc, json.loads(text)


class CheckVerdictTests(CheckCase):
    def test_clean_exits_zero(self):
        rc, text = self.check()
        self.assertEqual(rc, 0)
        self.assertIn("ok", text)

    def test_only_moved_exits_zero_and_is_listed_as_healable(self):
        self.insert_lines_above(2)
        rc, text = self.check()
        self.assertEqual(rc, 0)
        self.assertIn("moved", text)
        self.assertIn("vibe wikify reanchor", text)

    def test_changed_exits_one_and_names_page_and_commit(self):
        self.write_code(svc_source(tag="!"), msg="edit body")
        rc, data = self.data()
        self.assertEqual(rc, 1)
        self.assertFalse(data["ok"])
        finding = data["drift"][0]
        self.assertEqual((finding["page"], finding["category"], finding["path"]), ("svc.md", "changed", SVC))
        self.assertEqual(finding["commits"], [gitview.head(self.root)[:7]])

    def test_missing_exits_one(self):
        git(self.root, "rm", "-q", SVC)
        git(self.root, "commit", "-q", "-m", "rm")
        rc, data = self.data()
        self.assertEqual((rc, data["counts"]["missing"]), (1, 1))

    def test_uncovered_area_warns_but_never_fails(self):
        self.write_code("x = 1\n", rel="app/new/x.py", msg="new")
        rc, data = self.data()
        self.assertEqual(rc, 0)
        self.assertEqual([a["area"] for a in data["uncovered_areas"]], ["app/new"])
        self.assertEqual(data["uncovered_areas"][0]["files"], ["app/new/x.py"])

    def test_file_in_a_cited_area_is_not_uncovered(self):
        self.write_code("x = 1\n", rel="app/other.py", msg="sibling")
        self.assertEqual(self.data()[1]["uncovered_areas"], [])

    def test_internal_error_fails_closed(self):
        with mock.patch.object(drift, "classify", side_effect=RuntimeError("boom")):
            rc, data = self.data()
            rc_text, text = self.check()
        self.assertEqual((rc, rc_text), (1, 1))
        self.assertFalse(data["ok"])
        self.assertIn("RuntimeError", data["error"])
        self.assertNotIn("boom", data["error"])
        self.assertIn("check failed", text)

    def test_unbaselined_changed_counts_hashless_citations_on_changed_files(self):
        state.save(self.root, gitview.head(self.root), citations={})
        git(self.root, "add", "--", "docs/wiki")
        git(self.root, "commit", "-q", "-m", "docs(wiki): drop hashes")
        self.assertEqual(self.data()[1]["counts"]["unbaselined_changed"], 0)
        self.insert_lines_above(15)
        rc, data = self.data()
        self.assertEqual(data["counts"]["unbaselined_changed"], 1)
        self.assertTrue(any("no range hash yet" in n for n in data["notices"]))

    def test_hashed_citation_is_not_unbaselined(self):
        self.insert_lines_above(2)
        self.assertEqual(self.data()[1]["counts"]["unbaselined_changed"], 0)


class CheckSafetyTests(CheckCase):
    def test_read_only_and_idempotent(self):
        self.insert_lines_above(2)
        self.write_code("x = 1\n", rel="app/new/x.py", msg="new")
        before = self.tree_hash()
        first = self.check()
        second = self.check(ci=True)
        third = self.check()
        self.assertEqual(self.tree_hash(), before)
        self.assertEqual(first, third)
        self.assertNotEqual(first[1], second[1])

    def test_ci_judges_head_not_the_dirty_tree(self):
        self.page("Gone (src: app/missing.py:1-1)\n")
        self.assertEqual(self.check()[0], 1)
        self.assertEqual(self.check(ci=True)[0], 0)

    def test_json_matches_schema(self):
        self.insert_lines_above(2)
        self.write_code(svc_source(top=2, tag="!"), msg="edit")
        for ci in (False, True):
            _, data = self.data(ci=ci)
            self.assertEqual(validate(data, SCHEMA), [])

    def test_control_characters_in_paths_are_escaped(self):
        self.page("Bad (src: a\x1bb.py:1-2)\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "bad cite")
        for ci in (False, True):
            _, text = self.check(ci=ci)
            self.assertNotIn("\x1b", text)
            self.assertIn("\\x1b", text)

    def test_page_text_is_never_echoed(self):
        self.page("Handle " + CITE + "\n\npassword = 'hunter2hunter2'\n")
        for ci in (False, True):
            self.assertNotIn("hunter2", self.check(ci=ci)[1])


class CheckEdgeTests(RepoCase):
    def test_no_commits(self):
        rc, text = quiet(check_cmd.cmd_check, self.root, ci=True, as_json=False)
        self.assertEqual(rc, 0)
        self.assertIn("no commits", text)

    def test_never_marked_reports_no_baseline_distinctly(self):
        self.commit(SVC, svc_source())
        self.commit("docs/wiki/svc.md", "Handle " + CITE + "\n")
        rc, text = quiet(check_cmd.cmd_check, self.root, ci=False, as_json=False)
        self.assertEqual(rc, 0, text)
        self.assertIn("no baseline", text)


class SquashMergeTests(CheckCase):
    def squash(self, code_text=None):
        """One commit that mixes code with a rewritten .wikify.json, as a squash merge does."""
        if code_text is not None:
            (self.root / SVC).write_text(code_text)
        self.commit("src/other.py", "x = 1\n", msg="unrelated code")
        git(self.root, "reset", "--soft", "HEAD~1")
        state.save(self.root, gitview.head(self.root), citations=state.load(self.root)["citations"])
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "squash")

    def test_mixed_squash_commit_passes_check_but_not_the_commit_order_rule(self):
        self.squash()
        self.assertFalse(state.is_fresh(self.root))
        self.assertEqual(self.check(ci=True)[0], 0)

    def test_squash_that_also_changed_a_cited_body_still_fails(self):
        self.squash(code_text=svc_source(tag="!"))
        self.assertEqual(self.check(ci=True)[0], 1)

    def test_mark_rebaselines_after_a_squash(self):
        from agents.wikify import commands
        self.squash()
        self.assertEqual(quiet(commands.cmd_mark, self.root)[0], 0)
        git(self.root, "add", "--", "docs/wiki")
        git(self.root, "commit", "-q", "-m", "docs(wiki): mark")
        self.assertTrue(state.is_fresh(self.root))
        self.assertEqual(self.check(ci=True)[0], 0)


class SyncTests(CheckCase):
    def sync(self):
        return quiet(check_cmd.cmd_sync, self.root)

    def test_clean_wiki_has_an_empty_work_list(self):
        rc, text = self.sync()
        self.assertEqual(rc, 0)
        self.assertIn("work list (0)", text)

    def test_work_list_is_ordered_and_names_pages_and_actions(self):
        self.page("Handle " + CITE + "\n\nTail (src: app/svc.py:21-30)\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "more citations")
        from agents.wikify import commands
        quiet(commands.cmd_mark, self.root)
        git(self.root, "add", "--", "docs/wiki")
        git(self.root, "commit", "-q", "-m", "mark")
        self.page("Handle " + CITE + "\n\nTail (src: app/svc.py:21-30)\n\nGone (src: app/gone.py:1-2)\n")
        self.write_code(svc_source(top=2).replace("# tail 3", "# tail changed"), msg="drift")
        self.write_code("x = 1\n", rel="app/new/x.py", msg="new area")
        rc, text = self.sync()
        self.assertEqual(rc, 1)
        order = [line.split()[1] for line in text.splitlines() if line.startswith("  ") and line.split()[0].rstrip(".").isdigit()]
        self.assertEqual(order, ["moved", "changed", "missing", "uncovered"])
        self.assertIn("vibe wikify reanchor --apply", text)
        self.assertIn("svc.md", text)

    def test_sync_previews_the_rewrite_and_writes_nothing(self):
        self.insert_lines_above(3)
        before = self.tree_hash()
        rc, text = self.sync()
        self.assertEqual(rc, 0)
        self.assertIn("10-20 -> 13-23", text)
        self.assertEqual(self.tree_hash(), before)

    def test_exit_code_is_the_check_verdict(self):
        self.write_code(svc_source(tag="!"))
        self.assertEqual(self.sync()[0], 1)


class MapHygieneTests(CheckCase):
    def index(self, count):
        rows = "".join(f"- [P{n}](a/p{n}.md) — hint\n" for n in range(count))
        (self.root / "docs/wiki/index.md").write_text(
            f"# Wiki index\n\n<!-- wikify:map -->\n{rows}<!-- /wikify:map -->\n"
        )

    def test_notice_at_eighty_percent_never_changes_the_exit_code(self):
        self.index(49)
        rc, text = self.check()
        self.assertEqual(rc, 0)
        self.assertIn("map is at 82% of its 60-entry cap", text)

    def test_no_notice_below_eighty_percent(self):
        self.index(47)
        self.assertNotIn("map is at", self.check()[1])

    def test_sync_suggests_grouping_and_creates_nothing(self):
        self.index(49)
        before = self.tree_hash()
        rc, text = quiet(check_cmd.cmd_sync, self.root)
        self.assertEqual(rc, 0)
        self.assertIn("group docs/wiki/a/ (49 entries) under a/index.md", text)
        self.assertEqual(self.tree_hash(), before)
        self.assertFalse((self.root / "docs/wiki/a").exists())

    def test_json_carries_the_suggestions(self):
        self.index(49)
        self.assertEqual(self.data()[1]["suggestions"], ["group docs/wiki/a/ (49 entries) under a/index.md"])


class DetachedHeadTests(CheckCase):
    def test_detached_head_still_checks(self):
        git(self.root, "checkout", "-q", "--detach")
        self.write_code(svc_source(tag="!"))
        self.assertEqual(self.check()[0], 1)


if __name__ == "__main__":
    unittest.main()
