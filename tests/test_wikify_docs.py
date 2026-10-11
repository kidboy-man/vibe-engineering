import os
import time
import unittest
from unittest import mock

from agents.wikify import citations, commands, gitview, plan

from agents.wikify import docs_inventory as di
from tests.test_wikify_state import RepoCase, git


HAS_FIFO = hasattr(os, "mkfifo")
HAS_SYMLINK = hasattr(os, "symlink")


class InventoryTests(RepoCase):
    def write(self, rel, content="# T\n\nbody\n"):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content)

    def commit_all(self):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "c")

    def skips(self, inv):
        return {s.path: s.reason for s in inv.skipped}

    def base(self):
        for rel in (
            "README.md", "docs/a.md", "docs/sub/b.markdown", "pkg/README.md",
            "pkg/CHANGELOG.md", "agents/kits/x/templates/CLAUDE.md",
            "agents/kits/x/skills/s/SKILL.md", "agents/kits/x/rules/r.md",
            "AGENTS.md", "docs/wiki/index.md", "src/notes.md", ".env.md",
        ):
            self.write(rel)

    def test_default_rules_and_silent_exclusions(self):
        self.base()
        self.write("docs/my notes.md")
        self.write("docs/empty.md", "")
        self.write("docs/big.md", "a\n" * ((1 << 19) + 1))
        self.write("docs/latin.md", b"caf\xe9\n")
        self.write("docs/readme.txt")
        self.commit_all()
        inv = di.inventory(self.root)
        self.assertEqual(
            inv.docs,
            ["README.md", "docs/a.md", "docs/sub/b.markdown", "pkg/CHANGELOG.md", "pkg/README.md"],
        )
        self.assertEqual(
            self.skips(inv),
            {
                "docs/big.md": "larger than 1 MiB",
                "docs/empty.md": "empty",
                "docs/latin.md": "not valid UTF-8",
                "docs/my notes.md": "path not citable",
            },
        )
        self.assertEqual([s.path for s in inv.skipped], sorted(self.skips(inv)))

    def test_upper_case_suffix(self):
        self.write("README.MD")
        self.commit_all()
        self.assertEqual(di.inventory(self.root).docs, ["README.MD"])

    def test_wikifydocs_include_and_ignore(self):
        self.base()
        self.write(di.INCLUDES_REL, "# c\n\nagents/kits/x/rules/\ndocs/a.md\n")
        self.write("docs/wiki/.wikifyignore", "docs/a.md\n")
        self.commit_all()
        self.assertEqual(
            di.load_includes(self.root), ["agents/kits/x/rules/", "docs/a.md"]
        )
        inv = di.inventory(self.root)
        self.assertIn("agents/kits/x/rules/r.md", inv.docs)
        self.assertNotIn("docs/a.md", inv.docs)
        # include never rescues hard exclusions
        self.write(di.INCLUDES_REL, "agents/\n")
        self.commit_all()
        docs = di.inventory(self.root).docs
        self.assertNotIn("agents/kits/x/templates/CLAUDE.md", docs)
        self.assertNotIn("agents/kits/x/skills/s/SKILL.md", docs)

    def test_missing_includes(self):
        self.assertEqual(di.load_includes(self.root), [])

    def test_reads_head_not_working_tree(self):
        self.write("README.md")
        self.commit_all()
        self.write("README.md", "")
        self.write("docs/new.md")
        self.assertEqual(di.inventory(self.root).docs, ["README.md"])

    @unittest.skipUnless(HAS_SYMLINK, "needs symlinks")
    def test_symlink_and_gitlink_excluded(self):
        self.write("README.md")
        os.symlink("../README.md", self.root / "docs-link.md")
        (self.root / "docs").mkdir()
        os.symlink("../README.md", self.root / "docs/README.md")
        os.symlink("/etc/hostname", self.root / "docs/host.md")
        self.commit_all()
        git(self.root, "update-index", "--add", "--cacheinfo",
            "160000," + "a" * 40 + ",docs/sm.md")
        git(self.root, "commit", "-q", "-m", "gitlink")
        inv = di.inventory(self.root)
        self.assertEqual(inv.docs, ["README.md"])
        self.assertEqual(inv.skipped, [])

    def test_git_mode_failure_fails_closed(self):
        self.write("README.md")
        self.commit_all()
        with mock.patch.object(gitview, "regular_tracked", return_value=None):
            inv = di.inventory(self.root)
        self.assertEqual(inv.docs, [])
        self.assertEqual([s.reason for s in inv.skipped], ["could not read file modes"])

    def test_instruction_names_casefolded(self):
        for name in ("docs/agents.md", "docs/Claude.md", "docs/skill.md", "docs/GEMINI.MD"):
            self.write(name)
        self.write("docs/ok.md")
        self.commit_all()
        self.assertEqual(di.inventory(self.root).docs, ["docs/ok.md"])

    def test_staged_uncommitted_not_eligible(self):
        self.write("README.md")
        self.commit_all()
        self.write("docs/new.md")
        git(self.root, "add", "docs/new.md")
        inv = di.inventory(self.root)
        self.assertEqual((inv.docs, inv.skipped), (["README.md"], []))

    @unittest.skipUnless(HAS_SYMLINK, "needs symlinks")
    def test_staged_regular_but_symlink_at_head(self):
        self.write("README.md")
        os.symlink("README.md", self.root / "docs.md")
        self.commit_all()
        (self.root / "docs.md").unlink()
        self.write("docs.md", "# real\n")
        git(self.root, "add", "docs.md")
        self.assertEqual(di.inventory(self.root).docs, ["README.md"])

    def _reject(self, rel, kind):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == "oversized":
            path.write_bytes(b"#" * (64 * 1024 + 1))
        elif kind == "binary":
            path.write_bytes(b"\xff\xfe\n")
        elif kind == "symlink":
            os.symlink(self.root / "README.md", path)
        elif kind == "fifo":
            os.mkfifo(path)

    def _kinds(self):
        kinds = ["oversized", "binary"]
        if HAS_SYMLINK:
            kinds.append("symlink")
        if HAS_FIFO:
            kinds.append("fifo")
        return kinds

    def test_rejected_ignore_file_surfaces_everywhere(self):
        self.write("README.md")
        self.write("docs/secret.md")
        self.commit_all()
        for kind in self._kinds():
            with self.subTest(kind=kind):
                path = self.root / citations.IGNORE_REL
                if path.is_symlink() or path.exists():
                    path.unlink()
                self._reject(citations.IGNORE_REL, kind)
                self.assertEqual(citations.ignore_status(self.root), "rejected")
                rc, lines = commands.run_verify(self.root)
                self.assertEqual(rc, 1)
                self.assertIn(
                    "docs/wiki/.wikifyignore: rejected (symlink, not a regular file, "
                    "not valid UTF-8, or over 64 KiB); ignore rules were NOT applied",
                    lines,
                )
                inv = di.inventory(self.root)
                self.assertEqual(inv.docs, [])
                self.assertEqual(
                    inv.skipped,
                    [di.Skip(".wikifyignore", "ignore file rejected; ignore rules not applied")],
                )
                self.assertIn("rejected", plan.build_plan(self.root)["error"])

    def test_ignore_file_at_cap_and_absent_are_clean(self):
        self.write("README.md")
        self.write("docs/secret.md")
        self.commit_all()
        self.assertEqual(citations.ignore_status(self.root), "absent")
        rc, lines = commands.run_verify(self.root)
        self.assertEqual(rc, 0)
        self.assertIsNone(plan.build_plan(self.root)["error"])
        body = "docs/secret.md\n" + "#" * (64 * 1024 - len("docs/secret.md\n"))
        self.write(citations.IGNORE_REL, body)
        self.assertEqual(len(body.encode()), 64 * 1024)
        self.assertEqual(citations.ignore_status(self.root), "ok")
        self.assertEqual(di.inventory(self.root).docs, ["README.md"])
        self.assertEqual(commands.run_verify(self.root)[0], 0)

    def test_rejected_includes_file_is_skipped_entry_only(self):
        self.write("README.md")
        self.commit_all()
        for kind in self._kinds():
            with self.subTest(kind=kind):
                path = self.root / di.INCLUDES_REL
                if path.is_symlink() or path.exists():
                    path.unlink()
                self._reject(di.INCLUDES_REL, kind)
                self.assertEqual(di.includes_status(self.root), "rejected")
                inv = di.inventory(self.root)
                self.assertEqual(inv.docs, ["README.md"])
                self.assertEqual(
                    inv.skipped, [di.Skip(di.INCLUDES_REL, "includes file rejected")]
                )

    @unittest.skipUnless(HAS_FIFO and HAS_SYMLINK, "needs mkfifo and symlinks")
    def test_control_files_hardened(self):
        wiki = self.root / "docs/wiki"
        wiki.mkdir(parents=True)
        outside = self.root / "outside.txt"
        outside.write_text("README.md\n")
        cases = {
            "fifo": lambda p: os.mkfifo(p),
            "symlink": lambda p: os.symlink(outside, p),
            "oversized": lambda p: p.write_text("x/\n" * (65 * 1024 // 3 + 1)),
        }
        loaders = (
            (di.INCLUDES_REL, di.load_includes),
            (citations.IGNORE_REL, citations.load_ignore),
        )
        for rel, load in loaders:
            for name, make in cases.items():
                path = self.root / rel
                if path.exists() or path.is_symlink():
                    path.unlink()
                make(path)
                with self.subTest(rel=rel, case=name):
                    self.assertEqual(load(self.root), [])
            path.unlink()
            path.write_text("# c\na/\n")
            self.assertEqual(load(self.root), ["a/"])

    def test_cap_stops_reading(self):
        for i in range(3000):
            self.write(f"docs/d{i:04d}.md")
        self.commit_all()
        real = gitview.show_head
        with mock.patch.object(gitview, "show_head", side_effect=real) as spy:
            start = time.monotonic()
            inv = di.inventory(self.root)
            elapsed = time.monotonic() - start
        self.assertEqual(spy.call_count, 500)
        self.assertEqual(len(inv.docs), 500)
        self.assertEqual(len(inv.skipped), 2500)
        self.assertLess(elapsed, 5)

    def test_cap_after_filters(self):
        for i in range(501):
            self.write(f"docs/d{i:03d}.md")
        self.write("docs/empty.md", "")
        self.write("docs/a b.md")
        self.commit_all()
        inv = di.inventory(self.root)
        self.assertEqual(len(inv.docs), 500)
        self.assertEqual(inv.docs, sorted(inv.docs))
        self.assertEqual(
            self.skips(inv),
            {
                "docs/a b.md": "path not citable",
                "docs/d500.md": "over 500 docs",
                "docs/empty.md": "over 500 docs",
            },
        )

    def test_empty_repo(self):
        inv = di.inventory(self.root)
        self.assertEqual((inv.docs, inv.skipped), ([], []))


if __name__ == "__main__":
    unittest.main()
