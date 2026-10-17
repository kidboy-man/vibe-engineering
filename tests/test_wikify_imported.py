import json
import unittest
from unittest import mock

from agents.wikify import adopt_cmd, adopt_plan, check_cmd, commands, gitview, imported, imported_refs, state
from tests.test_wikify_state import git
from tests.wikify_adopt_helpers import AdoptCase
from tests.wikify_drift_helpers import quiet

STATE = "docs/wiki/.wikify.json"
PAGE = "w/overview.md"
PAGE_PATH = "docs/wiki/w/overview.md"


class ImportedCase(AdoptCase):
    """flat-docs adopted into w/ and marked; the two pages are registered imported pages."""

    def setUp(self):
        super().setUp()
        self.build("flat-docs")
        self.write_map("docs/** -> w/\n", commit=True)
        rc, out = quiet(adopt_cmd.cmd_adopt, self.root, apply=True)
        self.assertEqual(rc, 0, out)
        git(self.root, "commit", "-q", "-m", "docs(wiki): move docs")
        self.assertEqual(self.verify()[0], 0)
        self.assertEqual(quiet(commands.cmd_mark, self.root)[0], 0)
        git(self.root, "add", "--", "docs/wiki")
        git(self.root, "commit", "-q", "-m", "docs(wiki): adopt")

    def verify(self):
        return quiet(commands.cmd_verify, self.root)

    def mark(self):
        return quiet(commands.cmd_mark, self.root)

    def edit_page(self, extra="\nEdited line.\n", rel=PAGE_PATH):
        path = self.root / rel
        text = path.read_text()
        tail = adopt_plan.HUMAN_END + "\n"
        self.assertTrue(text.endswith(tail))
        path.write_text(text[: -len(tail)] + extra + tail)

    def commit_wiki(self):
        git(self.root, "add", "--", "docs/wiki")
        git(self.root, "commit", "-q", "-m", "docs(wiki): edit")


class ShapeTests(unittest.TestCase):
    def test_exactly_one_wrapper_is_imported_shape(self):
        wrapped = adopt_plan.wrap("docs/a.md", "# A\n\nbody\n")
        self.assertTrue(imported.is_imported_shape(wrapped))
        self.assertTrue(imported.is_imported_shape(adopt_plan.wrap("docs/a.md", "no newline")))

    def test_other_text_is_not_imported_shape(self):
        wrapped = adopt_plan.wrap("docs/a.md", "# A\n")
        for text in (
            "plain page\n",
            "<!-- wikify:human -->\nwhy\n<!-- /wikify:human -->\n",
            wrapped + "extra prose\n",
            "prefix\n" + wrapped,
            wrapped.replace("# A\n", "# A\n<!-- wikify:human -->\ninner\n<!-- /wikify:human -->\n"),
        ):
            self.assertFalse(imported.is_imported_shape(text), text)

    def test_page_hash_is_16_hex_and_content_sensitive(self):
        digest = imported.page_hash("abc\n")
        self.assertRegex(digest, r"^[0-9a-f]{16}$")
        self.assertNotEqual(digest, imported.page_hash("abd\n"))


class EditNoticeTests(ImportedCase):
    def test_adopt_registers_the_pages_it_creates(self):
        self.assertEqual(set(state.load(self.root)["imported"]), {"w/overview.md", "w/runbook.md"})

    def test_clean_pages_produce_no_notice(self):
        rc, out = self.verify()
        self.assertEqual(rc, 0)
        self.assertNotIn("IMPORTED PAGE", out)

    def test_edit_is_a_notice_not_an_error_and_hides_the_human_block_notice(self):
        self.edit_page()
        rc, out = self.verify()
        self.assertEqual(rc, 0, out)
        self.assertIn("IMPORTED PAGE EDITED: w/overview.md", out)
        self.assertNotIn("HUMAN BLOCK", out)

    def test_two_edits_before_mark_still_one_notice(self):
        self.edit_page("\nOne.\n")
        self.edit_page("\nTwo.\n")
        self.assertEqual(self.verify()[1].count("IMPORTED PAGE EDITED: w/overview.md"), 1)

    def test_mark_rerecords_and_the_notice_goes_away(self):
        self.edit_page()
        rc, out = self.mark()
        self.assertEqual(rc, 0, out)
        self.commit_wiki()
        self.assertNotIn("IMPORTED PAGE", self.verify()[1])
        self.assertEqual(state.load(self.root)["imported"]["w/overview.md"],
                         imported.page_hash((self.root / PAGE_PATH).read_text()))

    def test_check_lists_the_notice(self):
        self.edit_page()
        _, text = quiet(check_cmd.cmd_check, self.root)
        self.assertIn("IMPORTED PAGE EDITED: w/overview.md", text)

    def test_removed_registered_page_is_a_notice(self):
        (self.root / PAGE_PATH).unlink()
        git(self.root, "rm", "-q", "--cached", PAGE_PATH)
        rc, out = self.verify()
        self.assertIn("IMPORTED PAGE REMOVED: w/overview.md", out)


