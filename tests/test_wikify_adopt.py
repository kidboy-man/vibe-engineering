import contextlib
import hashlib
import io
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from agents.wikify import adopt_plan as ap
from agents.wikify import adopt_cmd, adopt_refs, agentmap, commands, docs_cmd, docs_inventory, gitview, plan
from agents.wikify import citations, state
from tests.test_wikify_state import git
from tests.wikify_adopt_helpers import FIXTURES, AdoptCase, MAPPING, validate

SPEC = Path(__file__).resolve().parents[1] / "specs" / "001-vibe-kits-baseline"


def rules(text):
    parsed, errors = ap.parse_rules(text.splitlines())
    assert not errors, errors
    return parsed


class MappingTests(unittest.TestCase):
    def test_parses_rules_comments_and_kinds(self):
        parsed = rules("# c\n\ndocs/trd/** -> specs/trd/ kind=spec\ndocs/x.md -> misc/\n")
        self.assertEqual([(r.glob, r.folder, r.kind) for r in parsed],
                         [("docs/trd/**", "specs/trd/", "spec"), ("docs/x.md", "misc/", "reference")])

    def test_rejects_bad_lines(self):
        for line in ("no arrow", "a -> b", "a -> /abs/", "a -> ../x/", "a -> sources/x/",
                     "a -> x/ kind=bogus", "a -> x/ y z", "a -> x\\y/", "a -> -> "):
            with self.subTest(line=line):
                self.assertTrue(ap.parse_rules([line])[1])

    def test_limits(self):
        many = [f"d{i}/** -> w/" for i in range(citations.MAX_IGNORE_PATTERNS + 1)]
        self.assertTrue(ap.parse_rules(many)[1])
        wild = "a" + "*/" * (citations.MAX_IGNORE_WILDCARDS + 1) + " -> w/"
        self.assertTrue(ap.parse_rules([wild])[1])

    def test_first_match_wins_and_destination_keeps_subdirs(self):
        r = rules("docs/trd/** -> specs/trd/ kind=spec\ndocs/** -> other/\n")
        rule = ap.match(r, "docs/trd/auth/tokens.md")
        self.assertEqual(rule.folder, "specs/trd/")
        self.assertEqual(ap.destination(rule, "docs/trd/auth/tokens.md"), "specs/trd/auth/tokens.md")
        self.assertEqual(ap.destination(ap.match(r, "docs/z.md"), "docs/z.md"), "other/z.md")
        self.assertIsNone(ap.match(r, "src/z.md"))

    def test_destination_rejects_non_md(self):
        r = rules("docs/** -> w/\n")
        self.assertIsNone(ap.destination(r[0], "docs/a.txt"))
        self.assertEqual(ap.destination(r[0], "docs/a.md"), "w/a.md")

    def test_root_files_need_an_exact_rule(self):
        r = rules("*.md -> w/\nREADME.md -> keep/\n")
        self.assertTrue(ap.names_exactly(r, "README.md"))
        self.assertFalse(ap.names_exactly(rules("*.md -> w/\n"), "README.md"))


class WrapTests(unittest.TestCase):
    def test_roundtrip_with_and_without_trailing_newline(self):
        for body in ("# T\n\nx\n", "no newline", "", "\n", "a\r\nb\r\n"):
            with self.subTest(body=body):
                page = ap.wrap("docs/a.md", body)
                self.assertTrue(page.startswith(ap.HUMAN_BEGIN + "\n<!-- imported from=docs/a.md"))
                self.assertTrue(ap.is_wrapped(page))
                self.assertEqual(ap.unwrap(page), ("docs/a.md", body))

    def test_hash_is_of_the_original_bytes(self):
        body = "# T\n"
        self.assertEqual(ap.sha256(body.encode()), hashlib.sha256(b"# T\n").hexdigest())

    def test_body_with_human_markers_is_refused(self):
        self.assertIsNotNone(ap.body_error("x <!-- wikify:human --> y"))
        self.assertIsNotNone(ap.body_error("x <!-- /wikify:human --> y"))
        self.assertIsNone(ap.body_error("# plain\n"))

    def test_unwrap_rejects_other_text(self):
        self.assertIsNone(ap.unwrap("# plain\n"))
        self.assertIsNone(ap.unwrap(ap.HUMAN_BEGIN + "\nhand written\n" + ap.HUMAN_END + "\n"))

    def test_provenance_path_must_be_citable(self):
        self.assertTrue(ap.provenance_ok("docs/a.md"))
        self.assertFalse(ap.provenance_ok("docs/a b.md"))
        self.assertFalse(ap.provenance_ok("docs/a-->b.md"))


