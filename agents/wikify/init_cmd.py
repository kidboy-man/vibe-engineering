"""``vibe wikify init``: scaffold docs/wiki/ without ever overwriting a file."""

from __future__ import annotations

import os
from pathlib import Path

from agents.wikify import gitview, state
from agents.wikify.state import WIKI_DIR

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "kits" / "wikify" / "templates" / "wikify" / "WIKIFY.md"
)

# headings and the map block only: prose here needs citations too
INDEX = "# Wiki index\n\n<!-- wikify:map -->\n<!-- /wikify:map -->\n"
STATE = '{\n  "version": 1,\n  "covered": null\n}\n'
IGNORE = (
    "# Repo paths the wiki must not cite, one glob per line.\n"
    "# Example: a vendored directory such as third_party/\n"
)
DOCS = (
    "# Extra docs to outline in docs/wiki/sources, one glob per line.\n"
    "# Default docs (README, docs/, ...) are always included; .wikifyignore still wins.\n"
    "# Example (uncomment to enable):\n"
    "# docs-extra/\n"
)
ALLOW = (
    "# Reviewed false positives of the secret scan, one per line.\n"
    "# Format: <page path under docs/wiki>|sha256:<first 16 hex of sha256(matched text)>\n"
    "# verify prints the exact line to add (ALLOW-LIST KEY). Never store the secret itself.\n"
    "# Only add entries after a human has reviewed the match.\n"
)


def cmd_init(cwd: str | Path | None = None) -> int:
    root = gitview.repo_root(cwd or os.getcwd())
    if root is None:
        print("not a git repository")
        return 1
    try:
        protocol = TEMPLATE.read_bytes()
    except OSError as exc:
        print(f"cannot read WIKIFY.md template: {type(exc).__name__}")
        return 1
    files = {
        "index.md": INDEX.encode(),
        ".wikify.json": STATE.encode(),
        "WIKIFY.md": protocol,
        ".wikifyignore": IGNORE.encode(),
        ".wikify-allow": ALLOW.encode(),
        ".wikifydocs": DOCS.encode(),
    }
    wiki = root / WIKI_DIR
    ignored = state.ignored_control_files(root)
    if ignored:
        print("refusing to initialize:", *ignored, sep="\n")
        return 1
    try:
        state.check_wiki_path(root)
        wiki.mkdir(parents=True, exist_ok=True)
    except state.UnsafeWikiPath as exc:
        print(f"refusing to initialize: {exc}")
        return 1
    except OSError as exc:
        print(f"cannot create {WIKI_DIR}: {type(exc).__name__}")
        return 1
    for name, data in files.items():
        try:
            with open(wiki / name, "xb") as fh:  # exclusive: never overwrite
                fh.write(data)
        except FileExistsError:
            print(f"already initialized: {WIKI_DIR}{name}")
        else:
            print(f"created {WIKI_DIR}{name}")
    print("Next: run vibe wikify link to add the agent pointer block to AGENTS.md")
    return 0
