import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (
    ROOT / "agents" / "kits" / "workflow" / "templates" / "workflow" / "shared"
    / "skills" / "vibe-flow" / "scripts" / "check_trace.py"
)

spec = importlib.util.spec_from_file_location("check_trace", SCRIPT)
ct = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ct  # dataclasses resolve annotations via sys.modules
spec.loader.exec_module(ct)

PRD = """# PRD: Checkout

### R-001: Login
Priority: Must
Given a user, when they log in, then they see the dashboard.

### R-002: Export
**Priority:** Should

## Requirements notes
### R-003: Audit log
Priority: must
"""

REQS = {"R-001": "must", "R-002": "should", "R-003": "must"}


def ticket(tid, implements=(), blocked_by=(), status="todo", file=None):
    return {
        "id": tid,
        "implements": list(implements),
        "blocked_by": list(blocked_by),
        "status": status,
        "file": file or f"issue-{tid}.md",
    }


def write_ticket(directory: Path, name: str, body: str) -> None:
    (directory / name).write_text(body, encoding="utf-8")


class FrontmatterTests(unittest.TestCase):
    def test_parses_scalars_lists_and_quotes(self):
        text = '---\ntitle: "Add login"\nid: T-01\nimplements: [R-001, R-002]\nblocked_by: []\nstatus: todo\n---\n# body\n'
        meta, errors = ct.parse_frontmatter(text)
        self.assertEqual(errors, [])
        self.assertEqual(meta["title"], "Add login")
        self.assertEqual(meta["id"], "T-01")
        self.assertEqual(meta["implements"], ["R-001", "R-002"])
        self.assertEqual(meta["blocked_by"], [])

    def test_missing_frontmatter_is_an_error(self):
        meta, errors = ct.parse_frontmatter("# just a body\n")
        self.assertEqual(meta, {})
        self.assertTrue(errors)

    def test_malformed_line_is_reported(self):
        _, errors = ct.parse_frontmatter("---\nid T-01\n---\n")
        self.assertTrue(any("id T-01" in e for e in errors))

    def test_block_style_lists_match_flow_style(self):
        block = "---\nid: T-02\nimplements:\n  - R-001\n  - \"R-002\"\nblocked_by:\n- T-01\nstatus: todo\n---\n"
        flow = "---\nid: T-02\nimplements: [R-001, R-002]\nblocked_by: [T-01]\nstatus: todo\n---\n"
        block_meta, block_errors = ct.parse_frontmatter(block)
        flow_meta, _ = ct.parse_frontmatter(flow)
        self.assertEqual(block_errors, [])
        self.assertEqual(block_meta, flow_meta)

    def test_empty_key_with_no_items_is_an_empty_list(self):
        meta, errors = ct.parse_frontmatter("---\nid: T-01\nblocked_by:\nstatus: todo\n---\n")
        self.assertEqual(errors, [])
        self.assertEqual(ct._as_list(meta["blocked_by"]), [])
        self.assertEqual(meta["status"], "todo")

    def test_folded_and_literal_scalars_are_accepted(self):
        text = "---\nname: x\ndescription: >\n  first line\n  second line\ntitle: |\n  literal\n---\n"
        meta, errors = ct.parse_frontmatter(text)
        self.assertEqual(errors, [])
        self.assertEqual(meta["description"], "first line second line")
        self.assertEqual(meta["title"], "literal")

    def test_indented_line_with_no_key_is_still_an_error(self):
        _, errors = ct.parse_frontmatter("---\n  - R-001\nid: T-01\n---\n")
        self.assertTrue(errors)

    def test_unterminated_frontmatter_is_an_error(self):
        _, errors = ct.parse_frontmatter("---\nid: T-01\n")
        self.assertTrue(errors)


class PrdTests(unittest.TestCase):
    def test_extracts_ids_and_priorities_in_both_styles(self):
        self.assertEqual(ct.parse_prd(PRD), REQS)

    def test_missing_priority_is_none(self):
        self.assertEqual(ct.parse_prd("### R-010: Thing\nno priority here\n"), {"R-010": None})

    def test_priority_does_not_leak_into_next_requirement(self):
        self.assertEqual(ct.parse_prd("### R-1: A\nPriority: Must\n### R-2: B\n"), {"R-1": "must", "R-2": None})


