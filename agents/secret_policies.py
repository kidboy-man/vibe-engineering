"""Shared key policies for JSONC config adapters.

The OpenCode JSONC adapter and the second-brain kit's OpenCode adapter both
need the same two concepts: a set of top-level keys the kit must never
overwrite, and a list of substrings that mark a key as a secret.
"""

from __future__ import annotations

import fnmatch

LOCAL_ONLY_KEYS: frozenset[str] = frozenset(
    {
        "model",
        "provider",
        "plugin",
        "mcp",
        "tools",
        "tool",
        "permission",
        "env",
        "agent",
        "experimental",
        "theme",
        "share",
        "autoupdate",
        "instructions",
    }
)

SECRET_KEY_SUBSTRINGS: tuple[str, ...] = (
    "token",
    "key",
    "secret",
    "password",
    "auth",
    "credential",
)

# Mirrors the standalone copy in the guardrails hook (hooks cannot import
# `agents`); tests/test_secret_policies_sync.py keeps the two identical.
SECRET_BASENAMES: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pem",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
)
SECRET_SAFE_SUFFIXES: tuple[str, ...] = (".example", ".sample", ".template", ".dist", ".pub")


def is_secret_key(name: str) -> bool:
    """True if *name* looks like it holds a secret, by substring match."""
    lowered = name.lower()
    return any(sub in lowered for sub in SECRET_KEY_SUBSTRINGS)


def is_secret_path(path: str) -> bool:
    """True if *path* names a secret file (env, private key, cloud creds)."""
    if not isinstance(path, str) or not path:
        return False
    path = path.strip().rstrip("/")
    if path.endswith(SECRET_SAFE_SUFFIXES):
        return False
    if path.endswith(".aws/credentials"):
        return True
    base = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(base, pattern) for pattern in SECRET_BASENAMES)
