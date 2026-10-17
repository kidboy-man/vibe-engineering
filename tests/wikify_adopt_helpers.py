"""Fixture repos and a tiny report validator for the wikify adopt tests."""

import contextlib
import io
import re

from agents.wikify import init_cmd
from tests.test_wikify_state import RepoCase, git

FIXTURES = {
    "empty-docs": {"src/app.py": "print('x')\n"},
    "flat-docs": {
        "docs/overview.md": "# Overview\n\nWhat it is.\n",
        "docs/runbook.md": "# Runbook\n\nSteps.\n",
        "src/app.py": "print('x')\n",
    },
    "nested-docs": {
        "README.md": "# Project\n",
        "pyproject.toml": '[project]\nreadme = "README.md"\n',
        "docs/trd/payments.md": "# Payments TRD\n\nSee [ADR](../adr/0001.md) and ![d](../img/d.png).\n",
        "docs/trd/auth/tokens.md": "# Tokens\n\nBody without trailing newline",
        "docs/adr/0001.md": "# ADR 1\n\nDecision.\n",
        "docs/img/d.png": "\x89PNG",
        "docs/guide.markdown": "# Guide\n",
        "docs/overview.md": "# Overview\n\nStart at [payments](trd/payments.md) or [site](https://x.io/a.md).\n",
        "docs/secret-notes.md": "# Notes\n\npassword = 'hunter2hunter2'\n",
        "docs/build.md": "# Build output\n",
        "Makefile": "check:\n\tcat docs/build.md\n",
        "src/app.py": "# see docs/adr/0001.md\nprint('x')\n",
    },
}

MAPPING = (
    "docs/trd/** -> specs/trd/ kind=spec\n"
    "docs/adr/** -> decisions/ kind=adr\n"
    "docs/secret-notes.md -> reference/\n"
    "docs/build.md -> reference/\n"
)


class AdoptCase(RepoCase):
    def build(self, name, init=True):
        for rel, content in FIXTURES[name].items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        if init:
            with contextlib.redirect_stdout(io.StringIO()):
                init_cmd.cmd_init(self.root)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "init")

    def write_map(self, text=MAPPING, commit=False):
        (self.root / "docs/wiki/.wikifymap").write_text(text, encoding="utf-8")
        if commit:
            git(self.root, "add", "-A")
            git(self.root, "commit", "-q", "-m", "map")


def validate(instance, schema, path="$"):
    """Stdlib subset of JSON Schema: type, required, enum, pattern, items, minimum, additionalProperties."""
    errors = []
    kind = schema.get("type")
    py = {"object": dict, "array": list, "string": str, "integer": int}.get(kind)
    if py and not isinstance(instance, py):
        return [f"{path}: expected {kind}"]
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum")
    if "pattern" in schema and not re.search(schema["pattern"], instance):
        errors.append(f"{path}: pattern mismatch")
    if "minimum" in schema and instance < schema["minimum"]:
        errors.append(f"{path}: below minimum")
    if kind == "object":
        props = schema.get("properties", {})
        errors += [f"{path}: missing {k}" for k in schema.get("required", []) if k not in instance]
        if schema.get("additionalProperties") is False:
            errors += [f"{path}: unexpected {k}" for k in instance if k not in props]
        for k, sub in props.items():
            if k in instance:
                errors += validate(instance[k], sub, f"{path}.{k}")
    if kind == "array":
        for i, item in enumerate(instance):
            errors += validate(item, schema.get("items", {}), f"{path}[{i}]")
    return errors


def materialize(root, name="nested-docs", init=True):
    """Write FIXTURES[name] into ``root`` as a committed git repo (with docs/wiki when ``init``)."""
    import subprocess
    from pathlib import Path

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    for rel, content in FIXTURES[name].items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    if init:
        with contextlib.redirect_stdout(io.StringIO()):
            init_cmd.cmd_init(root)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    (root / "docs/wiki").mkdir(parents=True, exist_ok=True)
    (root / "docs/wiki/.wikifymap").write_text(MAPPING, encoding="utf-8")  # left uncommitted, as a user would


if __name__ == "__main__":
    import sys

    materialize(sys.argv[1])