class CheckTests(unittest.TestCase):
    def test_valid_trail_has_no_errors_and_orders_by_dependency(self):
        tickets = [
            ticket("T-02", ["R-003"], ["T-01"]),
            ticket("T-01", ["R-001"]),
            ticket("T-03", ["R-002"], ["T-02"]),
        ]
        report = ct.check(REQS, tickets)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.order, ["T-01", "T-02", "T-03"])

    def test_order_is_numeric_not_lexicographic(self):
        tickets = [ticket("T-10", ["R-001"]), ticket("T-2", ["R-003"])]
        self.assertEqual(ct.check(REQS, tickets).order, ["T-2", "T-10"])

    def test_errors(self):
        cases = {
            "dangling blocked_by": (
                [ticket("T-01", ["R-001", "R-003"], ["T-09"])],
                "T-09",
            ),
            "dangling implements": (
                [ticket("T-01", ["R-001", "R-003", "R-099"])],
                "R-099",
            ),
            "duplicate id": (
                [ticket("T-01", ["R-001"]), ticket("T-01", ["R-003"])],
                "duplicate",
            ),
            "cycle": (
                [ticket("T-01", ["R-001"], ["T-02"]), ticket("T-02", ["R-003"], ["T-01"])],
                "cycle",
            ),
            "uncovered must": ([ticket("T-01", ["R-001"])], "R-003"),
            "self dependency": ([ticket("T-01", ["R-001", "R-003"], ["T-01"])], "cycle"),
        }
        for name, (tickets, needle) in cases.items():
            with self.subTest(name):
                errors = ct.check(REQS, tickets).errors
                self.assertTrue(any(needle in e for e in errors), f"{needle!r} not in {errors}")

    def test_uncovered_should_is_not_an_error(self):
        errors = ct.check(REQS, [ticket("T-01", ["R-001", "R-003"])]).errors
        self.assertEqual(errors, [])

    def test_ticket_without_implements_warns(self):
        report = ct.check(REQS, [ticket("T-01", ["R-001", "R-003"]), ticket("T-02")])
        self.assertEqual(report.errors, [])
        self.assertTrue(any("T-02" in w for w in report.warnings))

    def test_legacy_tickets_without_ids_are_not_errors(self):
        report = ct.check(REQS, [{"file": "issue-01.md"}, {"file": "issue-02.md"}])
        self.assertEqual(report.errors, [])
        self.assertEqual(report.order, [])
        self.assertTrue(any("no id" in w for w in report.warnings))

    def test_without_prd_requirement_checks_are_skipped(self):
        report = ct.check(None, [ticket("T-01", ["R-999"])])
        self.assertEqual(report.errors, [])

    def test_trd_missing_a_must_requirement_warns(self):
        report = ct.check(REQS, [ticket("T-01", ["R-001", "R-003"])], trd_text="covers R-001 only")
        self.assertTrue(any("R-003" in w and "TRD" in w for w in report.warnings))
        self.assertFalse(any("R-001" in w for w in report.warnings))


class NextTicketTests(unittest.TestCase):
    def _next(self, tickets):
        return ct.next_ticket(tickets, ct.check(None, tickets).order)

    def test_first_todo_with_all_blockers_done(self):
        tickets = [
            ticket("T-01", status="done"),
            ticket("T-02", blocked_by=["T-01"]),
            ticket("T-03", blocked_by=["T-02"]),
        ]
        self.assertEqual(self._next(tickets), "T-02")

    def test_blocked_tickets_are_skipped(self):
        tickets = [ticket("T-01", status="in-progress"), ticket("T-02", blocked_by=["T-01"])]
        self.assertIsNone(self._next(tickets))

    def test_none_when_everything_done(self):
        self.assertIsNone(self._next([ticket("T-01", status="done")]))


