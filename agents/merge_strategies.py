"""Merge strategies for kit installers.

Each strategy is a pure function that takes template/current content and
returns merged content plus metadata.  They know nothing about disk paths
or I/O — that stays in the installers.
"""

from __future__ import annotations

import json
import re
from typing import Callable


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
    local_only_keys: set[str],
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