class UnregisteredTests(ImportedCase):
    def unregister(self):
        state.save(self.root, state.load(self.root)["covered"], imported={})
        self.commit_wiki()

    def test_unregistered_wrapper_behaves_as_a_human_block_page(self):
        self.unregister()
        self.edit_page()
        out = self.verify()[1]
        self.assertIn("HUMAN BLOCK CHANGED: w/overview.md", out)
        self.assertNotIn("IMPORTED PAGE", out)

    def test_mark_never_registers_a_page(self):
        self.unregister()
        self.assertEqual(self.mark()[0], 0)
        self.assertEqual(state.load(self.root)["imported"], {})

    def test_a_genuine_human_block_page_keeps_its_notice(self):
        page = self.root / "docs/wiki/notes.md"
        page.write_text("Fact (src: src/app.py:1-1)\n\n<!-- wikify:human -->\nwhy\n<!-- /wikify:human -->\n")
        index = self.root / "docs/wiki/index.md"
        index.write_text(index.read_text().replace(
            "<!-- /wikify:map -->", "- [Notes](notes.md) — when reading notes\n<!-- /wikify:map -->"))
        self.assertEqual(self.mark()[0], 0)
        self.commit_wiki()
        page.write_text(page.read_text().replace("why", "because"))
        self.assertIn("HUMAN BLOCK CHANGED: notes.md", self.verify()[1])


class SpoofTests(ImportedCase):
    def human_page(self):
        page = self.root / "docs/wiki/notes.md"
        page.write_text("Fact (src: src/app.py:1-1)\n\n<!-- wikify:human -->\nwhy\n<!-- /wikify:human -->\n")
        index = self.root / "docs/wiki/index.md"
        index.write_text(index.read_text().replace(
            "<!-- /wikify:map -->", "- [Notes](notes.md) — when reading notes\n<!-- /wikify:map -->"))
        return page

    def test_registering_a_genuine_human_block_page_by_hand_changes_nothing(self):
        page = self.human_page()
        self.assertEqual(self.mark()[0], 0)
        self.commit_wiki()
        st = state.load(self.root)
        state.save(self.root, st["covered"], imported={**st["imported"], "notes.md": imported.page_hash(page.read_text())})
        page.write_text(page.read_text().replace("why", "because"))
        out = self.verify()[1]
        self.assertIn("HUMAN BLOCK CHANGED: notes.md", out)
        self.assertNotIn("IMPORTED PAGE EDITED: notes.md", out)
        self.assertIn("notes.md is registered as imported but is no longer a wrapper", out)

    def test_mark_drops_a_registration_that_is_not_a_wrapper(self):
        self.human_page()
        st = state.load(self.root)
        state.save(self.root, st["covered"], imported={**st["imported"], "notes.md": "0123456789abcdef"})
        self.assertEqual(self.mark()[0], 0)
        self.assertNotIn("notes.md", state.load(self.root)["imported"])

    def test_appending_prose_outside_the_wrapper_makes_it_an_ordinary_page(self):
        self.edit_page()
        path = self.root / PAGE_PATH
        path.write_text(path.read_text() + "Uncited prose.\n")
        rc, out = self.verify()
        self.assertEqual(rc, 1)
        self.assertIn("uncited paragraph", out)


class FrozenTests(ImportedCase):
    def set_mode(self, mode):
        path = self.root / STATE
        data = json.loads(path.read_text())
        data["imported_mode"] = mode
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        self.commit_wiki()

    def test_frozen_turns_an_edit_into_an_error(self):
        self.set_mode("frozen")
        self.edit_page()
        rc, out = self.verify()
        self.assertEqual(rc, 1)
        self.assertIn("IMPORTED PAGE CHANGED (frozen): w/overview.md", out)

    def test_frozen_without_edits_is_clean(self):
        self.set_mode("frozen")
        self.assertEqual(self.verify()[0], 0)

    def test_invalid_mode_falls_back_to_editable_with_a_notice(self):
        self.set_mode("bogus")
        self.edit_page()
        rc, out = self.verify()
        self.assertEqual(rc, 0)
        self.assertIn("imported_mode", out)
        self.assertIn("IMPORTED PAGE EDITED", out)


