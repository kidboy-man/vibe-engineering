"""qmd runtime probes: version gate and collection status."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from agents.kits.second_brain.paths import QMD_COLLECTION_NAME


def _check_min_version(binary: str, args: list[str], min_major: int) -> tuple[bool, str]:
    """Return (ok, message). ok=False when binary missing or major version < min_major."""
    if not shutil.which(binary):
        return False, f"{binary}: not found"
    try:
        out = subprocess.run([binary] + args, capture_output=True, text=True, timeout=5)
        m = re.search(r"(\d+)\.", out.stdout + out.stderr)
        if m and int(m.group(1)) < min_major:
            return False, f"{binary}: major version {m.group(1)} < {min_major}"
    except Exception:
        pass
    return True, ""


def _qmd_collection_status(vault_path: Path) -> tuple[bool, str | None]:
    """Return whether qmd's managed collection points at this vault's wiki.

    qmd 2.5+ prints only a virtual URI from `collection list`; `collection show`
    is its stable physical-path interface. Older qmd versions fall back to the
    legacy list output.
    """
    wiki_path = (vault_path / "wiki").resolve()
    shown = subprocess.run(
        ["qmd", "collection", "show", QMD_COLLECTION_NAME],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if shown.returncode == 0:
        match = re.search(r"^\s*Path:\s*(.+?)\s*$", shown.stdout, re.MULTILINE)
        if match:
            return Path(match.group(1)).expanduser().resolve() == wiki_path, None
        return str(wiki_path) in shown.stdout, None

    listed = subprocess.run(
        ["qmd", "collection", "list"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if listed.returncode != 0:
        return False, (listed.stderr or shown.stderr).strip() or "qmd collection inspection failed"
    return str(wiki_path) in listed.stdout, None
