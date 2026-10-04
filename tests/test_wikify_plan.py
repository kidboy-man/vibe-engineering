import tempfile
import subprocess
import unittest
from unittest import mock
from pathlib import Path

from agents.wikify import gitview, plan, state
from tests.test_wikify_state import STATE, RepoCase, git

PAGE = "docs/wiki/a.md"


def cite(path):
    return f"Does a thing. (src: {path}:1)\n"


class PlanTests(RepoCase):
    def test_full_on_no_state(self):
        self.commit("src/pkg/a.py", "class K:\n    pass\n")
        self.commit("README.md")
        p = plan.build_plan(self.root)
        self.assertEqual(p["mode"], "full")
        self.assertIsNone(p["base"])
        self.assertEqual(p["head"], gitview.head(self.root))
        self.assertEqual(p["changed"], ["README.md", "src/pkg/a.py"])
        self.assertEqual(p["contexts"], ["src/pkg"])
        self.assertEqual(p["symbols"], {"src/pkg/a.py": ["K"]})

    def test_state_never_committed_is_full(self):
        self.commit("src/a.py")
        state.save(self.root, gitview.head(self.root))
        self.assertEqual(plan.build_plan(self.root)["mode"], "full")

    def test_full_flag_overrides_state(self):
        self.commit("src/a.py")
        self.mark()
        p = plan.build_plan(self.root, full=True)
        self.assertEqual(p["mode"], "full")
        self.assertEqual(p["changed"], ["src/a.py"])

    def test_incremental_maps_changed_file_to_page(self):
        self.commit("src/a.py")
        self.commit("src/b.py")
        self.commit(PAGE, cite("src/a.py"))
        self.commit("docs/wiki/b.md", cite("src/b.py"))
        self.mark()
        self.commit("src/a.py", "x = 1\n")
        p = plan.build_plan(self.root)
        self.assertEqual(p["mode"], "incremental")
        self.assertEqual(p["base"], gitview.last_commit_touching(self.root, STATE))
        self.assertEqual(p["changed"], ["src/a.py"])
        self.assertEqual(p["refresh_pages"], ["a.md"])
        self.assertEqual(p["uncovered"], [])

    def test_added_file_is_uncovered(self):
        self.commit("src/a.py")
        self.commit(PAGE, cite("src/a.py"))
        self.mark()
        self.commit("src/new.py", "def f():\n    pass\n")
        p = plan.build_plan(self.root)
        self.assertEqual(p["uncovered"], ["src/new.py"])
        self.assertEqual(p["refresh_pages"], [])
        self.assertEqual(p["symbols"], {"src/new.py": ["f"]})

    def test_deleted_cited_file_flags_page_untouched(self):
        self.commit("src/a.py")
        self.commit(PAGE, cite("src/a.py"))
        self.mark()
        before = (self.root / PAGE).read_text()
        git(self.root, "rm", "-q", "src/a.py")
        git(self.root, "commit", "-q", "-m", "rm")
        p = plan.build_plan(self.root)
        self.assertEqual(p["stale_deleted"], [{"page": "a.md", "missing": ["src/a.py"]}])
        self.assertEqual((self.root / PAGE).read_text(), before)

    def test_incremental_after_amend(self):
        self.commit("src/a.py")
        self.mark()
        self.commit("src/b.py")
        git(self.root, "commit", "-q", "--amend", "--no-edit", "--reset-author")
        p = plan.build_plan(self.root)
        self.assertEqual(p["mode"], "incremental")
        self.assertEqual(p["changed"], ["src/b.py"])

    def test_ignored_and_secret_omitted_everywhere(self):
        self.commit("src/a.py")
        self.commit("src/gen/g.py", "def leak():\n    pass\n")
        self.commit(".env", "K=1\n")
        self.commit("docs/wiki/.wikifyignore", "src/gen/\n")
        for full in (True, False):
            if not full:
                self.mark()
                for rel in (".env", "src/gen/h.py", "src/ok.py"):
                    self.commit(rel, "def h():\n    pass\n")
            p = plan.build_plan(self.root, full=full)
            blob = plan.render(p) + repr(p)
            for hidden in (".env", "src/gen", "leak"):
                self.assertNotIn(hidden, blob, (full, hidden))
            self.assertIn("src/a.py" if full else "src/ok.py", p["changed"])

    def test_syntax_error_py_does_not_crash(self):
        self.commit("src/bad.py", "def (:\n")
        self.commit("src/ok.py", "def f():\n    pass\n")
        p = plan.build_plan(self.root)
        self.assertIn("src/bad.py", p["changed"])
        self.assertEqual(p["symbols"], {"src/ok.py": ["f"]})

    def test_enum_members(self):
        self.commit("src/e.py", "import enum\nclass C(enum.Enum):\n    A = 1\n    B = 2\n")
        self.assertEqual(plan.build_plan(self.root)["symbols"]["src/e.py"], ["C", "C.A", "C.B"])

    def test_no_commits(self):
        p = plan.build_plan(self.root)
        self.assertEqual(p["mode"], "full")
        self.assertIsNone(p["head"])
        for key in ("changed", "refresh_pages", "uncovered", "stale_deleted", "contexts"):
            self.assertEqual(p[key], [])
        self.assertEqual(p["symbols"], {})
        self.assertIn("full", plan.render(p))

    def test_full_refreshes_existing_pages_and_wiki_not_changed(self):
        self.commit("src/a.py")
        self.commit(PAGE, cite("src/a.py"))
        p = plan.build_plan(self.root)
        self.assertEqual(p["refresh_pages"], ["a.md"])
        self.assertEqual(p["changed"], ["src/a.py"])

    def test_render_lists_everything(self):
        self.commit("src/a.py")
        self.commit(PAGE, cite("src/a.py"))
        self.mark()
        git(self.root, "rm", "-q", "src/a.py")
        git(self.root, "commit", "-q", "-m", "rm")
        out = plan.render(plan.build_plan(self.root))
        for needle in ("incremental", "a.md", "src/a.py", "stale"):
            self.assertIn(needle, out)

    def test_annotated_members(self):
        self.commit("src/d.py", "class D:\n    x: int = 1\n    y: str\n")
        self.assertEqual(plan.build_plan(self.root)["symbols"]["src/d.py"], ["D", "D.x", "D.y"])

    def _failing(self, sub):
        real = gitview.run_git

        def fake(root, *args):
            if args and args[0] == sub:
                return subprocess.CompletedProcess(["git"], 124, "", "timeout")
            return real(root, *args)

        return mock.patch.object(gitview, "run_git", fake)

    def test_ls_files_failure_sets_error_rendered_first(self):
        self.commit("src/a.py")
        with self._failing("ls-files"):
            p = plan.build_plan(self.root)
        self.assertIn("ls-files", p["error"])
        self.assertEqual(p["changed"], [])
        self.assertTrue(plan.render(p).startswith("ERROR: "))

    def test_diff_failure_with_base_sets_error_and_falls_back_full(self):
        self.commit("src/a.py")
        self.mark()
        with self._failing("diff"):
            p = plan.build_plan(self.root)
        self.assertIn("diff", p["error"])
        self.assertEqual(p["mode"], "full")
        self.assertEqual(p["changed"], ["src/a.py"])

    def test_error_none_when_healthy_or_empty_tree(self):
        self.commit("src/a.py")
        self.assertIsNone(plan.build_plan(self.root)["error"])
        git(self.root, "rm", "-q", "src/a.py")
        git(self.root, "commit", "-q", "-m", "empty")
        p = plan.build_plan(self.root)
        self.assertIsNone(p["error"])
        self.assertEqual(p["changed"], [])
        self.assertFalse(plan.render(p).startswith("ERROR"))


if __name__ == "__main__":
    unittest.main()