class MigrateTests(ImportedCase):
    def legacy(self):
        state.save(self.root, state.load(self.root)["covered"], imported={})
        self.commit_wiki()

    def test_dry_run_lists_pages_and_writes_nothing(self):
        self.legacy()
        before = git(self.root, "status", "--porcelain")
        rc, out = quiet(imported.cmd_migrate, self.root, False)
        self.assertEqual(rc, 0)
        self.assertIn("would register: w/overview.md", out)
        self.assertEqual(git(self.root, "status", "--porcelain"), before)

    def test_apply_registers_wrapped_pages_and_touches_only_the_state_file(self):
        self.legacy()
        rc, out = quiet(imported.cmd_migrate, self.root, True)
        self.assertEqual(rc, 0, out)
        self.assertEqual(git(self.root, "status", "--porcelain", "--", ".").split(), ["M", STATE])
        self.assertEqual(set(state.load(self.root)["imported"]), {"w/overview.md", "w/runbook.md"})

    def test_apply_is_idempotent_and_skips_non_wrapper_pages(self):
        self.legacy()
        (self.root / "docs/wiki/plain.md").write_text("Plain (src: src/app.py:1-1)\n")
        quiet(imported.cmd_migrate, self.root, True)
        first = (self.root / STATE).read_text()
        rc, out = quiet(imported.cmd_migrate, self.root, True)
        self.assertEqual((self.root / STATE).read_text(), first)
        self.assertNotIn("plain.md", first)
        self.assertIn("nothing to register", out)

    def test_apply_refuses_a_symlinked_wiki(self):
        self.legacy()
        wiki = self.root / "docs/wiki"
        real = self.root / "docs/real"
        wiki.rename(real)
        wiki.symlink_to(real)
        rc, out = quiet(imported.cmd_migrate, self.root, True)
        self.assertEqual(rc, 1)
        self.assertIn("symlink", out)


BODY = (
    "# Overview\n\n"
    "See `src/app.py` and `docs/removed.md` and `Nonexistent_symbol` and `print`.\n\n"
    "Links: [gone](../gone.md), [ok](runbook.md), [web](https://x.io/a.md).\n\n"
    "```\n`docs/in-fence.md`\n```\n"
)


