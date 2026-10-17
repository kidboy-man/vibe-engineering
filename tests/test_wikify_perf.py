"""Permanent guard: 1 MiB hostile inputs must stay linear through public entry points."""

import importlib.util
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from agents.wikify import agentmap, citations, docs_inventory, gitview, pointer, scan, state

MIB = 1 << 20
# One end-to-end budget per hostile-input class, >= 10x the slowest measured
# case on a dev box (scan 0.19 s, other text 0.73 s, matcher matrix 1.8 s). These
# also catch a large constant-factor regression (old JWT scan: ~7 s here), which
# the load-independent doubling-ratio checks in the other modules cannot see.
SCAN_LIMIT = 3.0
TEXT_LIMIT = 10.0
MATCHER_LIMIT = 20.0
HOOK = (
    Path(__file__).resolve().parent.parent
    / "agents/kits/wikify/templates/wikify/hooks/vibe-wikify/wikify_guard.py"
)


def load_guard():
    spec = importlib.util.spec_from_file_location("wikify_guard_perf", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._find_vibe = lambda: None  # the machine's own `vibe` must not change the verdict
    return module


def fill(unit: str, size: int = MIB) -> str:
    return unit * (size // len(unit) + 1)


class Timed(unittest.TestCase):
    LIMIT = TEXT_LIMIT

    def timed(self, fn, *args, limit=None):
        limit = self.LIMIT if limit is None else limit
        start = time.perf_counter()
        out = fn(*args)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, limit, f"{elapsed:.2f}s")
        return out


class ScanPerfTests(Timed):
    LIMIT = SCAN_LIMIT

    CASES = {
        "email": "a@b.",
        "email-lines": "a@b.c\n",
        "jwt": "_eyJa.b.",
        "bearer": "Bearer " + "a" * 19,
        "aws": "AKIA" + "A" * 15,
        "assign": 'token="aaaaaaa',
    }

    def test_each_rule_worst_case(self):
        for name, unit in self.CASES.items():
            with self.subTest(rule=name):
                self.timed(scan.scan_text, fill(unit))


class ScanEquivalenceTests(unittest.TestCase):
    @staticmethod
    def reference(text):
        hits = []
        for rule, pattern in scan.RULES:
            for m in pattern.finditer(text):
                hits.append((text.count("\n", 0, m.start()) + 1, rule, m.group(0)))
        return sorted(hits, key=lambda h: (h[0], h[1]))

    def test_matches_straightforward_implementation(self):
        corpus = (
            "intro\n" + "a@b.co and x\n" * 3 + "Bearer " + "q" * 24 + "\n\n"
            "AKIA" + "B" * 16 + "\nline\n" + 'api_key = "' + "x" * 12 + '"\n'
            "password: abcdef1234567\n" + "-----BEGIN RSA PRIVATE KEY-----\n" + "tail"
        )
        for text in ("", "no hits\n", corpus, corpus * 3, "a@b.c\n" * 50):
            with self.subTest(n=len(text)):
                self.assertEqual(scan._scan(text), self.reference(text))
        self.assertTrue(self.reference(corpus))


class CitationPerfTests(Timed):
    def test_parse_hostile(self):
        for unit in ("(src: a:1)\n", "[", "[[", "[a](", "[a](b", "](a.md"):
            with self.subTest(unit=unit):
                self.timed(citations.parse, fill(unit))

    def test_citation_lines_unchanged(self):
        text = "".join(f"p{i} (src: a.py:{i + 1})\n\n" for i in range(40)) + "end (src: b.py:2-3 `x`)"
        cites, _ = citations.parse(text)
        want = [m.start() for m in citations.CITE.finditer(text)]
        self.assertEqual([c.line for c in cites], [text.count("\n", 0, s) + 1 for s in want])
        self.assertEqual(len(cites), 41)

    def test_verify_page_hostile(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "a.py").write_text("x\n", encoding="utf-8")
            subprocess.run(["git", "add", "a.py"], cwd=root, check=True)
            subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                 "commit", "-q", "-m", "x"],
                cwd=root, check=True,
            )
            ignore = [f"g{i}*/z" for i in range(8000)]
            cases = {
                "many-cites": fill("(src: a.py:1)\n"),
                "long-path": "(src: " + "a" * MIB + ":1)\n",
            }
            for name, text in cases.items():
                with self.subTest(case=name):
                    errs = self.timed(citations.verify_page, root, "p.md", text, ignore)
                    self.assertTrue(errs)
            long_path = citations.verify_page(root, "p.md", "(src: " + "a" * 5000 + ":1)\n", [])
            self.assertIn("path too long", long_path[0])
            many = citations.verify_page(root, "p.md", "(src: a.py:1)\n" * (citations.MAX_CITATIONS + 1), [])
            self.assertEqual([e for e in many if "too many citations" in e], many)
            self.assertEqual(len(many), 1)