class ControlFileTests(AdoptCase):
    def test_wikifymap_is_a_control_file(self):
        self.assertIn(".wikifymap", citations.CONTROL_FILES)
        self.assertIn("docs/wiki/.wikifymap", state.CONTROL_RELS)

    def test_wikifymap_is_not_a_layout_error(self):
        self.build("flat-docs")
        self.write_map("docs/** -> w/\n")
        errors, pages = citations.walk_wiki(self.root)
        self.assertEqual(errors, [])
        self.assertNotIn(".wikifymap", [rel for rel, _ in pages])


class ClassifyTests(AdoptCase):
    def plan(self, mapping=MAPPING):
        if not (self.root / "docs").exists():
            self.build("nested-docs")
        self.write_map(mapping)
        parsed, errors = ap.load_rules(self.root)
        self.assertEqual(errors, [])
        result = ap.plan_candidates(self.root, parsed)
        self.assertIsNone(result.error)
        return {c.source: c for c in result.candidates}

    def test_moves_get_destination_kind_and_hash(self):
        c = self.plan()
        t = c["docs/trd/auth/tokens.md"]
        self.assertEqual((t.destination, t.kind, t.reason), ("specs/trd/auth/tokens.md", "spec", None))
        self.assertEqual(t.sha256, ap.sha256(b"# Tokens\n\nBody without trailing newline"))
        self.assertEqual(c["docs/adr/0001.md"].destination, "decisions/0001.md")
        self.assertEqual(c["docs/adr/0001.md"].kind, "adr")

    def test_skip_reasons(self):
        c = self.plan()
        self.assertEqual(c["docs/guide.markdown"].reason, "non-markdown")
        self.assertEqual(c["docs/secret-notes.md"].reason, "secret-hit")
        self.assertEqual(c["docs/build.md"].reason, "build-coupled")
        self.assertEqual(c["README.md"].reason, "unmapped")
        for source in ("docs/guide.markdown", "docs/secret-notes.md", "docs/build.md"):
            self.assertEqual(c[source].kind, "skipped")
            self.assertEqual(c[source].destination, "")

    def test_root_file_needs_exact_rule(self):
        c = self.plan(MAPPING + "*.md -> misc/\n")
        self.assertEqual(c["README.md"].reason, "root-file")
        c = self.plan(MAPPING + "README.md -> misc/\n")
        self.assertEqual(c["README.md"].reason, "build-coupled")  # pyproject.toml reads it

    def test_collision_with_existing_page_and_duplicates(self):
        self.build("flat-docs")
        (self.root / "docs/wiki/specs").mkdir()
        (self.root / "docs/wiki/specs/overview.md").write_text("# hand written\n")
        (self.root / "docs/wiki/specs/Runbook.md").write_text("# hand written\n")
        self.write_map("docs/overview.md -> specs/\ndocs/runbook.md -> specs/\n")
        parsed, _ = ap.load_rules(self.root)
        got = {c.source: c.reason for c in ap.plan_candidates(self.root, parsed).candidates}
        self.assertEqual(got, {"docs/overview.md": "collision", "docs/runbook.md": "collision"})

    def test_body_with_human_marker_is_unsafe(self):
        self.build("flat-docs")
        (self.root / "docs/overview.md").write_text("# O\n<!-- wikify:human -->\n")
        from tests.test_wikify_state import git
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "x")
        self.write_map("docs/** -> w/\n")
        parsed, _ = ap.load_rules(self.root)
        got = {c.source: c.reason for c in ap.plan_candidates(self.root, parsed).candidates}
        self.assertEqual(got["docs/overview.md"], "unsafe-body")
        self.assertIsNone(got["docs/runbook.md"])

    def test_no_rules_means_everything_is_unmapped(self):
        self.build("flat-docs")
        got = {c.source: c.reason for c in ap.plan_candidates(self.root, []).candidates}
        self.assertEqual(set(got.values()), {"unmapped"})

    def test_destinations_are_unique_even_when_rules_overlap(self):
        self.build("flat-docs")
        (self.root / "docs/sub").mkdir()
        (self.root / "docs/sub/overview.md").write_text("# s\n")
        from tests.test_wikify_state import git
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "x")
        self.write_map("docs/*.md -> w/\ndocs/sub/*.md -> w/\n")
        parsed, _ = ap.load_rules(self.root)
        got = {c.source: c.reason for c in ap.plan_candidates(self.root, parsed).candidates}
        self.assertEqual(got["docs/overview.md"], None)
        self.assertEqual(got["docs/sub/overview.md"], "collision")


