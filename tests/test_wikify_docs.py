import unittest

from agents.wikify import docs_inventory as di
from tests.test_wikify_state import RepoCase, git


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

    def test_cap_after_filters(self):
        for i in range(501):
            self.write(f"docs/d{i:03d}.md")
        self.write("docs/empty.md", "")
        self.commit_all()
        inv = di.inventory(self.root)
        self.assertEqual(len(inv.docs), 500)
        self.assertEqual(inv.docs, sorted(inv.docs))
        self.assertEqual(
            self.skips(inv), {"docs/d500.md": "over 500 docs", "docs/empty.md": "empty"}
        )

    def test_empty_repo(self):
        inv = di.inventory(self.root)
        self.assertEqual((inv.docs, inv.skipped), ([], []))


if __name__ == "__main__":
    unittest.main()
