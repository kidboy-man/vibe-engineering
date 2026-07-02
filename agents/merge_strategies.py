"""Merge strategies for kit installers.

Each strategy is a pure function that takes template/current content and
returns merged content plus metadata.  They know nothing about disk paths
or I/O — that stays in the installers.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Collection
from typing import Any


def json_defaults_strategy(
    fragment: dict,
    current: dict,
    secret_keys: set[str],
) -> tuple[dict, bool]:
    """Merge JSON fragment defaults into current settings.

    - Never overwrite existing keys.
    - Skip the ``"env"`` key explicitly.
    - Skip keys present in *secret_keys*.

    Returns ``(merged_dict, changed)``.
    """
    changed = False
    merged = dict(current)
    for key, value in fragment.items():
        if key == "env" or key in secret_keys:
            continue
        # Treat the fragment as defaults. Do not overwrite a user's existing
        # model/provider/autonomy choices; those can be machine/account-specific.
        if key not in merged:
            merged[key] = value
            changed = True
    return merged, changed


def hook_command_merge_strategy(
    settings: dict,
    event: str,
    command: str,
    *,
    hook_type: str = "command",
) -> tuple[dict, bool]:
    """Add a kit-owned command to ``settings["hooks"][event]`` if absent.

    Dedupe key is exact string equality of an existing entry's ``command``
    field within *event*'s hook groups — independent of ``matcher``
    presence, since real Claude Code installs often omit it. Existing
    groups/events/commands are left untouched; a new group is appended
    only when no existing group in *event* already contains *command*.

    Returns ``(merged, changed)``. No-ops (returns ``(settings, False)``)
    when ``hooks`` or ``hooks[event]`` exists but isn't the expected type.
    """
    hooks = settings.get("hooks", {})
    if "hooks" in settings and not isinstance(hooks, dict):
        return settings, False

    event_groups = hooks.get(event, [])
    if event in hooks and not isinstance(event_groups, list):
        return settings, False

    for group in event_groups:
        if not isinstance(group, dict):
            continue
        for entry in group.get("hooks", []):
            if isinstance(entry, dict) and entry.get("command") == command:
                return settings, False

    merged = dict(settings)
    merged_hooks = dict(hooks)
    merged_hooks[event] = list(event_groups) + [
        {"hooks": [{"type": hook_type, "command": command}]}
    ]
    merged["hooks"] = merged_hooks
    return merged, True


def strip_hook_command(
    settings: dict,
    event: str,
    command: str,
) -> tuple[dict, bool]:
    """Remove only the kit-owned *command* from ``settings["hooks"][event]``.

    Prunes an emptied hook group, then an emptied event list, then an
    emptied ``hooks`` key. All other events/groups/commands are untouched.

    Returns ``(merged, changed)``.
    """
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict) or event not in hooks:
        return settings, False

    event_groups = hooks[event]
    if not isinstance(event_groups, list):
        return settings, False

    new_groups = []
    changed = False
    for group in event_groups:
        if not isinstance(group, dict):
            new_groups.append(group)
            continue
        entries = group.get("hooks", [])
        new_entries = [
            e for e in entries
            if not (isinstance(e, dict) and e.get("command") == command)
        ]
        if len(new_entries) != len(entries):
            changed = True
        if new_entries:
            new_group = dict(group)
            new_group["hooks"] = new_entries
            new_groups.append(new_group)
        # else: group is now empty, drop it (pruned)

    if not changed:
        return settings, False

    merged = dict(settings)
    merged_hooks = dict(hooks)
    if new_groups:
        merged_hooks[event] = new_groups
    else:
        del merged_hooks[event]

    if merged_hooks:
        merged["hooks"] = merged_hooks
    else:
        del merged["hooks"]

    return merged, True


def cursor_hook_merge_strategy(
    hooks_config: dict,
    event: str,
    command: str,
) -> tuple[dict, bool]:
    """Add a kit-owned command to ``hooks_config["hooks"][event]`` (Cursor's flat shape).

    Cursor's ``hooks.json`` entries are plain ``{"command": ...}`` objects
    directly in the event's list — no nested ``matcher``/groups wrapper,
    unlike Claude/Gemini's shape. Dedupe key is exact string equality of an
    existing entry's ``command`` field. Sets ``"version": 1`` only when the
    ``hooks`` key is being created fresh; an existing ``version`` is left
    untouched.

    Returns ``(merged, changed)``. No-ops (returns ``(hooks_config, False)``)
    when ``hooks`` or ``hooks_config["hooks"][event]`` exists but isn't the
    expected type.
    """
    hooks = hooks_config.get("hooks", {})
    if "hooks" in hooks_config and not isinstance(hooks, dict):
        return hooks_config, False

    entries = hooks.get(event, [])
    if event in hooks and not isinstance(entries, list):
        return hooks_config, False

    for entry in entries:
        if isinstance(entry, dict) and entry.get("command") == command:
            return hooks_config, False

    merged = dict(hooks_config)
    if "hooks" not in merged:
        merged.setdefault("version", 1)
    merged_hooks = dict(hooks)
    merged_hooks[event] = list(entries) + [{"command": command}]
    merged["hooks"] = merged_hooks
    return merged, True


def strip_cursor_hook(
    hooks_config: dict,
    event: str,
    command: str,
) -> tuple[dict, bool]:
    """Remove only the kit-owned *command* entry from ``hooks_config["hooks"][event]``.

    Prunes an emptied event list, then an emptied ``hooks`` key. ``version``
    and other events/entries are left untouched.

    Returns ``(merged, changed)``.
    """
    hooks = hooks_config.get("hooks")
    if not isinstance(hooks, dict) or event not in hooks:
        return hooks_config, False

    entries = hooks[event]
    if not isinstance(entries, list):
        return hooks_config, False

    new_entries = [
        e for e in entries if not (isinstance(e, dict) and e.get("command") == command)
    ]
    if len(new_entries) == len(entries):
        return hooks_config, False

    merged = dict(hooks_config)
    merged_hooks = dict(hooks)
    if new_entries:
        merged_hooks[event] = new_entries
    else:
        del merged_hooks[event]

    if merged_hooks:
        merged["hooks"] = merged_hooks
    else:
        del merged["hooks"]

    return merged, True


def codex_hook_block_merge_strategy(
    block: str,
    identity_substring: str,
    current: str | None,
) -> tuple[str, str]:
    """Append a kit-owned literal Codex hooks TOML block if not already present.

    Does NOT parse TOML array-of-tables syntax — *block* is opaque literal
    text. Dedupe is a plain substring check of *identity_substring* (e.g. the
    exact ``command = '...'`` line, byte-stable per install path) within
    *current*. This is intentionally narrow: a general array-of-tables-aware
    TOML merger is out of scope.

    - *current* is ``None`` -> create a file containing just *block*.
    - *identity_substring* in *current* -> unchanged (returns *current*
      unmodified).
    - otherwise -> append *block*, blank-line separated, at end of file.

    Returns ``(merged_content, action)`` where *action* is one of
    ``"create"``, ``"merge"``, or ``"unchanged"``.
    """
    if current is None:
        return block, "create"

    if identity_substring in current:
        return current, "unchanged"

    merged = current.rstrip("\n") + "\n\n" + block
    if not merged.endswith("\n"):
        merged += "\n"
    return merged, "merge"


def strip_codex_hook_block(
    existing: str,
    block: str,
) -> tuple[str | None, bool]:
    """Remove the kit-owned literal hook block via exact substring match of *block*.

    If *block* (verbatim) is not found — e.g. the user hand-edited it — this
    no-ops, returning ``(existing, False)``, rather than attempting a fuzzy
    repair that risks corrupting unrelated TOML content.

    Returns ``(remaining_content, fully_owned)``; *remaining_content* is
    ``None`` only when stripping the block empties the file entirely.
    """
    if block not in existing:
        return existing, False

    remaining = existing.replace(block, "", 1).strip()
    if not remaining:
        return None, True
    if not remaining.endswith("\n"):
        remaining += "\n"
    return remaining, False


def strip_jsonc_comments(text: str) -> str:
    """Strip ``//`` and ``/* */`` comments and trailing commas from a JSONC text.

    This is intentionally minimal — it handles the common cases produced by
    OpenCode's own config examples. It does not handle comments inside strings
    containing ``'//'`` or ``'/*'`` as literal content; OpenCode config does not
    produce such cases.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    string_quote = ""
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == string_quote:
                in_string = False
            i += 1
            continue
        if ch in ("'", '"'):
            in_string = True
            string_quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            # line comment
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            # block comment
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    cleaned = "".join(out)
    # Remove trailing commas before } or ]
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    return cleaned


def parse_jsonc(text: str) -> dict:
    """Parse a JSONC text, falling back to comment stripping on failure."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(strip_jsonc_comments(text))


def jsonc_defaults_strategy(
    fragment: dict,
    current: dict,
    local_only_keys: Collection[str],
    is_secret_key: Callable[[str], bool],
) -> tuple[dict, bool]:
    """Merge JSONC fragment defaults into current settings.

    - Never overwrite existing keys.
    - Skip keys present in *local_only_keys*.
    - Skip keys where *is_secret_key(key)* returns ``True``.

    Returns ``(merged_dict, changed)``.
    """
    changed = False
    merged = dict(current)
    safe_fragment: dict = {}
    for key, value in fragment.items():
        if key in local_only_keys:
            continue
        if is_secret_key(key):
            continue
        safe_fragment[key] = value

    for key, value in safe_fragment.items():
        if key not in merged:
            merged[key] = value
            changed = True
    return merged, changed


def marked_section_strategy(
    template: str,
    existing: str | None,
    begin_marker: str,
    end_marker: str,
) -> tuple[str, str]:
    """Return ``(merged_content, action)`` for marked-section merge.

    Actions:
      - ``'create'``: file did not exist; the merged content equals the wrapped
        template.
      - ``'merge'``: file existed and the merged content differs from existing.
      - ``'unchanged'``: file existed and the merged content equals existing.

    Merge rules:
      - Existing markers present: replace content between them; keep before
        and after verbatim.
      - No existing markers: prepend the marked section; keep the user's
        existing content untouched below the markers.
    """
    wrapped = begin_marker + template + end_marker
    if existing is None:
        return wrapped, "create"
    if begin_marker in existing and end_marker in existing:
        before, _, rest = existing.partition(begin_marker)
        _, _, after = rest.partition(end_marker)
        merged = before + begin_marker + template + end_marker + after
    else:
        merged = wrapped + existing
    if merged == existing:
        return merged, "unchanged"
    return merged, "merge"


def strip_marked_section(
    existing: str,
    begin_marker: str,
    end_marker: str,
) -> tuple[str | None, bool]:
    """Return ``(remaining_content, fully_owned)``.

    - *remaining_content*: file with our section removed (``None`` if file
      should be deleted entirely).
    - *fully_owned*: ``True`` if the entire file was our injected section
      (i.e. the caller can safely delete the file). ``False`` if user content
      remains.
    """
    if begin_marker not in existing or end_marker not in existing:
        return existing, False
    before, _, rest = existing.partition(begin_marker)
    _, _, after = rest.partition(end_marker)
    remaining = (before + after).strip()
    if not remaining:
        return None, True
    if not remaining.endswith("\n"):
        remaining += "\n"
    return remaining, False


def _find_toml_section(
    content: str, section_header: str
) -> tuple[str, str, str] | None:
    """Locate a TOML top-level section by its ``[header]`` line.

    Returns ``(before, body, after)`` or ``None`` if the section is not present.

    *before*  — everything up to (but not including) the header line.
    *body*    — content after the header line until the next top-level
                ``[section]`` line or end-of-file.
    *after*   — content from the next top-level ``[section]`` line onward
                (empty string if this is the last section).
    """
    target = section_header + "\n"
    idx = content.find(target)
    if idx == -1:
        return None
    before = content[:idx]
    body_start = idx + len(target)
    rest = content[body_start:]
    next_section = re.search(r"^\[", rest, re.MULTILINE)
    if next_section:
        body = rest[: next_section.start()]
        after = rest[next_section.start() :]
    else:
        body = rest
        after = ""
    return before, body, after


def toml_block_merge_strategy(
    section_header: str,
    template_body: str,
    current: str | None,
) -> tuple[str, str]:
    """Insert or replace a kit-owned TOML section block.

    - *current* is ``None`` → create a new file with just the section.
    - Section present → replace its body with *template_body*.
    - Section absent → append the section block.
    - Unrelated tables and comments outside the kit block are preserved
      byte-for-byte.  Comments *inside* the kit block may be replaced by the
      canonical template.

    Returns ``(merged_content, action)`` where *action* is one of
    ``"create"``, ``"merge"``, or ``"unchanged"``.
    """
    if current is None:
        return section_header + "\n" + template_body, "create"

    located = _find_toml_section(current, section_header)
    if located is None:
        merged = current.rstrip("\n") + "\n\n" + section_header + "\n" + template_body
        if not merged.endswith("\n"):
            merged += "\n"
        return merged, "merge"

    before, _existing_body, after = located
    merged = before + section_header + "\n" + template_body + after
    if merged == current:
        return merged, "unchanged"
    return merged, "merge"


def strip_toml_block(
    existing: str,
    section_header: str,
) -> tuple[str | None, bool]:
    """Remove only the kit-owned TOML section.

    Returns ``(remaining_content, fully_owned)``.

    - *remaining_content* is ``None`` when the file should be deleted entirely
      (it contained only the kit section).
    - *fully_owned* is ``True`` only in that case; ``False`` otherwise.
    """
    located = _find_toml_section(existing, section_header)
    if located is None:
        return existing, False

    before, _body, after = located
    remaining = (before + after).strip()
    if not remaining:
        return None, True
    if not remaining.endswith("\n"):
        remaining += "\n"
    return remaining, False
