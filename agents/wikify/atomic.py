"""Atomic text writes for wikify commands (exclusive temp file, no symlink following)."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


def write_atomic(path: Path, text: str, exclusive: bool = False) -> None:
    """Write ``text`` to ``path`` through a private temp file in the same directory.

    ``exclusive`` creates the file only if it does not exist (``os.link`` fails atomically with
    FileExistsError, so two writers cannot both win); otherwise an existing file is replaced."""
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp, flags, 0o666)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
        if exclusive:
            try:
                os.link(tmp, path)
            except FileExistsError:
                raise
            except OSError:  # no hard links on this filesystem: best-effort check, then replace
                if path.exists():
                    raise FileExistsError(path.name)
                os.replace(tmp, path)
                return
            tmp.unlink()
        else:
            os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