class RefsTests(AdoptCase):
    def test_finds_links_and_paths_and_skips_wiki(self):
        self.build("nested-docs")
        refs = adopt_refs.scan(self.root, ["docs/adr/0001.md", "docs/trd/payments.md", "docs/build.md"])
        adr = {(r.file, r.kind) for r in refs["docs/adr/0001.md"]}
        self.assertIn(("docs/trd/payments.md", "link"), adr)
        self.assertIn(("src/app.py", "path"), adr)
        self.assertEqual([(r.file, r.kind) for r in refs["docs/build.md"]], [("Makefile", "path")])
        self.assertEqual([(r.file, r.kind) for r in refs["docs/trd/payments.md"]], [("docs/overview.md", "link")])

    def test_is_config(self):
        for name in ("pyproject.toml", "Makefile", "a/b/ci.yml", "package.json", "Dockerfile"):
            self.assertTrue(adopt_refs.is_config(name), name)
        for name in ("src/a.py", "README.md", "docs/a.md"):
            self.assertFalse(adopt_refs.is_config(name), name)


class DryRunTests(AdoptCase):
    def run_adopt(self, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = adopt_cmd.cmd_adopt(self.root, **kw)
        return rc, buf.getvalue()

    def snapshot(self):
        return git(self.root, "status", "--porcelain", "--untracked-files=all"), git(self.root, "rev-parse", "HEAD")

    def test_dry_run_lists_moves_skips_and_refs_and_writes_nothing(self):
        self.build("nested-docs")
        self.write_map()
        before = self.snapshot()
        rc, out = self.run_adopt()
        self.assertEqual(rc, 0)
        self.assertIn("move docs/adr/0001.md -> docs/wiki/decisions/0001.md [adr]", out)
        self.assertIn("move docs/trd/auth/tokens.md -> docs/wiki/specs/trd/auth/tokens.md [spec]", out)
        self.assertIn("skip docs/build.md: build-coupled", out)
        self.assertIn("skip docs/secret-notes.md: secret-hit", out)
        self.assertIn("skip README.md: unmapped", out)
        self.assertIn("ref docs/trd/payments.md:3 (link)", out)  # to docs/adr/0001.md
        self.assertIn("dry run: no files written", out)
        self.assertEqual(self.snapshot(), before)

    def test_without_a_mapping_everything_is_unmapped(self):
        self.build("flat-docs")
        rc, out = self.run_adopt()
        self.assertEqual(rc, 0)
        self.assertIn("skip docs/overview.md: unmapped", out)
        self.assertNotIn("move docs/", out)

    def test_refuses_outside_git_and_without_wiki_index(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(adopt_cmd.cmd_adopt(tmp), 1)
            self.assertIn("not a git repository", buf.getvalue())
        self.build("flat-docs", init=False)
        rc, out = self.run_adopt()
        self.assertEqual(rc, 1)
        self.assertIn("run vibe wikify init first", out)

    def test_bad_mapping_is_refused(self):
        self.build("flat-docs")
        self.write_map("docs/** -> ../escape/\n")
        rc, out = self.run_adopt()
        self.assertEqual(rc, 1)
        self.assertIn("refused:", out)
        self.assertIn(".wikifymap:1", out)

    def test_map_option_reads_another_file(self):
        self.build("flat-docs")
        other = self.root / "elsewhere.map"
        other.write_text("docs/** -> w/\n")
        rc, out = self.run_adopt(map_file=str(other))
        self.assertIn("move docs/overview.md -> docs/wiki/w/overview.md [reference]", out)

    def test_include_and_exclude_narrow_the_set(self):
        self.build("flat-docs")
        self.write_map("docs/** -> w/\n")
        _, out = self.run_adopt(include=["docs/over*"])
        self.assertIn("docs/overview.md", out)
        self.assertNotIn("docs/runbook.md", out)
        _, out = self.run_adopt(exclude=["docs/over*"])
        self.assertNotIn("docs/overview.md", out)
        self.assertIn("docs/runbook.md", out)

    def test_untrusted_paths_are_printed_safely(self):
        self.build("flat-docs")
        weird = self.root / "docs" / "a\x1b[31mb.md"
        weird.write_text("# x\n")
        from tests.test_wikify_state import git as g
        g(self.root, "add", "-A")
        g(self.root, "commit", "-q", "-m", "w")
        _, out = self.run_adopt()
        self.assertNotIn("\x1b", out)


class ReportTests(AdoptCase):
    def report(self, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = adopt_cmd.cmd_adopt(self.root, report=True, **kw)
        self.assertEqual(rc, 0)
        return json.loads(buf.getvalue())  # stdout is JSON only

    def test_report_matches_the_schema(self):
        self.build("nested-docs")
        self.write_map()
        data = self.report()
        schema = json.loads((SPEC / "contracts/adopt-report.schema.json").read_text())
        self.assertEqual(validate(data, schema), [])

    def test_report_content(self):
        self.build("nested-docs")
        self.write_map()
        data = self.report()
        moves = {m["source"]: m for m in data["moves"]}
        self.assertEqual(moves["docs/adr/0001.md"]["kind"], "adr")
        self.assertEqual(moves["docs/adr/0001.md"]["body_sha256"], ap.sha256(b"# ADR 1\n\nDecision.\n"))
        skips = {s["source"]: s["reason"] for s in data["skips"]}
        self.assertEqual(skips["docs/build.md"], "build-coupled")
        self.assertIn("README.md", data["unclassified"])
        self.assertIn("docs/img/d.png", {r["target"] for r in data["unresolved_refs"]})
        self.assertIn("src/app.py", {r["file"] for r in data["unresolved_refs"]})
        self.assertIn("docs/adr/0001.md", data["commit_plan"]["outside_wiki"])
        self.assertIn("docs/wiki/decisions/0001.md", data["commit_plan"]["wiki_only"])

    def test_report_writes_nothing(self):
        self.build("nested-docs")
        self.write_map()
        before = git(self.root, "status", "--porcelain")
        self.report()
        self.assertEqual(git(self.root, "status", "--porcelain"), before)


class ApplyCase(AdoptCase):
    def apply(self, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = adopt_cmd.cmd_adopt(self.root, apply=True, **kw)
        return rc, buf.getvalue()

    def verify(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = commands.cmd_verify(self.root)
        return rc, buf.getvalue()

    def mark(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = commands.cmd_mark(self.root)
        return rc, buf.getvalue()

    def cycle(self, **kw):
        """apply, commit 1 (staged renames), verify, mark, commit 2 (docs only)."""
        rc, out = self.apply(**kw)
        self.assertEqual(rc, 0, out)
        git(self.root, "commit", "-q", "-m", "docs(wiki): move docs")
        rc, out = self.verify()
        self.assertEqual(rc, 0, out)
        rc, out = self.mark()
        self.assertEqual(rc, 0, out)
        git(self.root, "add", "--", "docs/wiki")
        git(self.root, "commit", "-q", "-m", "docs(wiki): adopt")

    def read(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")


class ApplyTests(ApplyCase):
    def test_moves_wrap_and_keep_history(self):
        self.build("nested-docs")
        self.write_map()
        rc, out = self.apply()
        self.assertEqual(rc, 0, out)
        self.assertFalse((self.root / "docs/adr/0001.md").exists())
        self.assertEqual(ap.unwrap(self.read("docs/wiki/decisions/0001.md")), ("docs/adr/0001.md", "# ADR 1\n\nDecision.\n"))
        self.assertEqual(
            ap.unwrap(self.read("docs/wiki/specs/trd/auth/tokens.md")),
            ("docs/trd/auth/tokens.md", "# Tokens\n\nBody without trailing newline"),
        )
        staged = git(self.root, "diff", "--cached", "--name-status", "-M")
        self.assertEqual(sorted(l.split("\t")[0] for l in staged.splitlines()), ["R100"] * 3)  # pure renames
        git(self.root, "commit", "-q", "-m", "move")
        log = git(self.root, "log", "--follow", "--format=%s", "--", "docs/wiki/decisions/0001.md")
        self.assertIn("init", log.splitlines())

    def test_skipped_docs_stay_and_output_says_what_to_do_next(self):
        self.build("nested-docs")
        self.write_map()
        rc, out = self.apply()
        for rel in ("docs/build.md", "docs/secret-notes.md", "docs/guide.markdown", "README.md", "docs/img/d.png"):
            self.assertTrue((self.root / rel).exists(), rel)
        self.assertIn("git commit", out)
        self.assertIn("vibe wikify mark", out)

    def test_bodies_are_hash_equal_after_the_full_cycle(self):
        self.build("nested-docs")
        self.write_map()
        want = {m["source"]: m for m in json.loads(self._report())["moves"]}
        self.cycle()
        for source, m in want.items():
            src, body = ap.unwrap(self.read(m["destination"]))
            self.assertEqual(src, source)
            self.assertEqual(ap.sha256(body.encode()), m["body_sha256"])

    def _report(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            adopt_cmd.cmd_adopt(self.root, report=True)
        return buf.getvalue()

    def test_dirty_tree_and_detached_head_are_refused_without_force(self):
        self.build("flat-docs")
        self.write_map("docs/** -> w/\n")
        (self.root / "scratch.txt").write_text("x")
        rc, out = self.apply()
        self.assertEqual(rc, 1)
        self.assertIn("uncommitted changes", out)
        self.assertTrue((self.root / "docs/overview.md").exists())
        rc, out = self.apply(force=True)
        self.assertEqual(rc, 0, out)
        (self.root / "scratch.txt").unlink()
        git(self.root, "reset", "-q", "--hard")
        git(self.root, "clean", "-fdq")
        git(self.root, "checkout", "-q", "--detach")
        rc, out = self.apply()
        self.assertEqual(rc, 1)
        self.assertIn("detached HEAD", out)

    def test_existing_destination_is_never_overwritten(self):
        self.build("flat-docs")
        (self.root / "docs/wiki/w").mkdir()
        (self.root / "docs/wiki/w/overview.md").write_text("# mine\n")
        self.write_map("docs/** -> w/\n")
        rc, out = self.apply()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.read("docs/wiki/w/overview.md"), "# mine\n")
        self.assertTrue((self.root / "docs/overview.md").exists())
        self.assertIn("skip docs/overview.md: collision", out)

    def test_nothing_to_move_is_a_no_op(self):
        self.build("empty-docs")
        self.write_map("docs/** -> w/\n")
        before = git(self.root, "status", "--porcelain")
        rc, out = self.apply()
        self.assertEqual(rc, 0)
        self.assertIn("nothing to move", out)
        self.assertEqual(git(self.root, "status", "--porcelain"), before)


class IdempotenceTests(ApplyCase):
    def test_second_apply_after_both_commits_changes_nothing(self):
        self.build("nested-docs")
        self.write_map()
        self.cycle()
        head = git(self.root, "rev-parse", "HEAD")
        rc, out = self.apply()
        self.assertEqual(rc, 0, out)
        self.assertIn("nothing to move", out)
        self.assertEqual(git(self.root, "status", "--porcelain"), "")
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), head)

    def test_interrupted_run_needs_force_and_then_completes(self):
        self.build("flat-docs")
        self.write_map("docs/** -> w/\n")
        real = gitview.run_git
        calls = {"mv": 0}

        def flaky(root, *args):
            if args and args[0] == "mv":
                calls["mv"] += 1
                if calls["mv"] == 2:
                    return subprocess.CompletedProcess(args, 1, "", "boom")
            return real(root, *args)

        with mock.patch.object(gitview, "run_git", flaky):
            rc, out = self.apply()
        self.assertEqual(rc, 1)
        self.assertIn("--force", out)
        rc, out = self.apply()
        self.assertEqual(rc, 1)
        self.assertIn("uncommitted changes", out)
        rc, out = self.apply(force=True)
        self.assertEqual(rc, 0, out)
        for name in ("overview", "runbook"):
            self.assertTrue(ap.is_wrapped(self.read(f"docs/wiki/w/{name}.md")))
            self.assertFalse((self.root / f"docs/{name}.md").exists())
        index = self.read("docs/wiki/index.md")
        self.assertEqual(index.count("(w/overview.md)"), 1)
        self.assertEqual(index.count("(w/runbook.md)"), 1)


class MapAndOutlineTests(ApplyCase):
    def outline_and_map(self):
        """flat docs with generated outline pages, and sources/index.md listed in the map."""
        self.build("flat-docs")
        with contextlib.redirect_stdout(io.StringIO()):
            docs_cmd.cmd_docs(self.root)
        index = self.root / "docs/wiki/index.md"
        index.write_text(index.read_text().replace(
            "<!-- /wikify:map -->", "- [Sources](sources/index.md) \u2014 outline pages\n<!-- /wikify:map -->"))
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "outline")

    def test_map_entries_and_verify_after_commit_one(self):
        self.build("nested-docs")
        self.write_map()
        rc, out = self.apply()
        self.assertEqual(rc, 0, out)
        index = self.read("docs/wiki/index.md")
        self.assertIn("(decisions/0001.md) \u2014 imported from docs/adr/0001.md", index)
        self.assertIn("[Payments TRD](specs/trd/payments.md)", index)
        git(self.root, "commit", "-q", "-m", "move")
        rc, out = self.verify()
        self.assertEqual(rc, 0, out)

    def test_map_caps_group_pages_under_folder_indexes(self):
        self.build("empty-docs")
        for i in range(70):
            (self.root / f"docs/d{i:02d}.md").write_text(f"# Doc {i}\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "docs")
        self.write_map("docs/** -> pages/\n")
        self.cycle()
        index = self.read("docs/wiki/index.md")
        self.assertIn("(pages/index.md)", index)
        self.assertLessEqual(len(agentmap.parse_map(index).entries), agentmap.MAX_ENTRIES)
        self.assertEqual(self.read("docs/wiki/pages/index.md").count("](d"), 70)

    def test_outline_pages_of_moved_docs_are_removed_and_index_rewritten(self):
        self.outline_and_map()
        self.write_map("docs/overview.md -> w/\n")
        self.cycle()
        self.assertFalse((self.root / "docs/wiki/sources/docs/overview.md").exists())
        self.assertTrue((self.root / "docs/wiki/sources/docs/runbook.md").exists())
        idx = self.read("docs/wiki/sources/index.md")
        self.assertNotIn("overview", idx)
        self.assertIn("runbook", idx)
        expected, _ = docs_inventory.expected_pages(self.root)
        self.assertEqual(idx, expected["sources/index.md"])

    def test_outline_index_is_removed_when_no_rows_remain(self):
        self.outline_and_map()
        self.write_map("docs/** -> w/\n")
        self.cycle()
        self.assertFalse((self.root / "docs/wiki/sources/index.md").exists())

    def test_unrelated_stale_outline_pages_need_prune_sources(self):
        self.outline_and_map()
        stale = self.root / "docs/wiki/sources/docs/gone.md"
        stale.write_text(docs_inventory.MARKER + "\n# gone\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "stale")
        self.write_map("docs/overview.md -> w/\n")
        rc, out = self.apply()
        self.assertEqual(rc, 0, out)
        self.assertTrue(stale.exists())
        self.assertIn("stale docs/wiki/sources/docs/gone.md", out)
        git(self.root, "reset", "-q", "--hard")
        git(self.root, "clean", "-fdq")
        rc, out = self.apply(prune_sources=True)
        self.assertEqual(rc, 0, out)
        self.assertFalse(stale.exists())

    def test_plan_is_clean_after_the_full_cycle(self):
        self.outline_and_map()
        self.write_map("docs/** -> w/\n")
        self.cycle()
        result = plan.build_plan(self.root)
        self.assertIsNone(result["error"])
        self.assertEqual(result["docs_unindexed"], [])
        self.assertEqual(result["docs_stale"], [])
        self.assertEqual(result["map_missing"], [])
        self.assertEqual(result["uncovered"], [])

    def test_commit_plan_is_printed_and_nothing_is_committed(self):
        self.build("flat-docs")
        self.write_map("docs/** -> w/\n")
        head = git(self.root, "rev-parse", "HEAD")
        rc, out = self.apply()
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), head)
        for step in ("1. git commit", "2. vibe wikify verify", "3. git add -- docs/wiki"):
            self.assertIn(step, out)


class RewriteTests(unittest.TestCase):
    MOVED = {"docs/adr/0001.md": "docs/wiki/decisions/0001.md"}

    def test_links_follow_moved_docs_and_assets_keep_their_target(self):
        text = "See [ADR](../adr/0001.md#x) and ![d](../img/d.png)\n"
        got, n = adopt_refs.rewrite_links(text, "docs/trd", "docs/wiki/specs/trd", self.MOVED)
        self.assertEqual(got, "See [ADR](../../decisions/0001.md#x) and ![d](../../../img/d.png)\n")
        self.assertEqual(n, 2)

    def test_urls_anchors_absolute_and_fences_are_left_alone(self):
        text = "[u](https://x.io/a.md) [a](#top) [r](/abs.md)\n```\n[c](../adr/0001.md)\n```\n"
        self.assertEqual(adopt_refs.rewrite_links(text, "docs/trd", "docs/wiki/x", self.MOVED), (text, 0))

    def test_unchanged_links_are_not_counted(self):
        self.assertEqual(adopt_refs.rewrite_links("[a](b.md)", "docs", "docs", {}), ("[a](b.md)", 0))


class RewriteApplyTests(ApplyCase):
    def prepare(self):
        self.build("nested-docs")
        self.write_map()

    def test_default_leaves_bodies_byte_identical(self):
        self.prepare()
        self.cycle()
        _, body = ap.unwrap(self.read("docs/wiki/specs/trd/payments.md"))
        self.assertEqual(body, FIXTURES["nested-docs"]["docs/trd/payments.md"])
        self.assertIn("(trd/payments.md)", self.read("docs/overview.md"))

    def test_rewrite_refs_fixes_moved_bodies_and_incoming_docs_links(self):
        self.prepare()
        rc, out = self.apply(rewrite_refs=True)
        self.assertEqual(rc, 0, out)
        _, body = ap.unwrap(self.read("docs/wiki/specs/trd/payments.md"))
        self.assertIn("[ADR](../../decisions/0001.md)", body)
        self.assertIn("![d](../../../img/d.png)", body)
        original = FIXTURES["nested-docs"]["docs/trd/payments.md"]
        want, _ = adopt_refs.rewrite_links(
            original, "docs/trd", "docs/wiki/specs/trd",
            {"docs/adr/0001.md": "docs/wiki/decisions/0001.md", "docs/trd/payments.md": "docs/wiki/specs/trd/payments.md"},
        )
        self.assertEqual(body, want)  # equal after the same link substitutions, nothing else
        self.assertIn("(wiki/specs/trd/payments.md)", self.read("docs/overview.md"))
        self.assertIn("https://x.io/a.md", self.read("docs/overview.md"))
        names = git(self.root, "diff", "--cached", "--name-status", "-M").splitlines()
        self.assertEqual(sorted(l.split("\t")[0] for l in names), ["M", "R100", "R100", "R100"])

    def test_rewrite_refs_cycle_verifies_and_unresolved_shrinks(self):
        self.prepare()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            adopt_cmd.cmd_adopt(self.root, report=True, rewrite_refs=True)
        data = json.loads(buf.getvalue())
        targets = {r["target"] for r in data["unresolved_refs"]}
        self.assertNotIn("docs/img/d.png", targets)  # rewritten, no longer unresolved
        self.assertIn("src/app.py", {r["file"] for r in data["unresolved_refs"]})  # code comment: only listed
        self.assertIn("docs/overview.md", data["commit_plan"]["outside_wiki"])
        self.cycle(rewrite_refs=True)


if __name__ == "__main__":
    unittest.main()
