"""``vibe wikify init``: scaffold docs/wiki/ without ever overwriting a file."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from agents.wikify import gitview, state
from agents.wikify.state import WIKI_DIR

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "kits" / "wikify" / "templates" / "wikify" / "WIKIFY.md"
)

# SHA-256 of every earlier shipped docs/wiki/WIKIFY.md (oldest last), built from
# `git log --follow -- agents/kits/wikify/templates/wikify/WIKIFY.md`. A repo file with one of
# these hashes is pristine kit-owned text and may be replaced; anything else is user-owned.
# tests/test_wikify_init.py fails when a shipped version is missing here.
KNOWN_PROTOCOL_SHA256 = frozenset({
    "6dfe3d81b4cf0cd0b3a2fa97aa29f1379f0970afd957421b57be6b8b5a17127d",
    "34e6f3dce468c5427a2aace8a209973b73341db7048449b4be1781d5ead6226f",
    "4edf875b0c70a6ed825ffe7000e1de65c2a4491ce16798a8a353eacbd788e14f",
    "304db5df390b457d4a54be5ecd11530d04c6d08ed97649266d01df13063b99cc",
    "13e20ad9dc03dbb3c8409d67b93ef0d74c20fffbe92ce3b4d8c9e537182b1757",
    "ac3bc2e087d5a04b6465894bc32e84da5198c5ed9358357b5274a6a5a5aaa28e",
    "f36a648b160bfd0e0277eb745b20d2eff7ba784f022cbe73052e5f5794e090dd",
    "e95871197264130db50ed1ebf93e0210ed34866a425806ff84700290a1b2aade",
    "fd6c90ab83f1d3c19f3bb7dac121fdba17c0c2e36cb351029c80918c8783fe7d",
    "40357315dc4fa64d09c6ddd6d84d73cb413cdc3666ced78d876a561b7133c74a",
    "c340c9e30566e5ea6e8cd43a7f9d186c1b29cbf92eb9f0c9f78e6579ddeb79fd",
    "a28e4f7a2189a065c2b06504de576382c2c2313f19341985abb86ff3c68fef66",
    "fe0ec6c55e5dfce52b2c0d843822bcfbb4c207055fa53c1b94fa63810d8e5a22",
})


# headings and the map block only: prose here needs citations too
INDEX = "# Wiki index\n\n<!-- wikify:map -->\n<!-- /wikify:map -->\n"
STATE = '{\n  "version": 1,\n  "covered": null\n}\n'
IGNORE = (
    "# Repo paths the wiki must not cite, one glob per line.\n"
    "# Example: a vendored directory such as third_party/\n"
    "# A name without / matches at any depth; a / anchors at the repo root; no ! lines.\n"
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


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cmd_update_protocol(cwd: str | Path | None = None, apply: bool = False) -> int:
    """Replace docs/wiki/WIKIFY.md with the shipped protocol, only when it is a pristine
    earlier shipped version (so nothing user-owned is lost); dry run unless ``apply``."""
    root = gitview.repo_root(cwd or os.getcwd())
    if root is None:
        print("not a git repository")
        return 1
    try:
        state.check_wiki_path(root)
        target = root / WIKI_DIR / "WIKIFY.md"
        if target.is_symlink() or not target.is_file():
            print(f"refused: {WIKI_DIR}WIKIFY.md is missing, a symlink, or not a regular file")
            return 1
        current = target.read_bytes()
        shipped = TEMPLATE.read_bytes()
    except state.UnsafeWikiPath as exc:
        print(f"refused: {exc}")
        return 1
    except OSError as exc:
        print(f"cannot read the protocol: {type(exc).__name__}")
        return 1
    if sha256(current) == sha256(shipped):
        print(f"{WIKI_DIR}WIKIFY.md is up to date")
        return 0
    if sha256(current) not in KNOWN_PROTOCOL_SHA256:
        print(f"{WIKI_DIR}WIKIFY.md locally edited; not overwritten (diff it against the shipped protocol)")
        return 1
    if not apply:
        print(f"would replace {WIKI_DIR}WIKIFY.md with the current protocol (rerun with --apply)")
        return 0
    tmp = target.with_name(f".WIKIFY.md.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(shipped)
        os.replace(tmp, target)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        print(f"cannot write the protocol: {type(exc).__name__}")
        return 1
    print(f"updated {WIKI_DIR}WIKIFY.md; review it with git diff and commit docs-only")
    return 0
