"""No new writer touches the files a person owns: ignore/allow lists, human blocks, generated pages."""

import unittest

from agents.wikify import adopt_cmd, commands, hookinstall, imported, imported_refs, init_cmd, reanchor, state
from tests.test_wikify_state import git
from tests.wikify_adopt_helpers import AdoptCase
from tests.wikify_drift_helpers import quiet

OWNED = (
    "docs/wiki/.wikifyignore",
    "docs/wiki/.wikify-allow",
    "docs/wiki/.wikifydocs",
    "docs/wiki/notes.md",
    "docs/wiki/sources/gen.md",
)
NOTES = (
    "Fact (src: src/app.py:1-1 `print`)\n\n<!-- wikify:human -->\nwhy: (src: src/app.py:1-1)\n<!-- /wikify:human -->\n"
)
GENERATED = "<!-- wikify:generated -->\nDoc (src: src/app.py:1-1 `print`)\n"


class ControlFilesTests(AdoptCase):
    def setUp(self):
        super().setUp()
        self.build("flat-docs")
        self.write_map("docs/** -> w/\n", commit=True)
        quiet(adopt_cmd.cmd_adopt, self.root, apply=True)
        git(self.root, "commit", "-q", "-m", "docs(wiki): move docs")
        (self.root / "docs/wiki/.wikifyignore").write_text("# mine\nvendor/\n")
        (self.root / "docs/wiki/.wikify-allow").write_text("# mine\n")
        (self.root / "docs/wiki/notes.md").write_text(NOTES)
        (self.root / "docs/wiki/sources").mkdir(exist_ok=True)
        (self.root / "docs/wiki/sources/gen.md").write_text(GENERATED)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "owned files")
        self.snapshot = self.read_owned()

    def read_owned(self):
        return {rel: (self.root / rel).read_bytes() for rel in OWNED}

    def test_every_writer_leaves_owned_files_byte_identical(self):
        # make each writer have something to do where it can
        (self.root / "src/app.py").write_text("# pad\n" * 3 + "print('x')\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "shift")
        steps = [
            lambda: reanchor.cmd_reanchor(self.root, True),
            lambda: imported_refs.cmd_fix_links(self.root, True),
            lambda: imported.cmd_migrate(self.root, True),
            lambda: hookinstall.cmd_install_hook(self.root, True),
            lambda: init_cmd.cmd_update_protocol(self.root, True),
            lambda: commands.cmd_mark(self.root, True),
        ]
        for step in steps:
            quiet(step)
            self.assertEqual(self.read_owned(), self.snapshot)

    def test_state_file_keeps_user_settings_through_mark(self):
        path = self.root / state.STATE_REL
        data = state._read_raw(self.root)
        data["imported_mode"] = "frozen"
        data["future_key"] = {"keep": True}
        import json
        path.write_text(json.dumps(data))
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "settings")
        quiet(commands.cmd_mark, self.root)
        after = state._read_raw(self.root)
        self.assertEqual(after["imported_mode"], "frozen")
        self.assertEqual(after["future_key"], {"keep": True})


if __name__ == "__main__":
    unittest.main()
