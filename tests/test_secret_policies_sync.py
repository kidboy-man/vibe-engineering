"""secret_policies.is_secret_path must match the standalone guard.py copy.

Hook scripts cannot import `agents`, so the guardrails hook carries its own
copy of the policy; this test keeps the two from drifting.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from agents import secret_policies

GUARD = (
    Path(__file__).resolve().parents[1]
    / "agents/kits/guardrails/templates/guardrails/hooks/vibe-guardrails/guard.py"
)

CASES = [
    (".env", True),
    (".env.local", True),
    (".env.example", False),
    ("a/b/id_rsa", True),
    ("id_rsa.pub", False),
    ("k.pem", True),
    ("home/.aws/credentials", True),
    ("src/app.py", False),
    ("", False),
]


def _load_guard():
    spec = importlib.util.spec_from_file_location("vibe_guard_under_test", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SecretPolicySyncTest(unittest.TestCase):
    def test_matches_guard_copy(self):
        guard = _load_guard()
        for path, expected in CASES:
            with self.subTest(path=path):
                self.assertEqual(guard.is_secret_path(path), expected)
                self.assertEqual(secret_policies.is_secret_path(path), expected)


if __name__ == "__main__":
    unittest.main()