class IgnoreMatcherPerfTests(Timed):
    LIMIT = MATCHER_LIMIT

    def test_many_patterns_times_many_paths(self):
        globs = [f"*/*/a*b?c/**/f{i}.py" for i in range(citations.MAX_IGNORE_PATTERNS)]
        paths = [f"d{i % 40}/x/{'s/' * (i % 12)}file{i}.py" for i in range(3000)]
        self.timed(lambda: [citations.is_ignored(p, globs) for p in paths])

    def test_double_star_runs_do_not_backtrack(self):
        glob = "/".join(["**"] * 100) + "/zzz"
        path = "/".join(["a"] * 2000) + "/q"
        self.assertFalse(self.timed(citations.is_ignored, path, [glob]))
        stars = "*a" * 8 + "*b"
        self.assertFalse(self.timed(citations.is_ignored, "a" * 4000, [stars]))

    def test_caps_reject_before_matching(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs/wiki").mkdir(parents=True)
            ign = root / "docs/wiki/.wikifyignore"
            for body in ("a\n" * 20000, "*" * 300 + "\n", "*a" * 9 + "\n"):
                ign.write_text(body, encoding="utf-8")
                self.assertEqual(self.timed(citations.ignore_status, root), "rejected")
            ign.write_text("vendor/\n", encoding="utf-8")
            self.assertEqual(citations.ignore_status(root), "ok")


class MapAndDocsPerfTests(Timed):
    def test_agentmap(self):
        for unit in ("](", "](a", "](a.md", "[x](a.md) ", "<!-- wikify:map -->\n"):
            with self.subTest(unit=unit):
                text = fill(unit)
                self.timed(agentmap.page_links, "p.md", text)
                self.timed(agentmap.parse_map, text)

    def test_docs_outline_and_pointer_fences(self):
        for unit in ("# h\n", "```\n", "~~~\n", "#", "  \t"):
            with self.subTest(unit=unit):
                text = fill(unit)
                self.timed(docs_inventory.outline, text)
                self.timed(pointer._markers, text.splitlines(keepends=True))


class HookPerfTests(Timed):
    @classmethod
    def setUpClass(cls):
        cls.guard = load_guard()

    def decide(self, command, cwd="/"):
        payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}
        return self.timed(self.guard.decide, payload)

    def test_hostile_commands_allowed_fast(self):
        for command in ("a" * MIB, fill(";&|<>()"), "'" + fill("<<a "), fill("git push; ")):
            with self.subTest(head=command[:8]):
                self.assertIsNone(self.decide(command))

    def test_heredoc_word_linear_below_cap(self):
        line = "'" + "<<a " * 15000
        self.timed(self.guard._heredoc_word, line)

    def test_large_legitimate_command_still_blocked_when_stale(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
            subprocess.run([*git, "init", "-q"], cwd=root, check=True)
            (root / "src").mkdir()
            (root / "src/a.py").write_text("x\n", encoding="utf-8")
            subprocess.run([*git, "add", "src/a.py"], cwd=root, check=True)
            subprocess.run([*git, "commit", "-q", "-m", "c"], cwd=root, check=True)
            state.save(root, gitview.head(root))  # never committed -> stale
            body = "x" * (60 * 1024)
            blocked = self.decide(f'git commit -m "{body}" && git push', str(root))
            self.assertEqual(blocked, self.guard.MESSAGE)
            over = f'git commit -m "{"x" * (70 * 1024)}" && git push'
            self.assertIsNone(self.decide(over, str(root)))


class DriftPerfTests(unittest.TestCase):
    """Call counts and doubling ratios, never wall-clock limits (constitution Principle IV)."""

    def check_git_calls(self, pages):
        from unittest import mock

        from agents.wikify import check_cmd
        from tests.wikify_drift_helpers import CITE, DriftCase, quiet
        from tests.test_wikify_state import git

        class Case(DriftCase):
            def runTest(self):
                pass

        case = Case()
        case.setUp()
        try:
            for n in range(pages):
                case.page(f"Handle {CITE}\n\nTail (src: app/svc.py:21-30)\n", rel=f"docs/wiki/p{n}.md")
            git(case.root, "add", "-A")
            git(case.root, "commit", "-q", "-m", "pages")
            real = gitview.subprocess.run
            calls = []

            def spy(argv, *args, **kwargs):
                calls.append(tuple(argv[3:]))  # drop: git -c core.quotePath=false
                return real(argv, *args, **kwargs)

            with mock.patch.object(gitview.subprocess, "run", side_effect=spy):
                quiet(check_cmd.cmd_check, case.root, True)
            return calls
        finally:
            case.doCleanups()

    def test_check_git_calls_do_not_grow_with_the_number_of_pages(self):
        few = self.check_git_calls(5)
        many = self.check_git_calls(40)
        shows = lambda calls: [c for c in calls if c[0] == "show" and "app/svc.py" in c[-1]]
        logs = lambda calls: [c for c in calls if c[0] == "log"]
        self.assertEqual(len(shows(few)), 1)
        self.assertEqual(len(shows(many)), 1)  # one read per distinct cited file
        self.assertEqual(len(logs(few)), len(logs(many)))
        self.assertLessEqual(len(logs(many)), 2)
        page_blob = lambda c: c[-1].startswith("HEAD:docs/wiki/") and c[-1].endswith(".md")
        other = lambda calls: [c for c in calls if not page_blob(c)]
        self.assertEqual(len(other(few)), len(other(many)))  # only the page blobs scale
        self.assertEqual(len(many) - len(other(many)), 42)  # 40 pages + index.md + svc.md, one read each

    def test_window_search_is_linear_in_file_length(self):
        from agents.wikify import drift
        from tests.wikify_perf_helpers import assert_scales_linearly

        def make(n):
            lines = [f"line {i}" for i in range(n)]
            return lines, 50, drift.range_hash(lines, 10, 59)

        assert_scales_linearly(self, make, drift.find_windows, 4000, label="find_windows")

    def test_oversized_relocation_gives_up_instead_of_running_away(self):
        from agents.wikify import drift

        lines = [f"line {i}" for i in range(6000)]
        self.assertIsNone(drift.find_windows(lines, 3000, "0" * 12))


if __name__ == "__main__":
    unittest.main()
