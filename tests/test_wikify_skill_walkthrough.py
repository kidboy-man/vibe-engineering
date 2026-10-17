"""The documented sync loop uses real commands and ends with a passing check."""

import re
import unittest
from pathlib import Path

from agents import cli
from agents.wikify import check_cmd, commands, reanchor
from tests.test_wikify_state import git
from tests.wikify_drift_helpers import DriftCase, quiet

REPO = Path(__file__).resolve().parent.parent
DOC = REPO / "docs/wikify-sync-walkthrough.md"
SKILL = REPO / "agents/kits/wikify/templates/wikify/skills/wikify-sync/SKILL.md"
BILLING = "app/billing.py"
BILLING_PAGE = "docs/wiki/billing.md"


def billing_source(tag=""):
    return "\n".join(
        ["# billing"] * 4 + ["def charge(total):"] + [f"    total += {n}{tag}" for n in range(1, 7)]
        + ["    return total"] + [f"# end {n}" for n in range(1, 6)]
    ) + "\n"


class CommandNameTests(unittest.TestCase):
    def commands_in(self, text):
        return re.findall(r"^(?:\s*)(vibe wikify [^\n`]+)$", text, re.M)

    def test_every_documented_command_parses(self):
        parser = cli.build_parser(cli.KITS)
        found = []
        for source in (DOC.read_text(encoding="utf-8"), SKILL.read_text(encoding="utf-8")):
            found += self.commands_in(source)
            found += re.findall(r"`(vibe wikify [^`]+)`", source)
        self.assertGreater(len(found), 8)
        for line in found:
            args = line.split()[1:]
            with self.subTest(command=line):
                parser.parse_args(args)


class SyncLoopTests(DriftCase):
    def setUp(self):
        super().setUp()
        self.commit(BILLING, billing_source())
        self.page("Handle adds numbers (src: app/svc.py:10-20 `handle`)\n")
        self.page("Charge adds fees (src: app/billing.py:5-12 `charge`)\n", rel=BILLING_PAGE)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "billing page")
        self.assertEqual(quiet(commands.cmd_mark, self.root)[0], 0)
        git(self.root, "add", "--", "docs/wiki")
        git(self.root, "commit", "-q", "-m", "docs(wiki): mark")
        # index.md has no map block: both pages are reachable only as legacy pages

    def test_sync_edit_verify_mark_commit_ends_with_a_passing_check(self):
        self.insert_lines_above(15)
        self.write_code(billing_source(tag="!"), rel=BILLING, msg="edit charge")
        rc, text = quiet(check_cmd.cmd_sync, self.root)
        self.assertEqual(rc, 1)
        self.assertIn("moved", text)
        self.assertIn("changed", text)
        # step 2: heal the mechanical drift; the edited body is refused, which is the cue for step 3
        rc, dry = quiet(reanchor.cmd_reanchor, self.root, False)
        self.assertEqual(rc, 1)
        self.assertIn("refused: billing.md", dry)
        rc, out = quiet(reanchor.cmd_reanchor, self.root, True)
        self.assertEqual(rc, 1)
        self.assertIn("re-anchored 1 citation", out)
        # step 3: the agent reads the code and updates the paragraph
        self.page("Charge adds fees and a marker (src: app/billing.py:5-12 `charge`)\n", rel=BILLING_PAGE)
        # step 4: verify, mark
        self.assertEqual(quiet(commands.cmd_verify, self.root)[0], 0)
        rc, out = quiet(commands.cmd_mark, self.root)
        self.assertEqual(rc, 0, out)
        # step 5: docs-only commit after confirmation
        git(self.root, "add", "--", "docs/wiki")
        git(self.root, "commit", "-q", "-m", "docs(wiki): sync")
        # step 6
        self.assertEqual(quiet(check_cmd.cmd_check, self.root)[0], 0)
        self.assertEqual(quiet(check_cmd.cmd_check, self.root, True)[0], 0)
        self.assertEqual(quiet(check_cmd.cmd_sync, self.root)[1].splitlines()[0], "work list (0):")


if __name__ == "__main__":
    unittest.main()