class LoadTicketsTests(unittest.TestCase):
    def test_loads_sorted_and_reports_bad_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            write_ticket(d, "issue-02.md", "---\nid: T-02\nimplements: [R-001]\n---\n")
            write_ticket(d, "issue-01.md", "---\nid: T-01\n---\n")
            write_ticket(d, "issue-03.md", "no frontmatter\n")
            (d / "_metadata.json").write_text("{}", encoding="utf-8")
            tickets, errors = ct.load_tickets(d)
        self.assertEqual([t["file"] for t in tickets], ["issue-01.md", "issue-02.md"])
        self.assertTrue(any("issue-03.md" in e for e in errors))

    def test_missing_directory_is_an_error(self):
        tickets, errors = ct.load_tickets(Path("/nonexistent/tickets"))
        self.assertEqual(tickets, [])
        self.assertTrue(errors)


class CliTests(unittest.TestCase):
    def _trail(self, tmp: str, ticket_two_blocks_on: str = "T-01") -> tuple[Path, Path]:
        d = Path(tmp)
        prd = d / "prd.md"
        prd.write_text(PRD, encoding="utf-8")
        tickets = d / "tickets"
        tickets.mkdir()
        write_ticket(tickets, "issue-01.md", "---\nid: T-01\nimplements: [R-001]\nstatus: done\n---\n")
        write_ticket(
            tickets,
            "issue-02.md",
            f"---\nid: T-02\nimplements: [R-003]\nblocked_by: [{ticket_two_blocks_on}]\nstatus: todo\n---\n",
        )
        return prd, tickets

    def _run(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            rc = ct.main(list(argv))
        return rc, out.getvalue()

    def test_ok_trail_exits_0_and_prints_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            prd, tickets = self._trail(tmp)
            rc, out = self._run("--prd", str(prd), "--tickets", str(tickets))
        self.assertEqual(rc, 0)
        self.assertIn("T-01", out)
        self.assertLess(out.index("T-01"), out.index("T-02"))

    def test_broken_trail_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            prd, tickets = self._trail(tmp, ticket_two_blocks_on="T-99")
            rc, out = self._run("--prd", str(prd), "--tickets", str(tickets))
        self.assertEqual(rc, 1)
        self.assertIn("T-99", out)

    def test_next_prints_only_the_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            prd, tickets = self._trail(tmp)
            rc, out = self._run("--tickets", str(tickets), "--next")
        self.assertEqual((rc, out.strip()), (0, "T-02"))

    def test_json_output_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            prd, tickets = self._trail(tmp)
            rc, out = self._run("--prd", str(prd), "--tickets", str(tickets), "--json")
        data = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(data["order"], ["T-01", "T-02"])
        self.assertEqual(data["next"], "T-02")
        self.assertEqual(data["errors"], [])

    def test_prd_without_requirement_headings_gives_one_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, tickets = self._trail(tmp)
            prd = Path(tmp) / "bad-prd.md"
            prd.write_text("### **R-001**: Login\nPriority: Must\n", encoding="utf-8")
            rc, out = self._run("--prd", str(prd), "--tickets", str(tickets))
        self.assertEqual(rc, 1)
        self.assertIn("no '### R-NNN' requirement headings", out)
        self.assertIn("bad-prd.md", out)
        self.assertNotIn("unknown requirement", out)

    def test_next_explains_when_a_ticket_is_stuck_in_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            tickets = Path(tmp)
            write_ticket(tickets, "issue-01.md", "---\nid: T-01\nstatus: in-progress\n---\n")
            write_ticket(tickets, "issue-02.md", "---\nid: T-02\nblocked_by: [T-01]\nstatus: todo\n---\n")
            rc, out = self._run("--tickets", str(tickets), "--next")
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "none (in-progress: T-01)")

    def test_next_is_plain_none_when_everything_is_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_ticket(Path(tmp), "issue-01.md", "---\nid: T-01\nstatus: done\n---\n")
            rc, out = self._run("--tickets", tmp, "--next")
        self.assertEqual((rc, out.strip()), (0, "none"))

    def test_missing_prd_file_is_an_error_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, tickets = self._trail(tmp)
            rc, out = self._run("--prd", "/nonexistent/prd.md", "--tickets", str(tickets))
        self.assertEqual(rc, 1)
        self.assertIn("prd.md", out)


if __name__ == "__main__":
    unittest.main()
