import unittest

from agents.wikify import check_cmd, commands, imported, reanchor, state
from tests.test_wikify_state import git
from tests.wikify_drift_helpers import CITE, PAGE, DriftCase, quiet, svc_source

HUMAN = "<!-- wikify:human -->\nOld note " + CITE + "\n<!-- /wikify:human -->\n"


class ReanchorCase(DriftCase):
    def run_reanchor(self, apply=False):
        return quiet(reanchor.cmd_reanchor, self.root, apply)

    def page_text(self):
        return (self.root / PAGE).read_bytes().decode()

    def keys(self):
        return state.load(self.root)["citations"]


class DryRunTests(ReanchorCase):
    def test_dry_run_prints_the_rewrite_and_changes_nothing(self):
        self.insert_lines_above(3)
        before = self.tree_hash()
        rc, text = self.run_reanchor()
        self.assertEqual(rc, 0)
        self.assertIn("svc.md:1: app/svc.py 10-20 -> 13-23 `handle`", text)
        self.assertEqual(self.tree_hash(), before)

    def test_nothing_to_heal(self):
        rc, text = self.run_reanchor()
        self.assertEqual(rc, 0)
        self.assertIn("nothing to re-anchor", text)


class ApplyTests(ReanchorCase):
    def test_apply_rewrites_only_the_digits_and_rekeys(self):
        self.insert_lines_above(15)
        old = self.page_text()
        old_hash = self.keys()["svc.md|app/svc.py:10-20|handle"]
        rc, _ = self.run_reanchor(apply=True)
        self.assertEqual(rc, 0)
        new = self.page_text()
        self.assertEqual(new, old.replace("app/svc.py:10-20", "app/svc.py:25-35"))
        keys = self.keys()
        self.assertEqual(keys, {"svc.md|app/svc.py:25-35|handle": old_hash})
        rc_check, _ = quiet(check_cmd.cmd_check, self.root)
        self.assertEqual(rc_check, 0)
        self.assertEqual(commands.run_verify(self.root)[0], 0)

    def test_small_shift_where_symbol_is_still_in_old_range_is_healed(self):
        self.insert_lines_above(2)
        self.run_reanchor(apply=True)
        self.assertIn("app/svc.py:12-22", self.page_text())

    def test_apply_keeps_crlf_endings(self):
        crlf = self.page_text().replace("\n", "\r\n")
        (self.root / PAGE).write_bytes(crlf.encode())
        self.insert_lines_above(3)
        self.run_reanchor(apply=True)
        self.assertEqual(self.page_text(), crlf.replace("10-20", "13-23"))

    def test_single_line_citation_keeps_its_form(self):
        self.write_code(svc_source().replace("def handle(x):", "def handle(x):  # one"))
        self.page("One (src: app/svc.py:10 `def handle`)\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "single")
        rc, _ = quiet(commands.cmd_mark, self.root)
        self.assertEqual(rc, 0)
        self.write_code(svc_source(top=2).replace("def handle(x):", "def handle(x):  # one"))
        self.run_reanchor(apply=True)
        self.assertIn("app/svc.py:12 `def handle`", self.page_text())

    def test_chained_moves_keep_each_citation_its_own_hash(self):
        """B's new range is A's old range and both cite the same symbol: re-keying must not
        let one overwrite the other."""
        block = lambda tag: [f"{tag} blk"] + [f"{tag} {n}" for n in range(1, 10)]
        text = "\n".join(["# pad"] * 4 + block("A") + block("B") + ["# tail"] * 4) + "\n"
        self.write_code(text, rel="app/two.py", msg="two blocks")
        self.page("A (src: app/two.py:5-14 `blk`)\n\nB (src: app/two.py:15-24 `blk`)\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "two cites")
        self.assertEqual(quiet(commands.cmd_mark, self.root)[0], 0)
        before = self.keys()
        hash_a, hash_b = before["svc.md|app/two.py:5-14|blk"], before["svc.md|app/two.py:15-24|blk"]
        self.assertNotEqual(hash_a, hash_b)
        self.write_code("# new\n" * 10 + text, rel="app/two.py", msg="shift 10")
        self.assertEqual(self.run_reanchor(apply=True)[0], 0)
        keys = self.keys()
        self.assertEqual(keys["svc.md|app/two.py:15-24|blk"], hash_a)  # A moved onto B's old range
        self.assertEqual(keys["svc.md|app/two.py:25-34|blk"], hash_b)
        self.assertEqual(len(keys), 2)
        rc, text_out = quiet(check_cmd.cmd_check, self.root)
        self.assertEqual(rc, 0, text_out)
        self.assertNotIn("moved", text_out)

    def test_only_the_moved_citation_in_a_page_changes(self):
        self.page("Handle " + CITE + "\n\nTail (src: app/svc.py:21-30)\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "two")
        quiet(commands.cmd_mark, self.root)
        self.insert_lines_above(2)
        self.run_reanchor(apply=True)
        self.assertEqual(self.page_text().count("app/svc.py:12-22"), 1)
        self.assertEqual(self.page_text().count("app/svc.py:23-32"), 1)


class RefusalTests(ReanchorCase):
    def test_ambiguous_relocation_is_refused_and_page_untouched(self):
        # no usable recorded commit (as after a rebase or squash): only the hash windows can decide
        state.save(self.root, "0" * 40, citations=self.keys())
        self.write_code(svc_source(top=3) + svc_source())
        before = self.page_text()
        rc, text = self.run_reanchor(apply=True)
        self.assertEqual(rc, 1)
        self.assertIn("refused", text)
        self.assertIn("ambiguous: 2 matches", text)
        self.assertEqual(self.page_text(), before)

    def test_changed_body_is_refused(self):
        self.write_code(svc_source(tag="!"))
        rc, text = self.run_reanchor(apply=True)
        self.assertEqual(rc, 1)
        self.assertIn("cited lines were edited", text)

    def test_citation_without_a_hash_is_never_healed(self):
        state.save(self.root, state.load(self.root)["covered"], citations={})
        self.insert_lines_above(15)
        before = self.page_text()
        rc, text = self.run_reanchor(apply=True)
        self.assertEqual(rc, 1)
        self.assertEqual(self.page_text(), before)

    def test_missing_symbol_is_not_a_refusal(self):
        self.write_code(svc_source().replace("def handle", "def other"))
        self.assertEqual(self.run_reanchor(apply=True)[0], 0)


class ScopeTests(ReanchorCase):
    def test_human_blocks_and_generated_pages_are_never_touched(self):
        self.page("Handle " + CITE + "\n\n" + HUMAN)
        generated = "<!-- wikify:generated -->\nDoc " + CITE + "\n"
        (self.root / "docs/wiki/sources").mkdir()
        (self.root / "docs/wiki/sources/g.md").write_text(generated)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "scope")
        quiet(commands.cmd_mark, self.root)
        self.insert_lines_above(3)
        self.run_reanchor(apply=True)
        text = self.page_text()
        self.assertIn("Old note (src: app/svc.py:10-20 `handle`)", text)
        self.assertEqual(text.count("app/svc.py:13-23"), 1)
        self.assertEqual((self.root / "docs/wiki/sources/g.md").read_text(), generated)

    def test_registered_imported_wrappers_are_skipped(self):
        from agents.wikify import adopt_plan
        self.page(adopt_plan.wrap("docs/svc.md", "Handle " + CITE + "\n"))
        st = state.load(self.root)
        state.save(self.root, st["covered"], imported={"svc.md": imported.page_hash(self.page_text())})
        self.insert_lines_above(3)
        before = self.page_text()
        self.run_reanchor(apply=True)
        self.assertEqual(self.page_text(), before)

    def test_a_registration_alone_does_not_exempt_an_ordinary_page(self):
        st = state.load(self.root)
        state.save(self.root, st["covered"], imported={"svc.md": "0123456789abcdef"})
        self.insert_lines_above(3)
        self.run_reanchor(apply=True)
        self.assertIn("app/svc.py:13-23", self.page_text())

    def test_symlinked_wiki_is_refused(self):
        wiki = self.root / "docs/wiki"
        real = self.root / "docs/real"
        wiki.rename(real)
        wiki.symlink_to(real)
        self.insert_lines_above(3)
        rc, text = self.run_reanchor(apply=True)
        self.assertEqual(rc, 1)
        self.assertIn("symlink", text)


class MarkReanchorTests(ReanchorCase):
    def test_mark_reanchor_heals_then_verifies_and_records(self):
        self.insert_lines_above(3)
        rc, text = quiet(commands.cmd_mark, self.root, True)
        self.assertEqual(rc, 0, text)
        self.assertIn("app/svc.py:13-23", self.page_text())
        self.assertIn("svc.md|app/svc.py:13-23|handle", self.keys())

    def test_plain_mark_after_a_small_shift_does_not_bless_the_old_lines(self):
        self.insert_lines_above(2)  # the symbol stays inside 10-20, so verify passes
        rc, out = quiet(commands.cmd_mark, self.root)
        self.assertEqual(rc, 0, out)
        self.assertIn("1 citation(s) moved", out)
        self.assertIn("svc.md|app/svc.py:10-20|handle", self.keys())
        _, text = quiet(check_cmd.cmd_check, self.root)
        self.assertIn("moved", text)
        self.assertEqual(self.run_reanchor(apply=True)[0], 0)
        self.assertIn("app/svc.py:12-22", self.page_text())
        self.assertIn("svc.md|app/svc.py:12-22|handle", self.keys())

    def test_mark_refuses_an_unparseable_state_file(self):
        (self.root / "docs/wiki/.wikify.json").write_text("<<<<<<< ours\n")
        rc, out = quiet(commands.cmd_mark, self.root)
        self.assertEqual(rc, 1)
        self.assertIn("not marked", out)
        self.assertIn("not valid JSON", out)

    def test_mark_without_reanchor_still_fails_on_a_moved_citation(self):
        self.insert_lines_above(15)
        rc, text = quiet(commands.cmd_mark, self.root)
        self.assertEqual(rc, 1)
        self.assertIn("not marked", text)


if __name__ == "__main__":
    unittest.main()
