import contextlib
import hashlib
import io
import json
import unittest
from pathlib import Path

from agents.wikify import adopt_plan as ap
from agents.wikify import adopt_cmd, adopt_refs
from agents.wikify import citations, state
from tests.test_wikify_state import git
from tests.wikify_adopt_helpers import AdoptCase, MAPPING, validate

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
        self.assertEqual(refs["docs/trd/payments.md"], [])

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


if __name__ == "__main__":
    unittest.main()
