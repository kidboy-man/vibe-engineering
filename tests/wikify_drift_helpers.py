"""Fixture repo for the wikify drift tests: one wiki page citing app/svc.py:10-20 `handle`."""

import contextlib
import hashlib
import io
import os

from agents.wikify import commands, init_cmd
from tests.test_wikify_state import RepoCase, git

SVC = "app/svc.py"
PAGE = "docs/wiki/svc.md"
CITE = "(src: app/svc.py:10-20 `handle`)"


def svc_source(top=0, tag=""):
    """app/svc.py with `handle` at lines 10-20 (shifted down by `top` extra lines)."""
    lines = [f"# top {n}" for n in range(1, 10)]
    lines = ["# shift"] * top + lines
    lines += ["def handle(x):"] + [f"    x += {n}{tag}" for n in range(1, 10)] + ["    return x"]
    lines += [f"# tail {n}" for n in range(1, 11)]
    return "\n".join(lines) + "\n"


def quiet(fn, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*args, **kwargs)
    return rc, buf.getvalue()


class DriftCase(RepoCase):
    """Repo with a wiki that verifies and is marked; helpers to drift the code."""

    def setUp(self):
        super().setUp()
        self.commit(SVC, svc_source())
        quiet(init_cmd.cmd_init, cwd=self.root)
        # legacy index without a map: these tests are about citations, not the map
        (self.root / "docs/wiki/index.md").write_text("# Wiki index\n")
        self.page("Handle adds numbers " + CITE + "\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "wiki")
        rc, text = quiet(commands.cmd_mark, self.root)
        self.assertEqual(rc, 0, text)
        git(self.root, "add", "--", "docs/wiki")
        git(self.root, "commit", "-q", "-m", "docs(wiki): mark")

    def page(self, text, rel=PAGE):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def write_code(self, content, rel=SVC, msg="code"):
        self.commit(rel, content, msg)

    def insert_lines_above(self, count):
        self.write_code(svc_source(top=count), msg=f"shift {count}")

    def tree_hash(self):
        """Hash of every file under the work tree plus `git status`, to prove read-only."""
        digest = hashlib.sha256()
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if d != ".git")
            for name in sorted(filenames):
                path = os.path.join(dirpath, name)
                digest.update(os.path.relpath(path, self.root).encode())
                with open(path, "rb") as handle:
                    digest.update(handle.read())
        digest.update(git(self.root, "status", "--porcelain").encode())
        return digest.hexdigest()
