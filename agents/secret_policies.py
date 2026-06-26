"""Shared key policies for JSONC config adapters.

The OpenCode JSONC adapter and the second-brain kit's OpenCode adapter both
need the same two concepts: a set of top-level keys the kit must never
overwrite, and a list of substrings that mark a key as a secret.
"""

from __future__ import annotations

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


def is_secret_key(name: str) -> bool:
    """True if *name* looks like it holds a secret, by substring match."""
    lowered = name.lower()
    return any(sub in lowered for sub in SECRET_KEY_SUBSTRINGS)