class ReferenceTests(ImportedCase):
    def set_body(self, body=BODY, rel=PAGE_PATH):
        (self.root / rel).write_text(adopt_plan.wrap("docs/overview.md", body))

    def find(self, at_head=False):
        from agents.wikify import drift
        pages = drift.read_pages(self.root, at_head)
        return imported_refs.find(self.root, pages, set(gitview.tracked_files(self.root)), [])

    def kinds(self, found):
        return sorted((f["kind"], f["token"]) for f in found)

    def test_dead_path_dead_symbol_and_stale_link(self):
        self.set_body()
        found = self.find()
        self.assertEqual(self.kinds(found), [
            ("DEAD PATH", "docs/removed.md"),
            ("DEAD SYMBOL", "Nonexistent_symbol"),
            ("STALE LINK", "../gone.md"),
        ])
        self.assertTrue(all(f["page"] == "w/overview.md" and f["line"] >= 3 for f in found))

    def test_partial_paths_and_qualified_names_are_not_dead_paths(self):
        # `service.go` style fragments match the tail of a tracked path; `pkg.Func` is no file
        (self.root / "pkg/port").mkdir(parents=True)
        (self.root / "pkg/port/service.go").write_text("package port\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "go file")
        self.set_body("# T\n\n`src/app.py` `port/service.go` `internal/app/server.Build` `x/app.py` `a/b.go`\n")
        self.assertEqual(self.kinds(self.find()), [("DEAD PATH", "a/b.go"), ("DEAD PATH", "x/app.py")])

    def test_line_numbers_are_page_lines(self):
        self.set_body()
        lines = (self.root / PAGE_PATH).read_text().splitlines()
        by_token = {f["token"]: f["line"] for f in self.find()}
        self.assertIn("docs/removed.md", lines[by_token["docs/removed.md"] - 1])
        self.assertIn("../gone.md", lines[by_token["../gone.md"] - 1])

    def test_unregistered_wrapper_pages_are_scanned_too(self):
        self.set_body()
        state.save(self.root, state.load(self.root)["covered"], imported={})
        self.assertEqual(len(self.find()), 3)

    def test_ordinary_pages_are_not_scanned(self):
        (self.root / "docs/wiki/plain.md").write_text("`docs/removed.md` (src: src/app.py:1-1)\n")
        self.set_body("# Fine\n")
        self.assertEqual(self.find(), [])

    def test_symbols_in_secret_paths_and_markdown_do_not_count(self):
        (self.root / ".env").write_text("OnlySecret=1\n")
        (self.root / "NOTES.md").write_text("OnlyInMarkdown\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "files")
        self.set_body("# T\n\n`OnlySecret` `OnlyInMarkdown`\n")
        self.assertEqual(self.kinds(self.find()), [("DEAD SYMBOL", "OnlyInMarkdown"), ("DEAD SYMBOL", "OnlySecret")])

    def test_a_token_that_looks_like_a_secret_is_never_echoed(self):
        self.set_body("# T\n\n`AKIAABCDEFGHIJKLMNOP` and `" + "x" * 300 + "`\n")
        rc, text = quiet(check_cmd.cmd_check, self.root)
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", text)
        self.assertNotIn("xxxxxxxxxx", text)
        self.assertEqual(self.find(), [])

    def test_each_tracked_file_is_read_once_however_many_tokens(self):
        self.set_body("# T\n\n" + " ".join(f"`Sym{n}`" for n in range(60)) + "\n")
        real = imported_refs._read_text
        with mock.patch.object(imported_refs, "_read_text", side_effect=real) as spy:
            self.find()
        self.assertLessEqual(spy.call_count, len(gitview.tracked_files(self.root)))

    def test_findings_never_change_the_check_exit_code_and_carry_the_floor_note(self):
        self.set_body()
        rc, text = quiet(check_cmd.cmd_check, self.root)
        self.assertEqual(rc, 0)
        self.assertIn("name-only matching is a floor", text)
        self.assertIn("DEAD PATH docs/removed.md", text)
        rc_ci, _ = quiet(check_cmd.cmd_check, self.root, True)
        self.assertEqual(rc_ci, 0)

    def test_json_lists_references(self):
        self.set_body()
        rc, text = quiet(check_cmd.cmd_check, self.root, False, True)
        data = json.loads(text)
        self.assertEqual(data["counts"]["references"], 3)
        self.assertEqual({r["kind"] for r in data["references"]}, {"DEAD PATH", "DEAD SYMBOL", "STALE LINK"})


class FixLinksTests(ImportedCase):
    def setUp(self):
        super().setUp()
        body = "# Overview\n\nRun `docs/runbook.md` or `docs/missing.md`.\n"
        (self.root / PAGE_PATH).write_text(adopt_plan.wrap("docs/overview.md", body))
        self.commit_wiki()

    def fix(self, apply=False):
        return quiet(imported_refs.cmd_fix_links, self.root, apply)

    def test_dry_run_prints_the_rewrite_and_writes_nothing(self):
        before = (self.root / PAGE_PATH).read_text()
        rc, out = self.fix()
        self.assertEqual(rc, 0)
        self.assertIn("`docs/runbook.md` -> `docs/wiki/w/runbook.md`", out)
        self.assertEqual((self.root / PAGE_PATH).read_text(), before)

    def test_apply_rewrites_only_mapped_dead_paths(self):
        rc, out = self.fix(apply=True)
        self.assertEqual(rc, 0, out)
        text = (self.root / PAGE_PATH).read_text()
        self.assertIn("`docs/wiki/w/runbook.md`", text)
        self.assertIn("`docs/missing.md`", text)  # not mapped to an existing page: untouched
        self.assertTrue(imported.is_imported_shape(text))

    def test_apply_records_the_hash_of_its_own_edit(self):
        self.fix(apply=True)
        self.assertNotIn("IMPORTED PAGE", self.verify()[1])
        self.assertEqual(self.mark()[0], 0)

    def test_unregistered_wrappers_and_other_pages_are_never_touched(self):
        state.save(self.root, state.load(self.root)["covered"], imported={})
        before = (self.root / PAGE_PATH).read_text()
        rc, out = self.fix(apply=True)
        self.assertEqual(rc, 1)
        self.assertIn("migrate-imported", out)
        self.assertEqual((self.root / PAGE_PATH).read_text(), before)

    def test_apply_keeps_the_hash_current_so_frozen_mode_accepts_the_tools_own_edit(self):
        path = self.root / STATE
        data = json.loads(path.read_text())
        data["imported_mode"] = "frozen"
        data["imported"]["w/overview.md"] = imported.page_hash((self.root / PAGE_PATH).read_text())
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        self.fix(apply=True)
        rc, out = self.verify()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("IMPORTED PAGE", out)

    def test_rewrite_does_not_touch_longer_paths_with_the_same_prefix(self):
        body = "# Overview\n\n`docs/runbook.md` and `docs/runbook.md.bak` and `docs/runbook.mdx:3`.\n"
        (self.root / PAGE_PATH).write_text(adopt_plan.wrap("docs/overview.md", body))
        self.fix(apply=True)
        text = (self.root / PAGE_PATH).read_text()
        self.assertIn("`docs/wiki/w/runbook.md`", text)
        self.assertIn("`docs/runbook.md.bak`", text)
        self.assertIn("`docs/runbook.mdx:3`", text)

    def test_nothing_to_fix(self):
        self.fix(apply=True)
        self.mark()
        rc, out = self.fix(apply=True)
        self.assertEqual(rc, 0)
        self.assertIn("nothing to fix", out)


if __name__ == "__main__":
    unittest.main()
