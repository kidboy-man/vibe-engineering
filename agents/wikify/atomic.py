"""Atomic text writes for wikify commands (exclusive temp file, no symlink following)."""

from __future__ import annotations

import os
from pathlib import Path


def write_atomic(path: Path, text: str, exclusive: bool = False) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp, flags, 0o666)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
        if exclusive and path.exists():
            raise FileExistsError(path.name)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
