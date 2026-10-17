import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents.wikify import scan
from tests.wikify_perf_helpers import assert_scales_linearly

# Fake secrets are assembled at runtime so no secret-looking literal sits here.
AWS = "AKIA" + "IOSFODNN7" + "EXAMPLE"
GHP = "ghp_" + "a" * 36
SLACK = "xoxb" + "-" + "1" * 12
BEARER = "Bearer " + "a" * 24
JWT = ".".join(["eyJ" + "hbGciOi", "eyJ" + "zdWIiOi", "c2ln" + "bmF0dXJl"])
PEM = "-----BEGIN " + "RSA " + "PRIVATE KEY-----"
ASSIGN = 'api_key = "' + "x" * 12 + '"'


class ScanTextCase(unittest.TestCase):
    def rules(self, text):
        return [rule for _, rule in scan.scan_text(text)]

    def test_rules_positive(self):
        cases = {
            "private-key": PEM,
            "aws-access-key": "id " + AWS,
            "github-token": GHP,
            "slack-token": SLACK,
            "bearer-token": "Authorization: " + BEARER,
            "jwt": "t=" + JWT,
            "home-path": "see /home/alice/project/x.py",
            "email": "mail bob@corp.io now",
            "secret-assignment": ASSIGN,
        }
        for rule, text in cases.items():
            with self.subTest(rule=rule):
                self.assertIn(rule, self.rules(text))

    def test_rules_benign(self):
        cases = {
            "private-key": "-----BEGIN CERTIFICATE-----",
            "aws-access-key": "AKIA" + "SHORT",
            "github-token": "ghp_" + "a" * 10,
            "slack-token": "xoxz-" + "1" * 12,
            "bearer-token": "Bearer token required",
            "jwt": "eyJ only one segment",
            "home-path": "use /home/<name>/ or ~/ here",
            "email": "user at example dot com; @decorator",
            "secret-assignment": 'password = "short"',
        }
        for rule, text in cases.items():
            with self.subTest(rule=rule):
                self.assertNotIn(rule, self.rules(text))

    def test_jwt_after_word_char(self):
        for prefix in ("x_", "x-", "token:"):
            with self.subTest(prefix=prefix):
                self.assertIn("jwt", self.rules(prefix + JWT))

    def test_private_key_variants(self):
        for kind in ("PGP PRIVATE KEY BLOCK", "ENCRYPTED PRIVATE KEY", "DSA PRIVATE KEY"):
            with self.subTest(kind=kind):
                self.assertIn("private-key", self.rules("-----BEGIN " + kind + "-----"))

    def test_secret_assignment_shapes(self):
        pos = [
            '"api_key": "' + "x" * 8 + "1234" + '"',
            "password: " + "hunter" + "2" * 6,
            "token =\u00a0\"" + "y" * 12 + '"',
            "DB_PASSWD=" + "abcdef" + "12345",
        ]
        for text in pos:
            with self.subTest(text=text):
                self.assertIn("secret-assignment", self.rules(text))
        for text in ("password: required", "token: refresh", "secret: none",
                     "password: requiredvalue"):
            with self.subTest(text=text):
                self.assertNotIn("secret-assignment", self.rules(text))

    def test_adversarial_input_is_fast(self):
        for unit in ("eyJ", "token=", "Bearer ", "x_eyJ", "_eyJ", "-eyJ"):
            with self.subTest(unit=unit):
                assert_scales_linearly(
                    self,
                    lambda n, unit=unit: (unit * (n // len(unit)),),
                    scan.scan_text,
                    16_384,
                    label=unit,
                )

    def test_adversarial_wiki_file_is_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "docs" / "wiki"
            wiki.mkdir(parents=True)

            def make(n):
                (wiki / "a.md").write_text("_eyJ" * (n // 4))
                return (Path(tmp),)

            assert_scales_linearly(self, make, scan.scan_wiki, 16_384, label="scan_wiki")

    def test_real_shaped_jwt_detected(self):
        enc = lambda raw: base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
        header = enc('{"alg":"HS256","typ":"JWT"}')
        self.assertEqual(len(header), 36)
        token = ".".join([header, enc('{"sub":"1234567890","iat":1516239022}'), "s" * 43])
        for prefix in ("", "t=", '"', "'", "Bearer ", "x_", "x-", "\n"):
            with self.subTest(prefix=prefix):
                self.assertIn("jwt", self.rules(prefix + token))

    def test_floor_notice(self):
        self.assertIn("floor", scan.FLOOR_NOTICE)

    def test_line_numbers_and_users_path(self):
        hits = scan.scan_text("ok\nok\n/Users/bob/x\n")
        self.assertEqual(hits, [(3, "home-path")])

    def test_long_input_is_fast(self):
        self.assertEqual(scan.scan_text("a" * 200000 + "\n" + "a@" * 20000), [])


class WikiCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.wiki = self.root / "docs" / "wiki"
        self.wiki.mkdir(parents=True)

    def write(self, rel, text):
        path = self.wiki / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_clean_wiki(self):
        self.write("index.md", "# Index\nnothing here\n")
        self.assertEqual(scan.scan_wiki(self.root), [])

    def test_missing_wiki_dir(self):
        self.assertEqual(scan.scan_wiki(self.root / "nope"), [])

    def test_hit_format_and_human_block_included(self):
        self.write("sub/a.md", "x\n<!-- wikify:human -->\n" + GHP + "\n<!-- /wikify:human -->\n")
        self.assertEqual(scan.scan_wiki(self.root), ["sub/a.md:3: github-token"])

    def test_undecodable_bytes_replaced(self):
        (self.wiki / "b.md").write_bytes(b"\xff\xfe " + AWS.encode() + b"\n")
        self.assertEqual(scan.scan_wiki(self.root), ["b.md:1: aws-access-key"])

    def test_allow_list_exact_page_and_text(self):
        self.write("a.md", "contact noreply@example.com\n")
        self.write("b.md", "contact noreply@example.com\n")
        self.write("c.md", "contact other@example.com\n")
        self.write(".wikify-allow", "# note\n\na.md|noreply@example.com\nc.md|noreply@example.com\n")
        self.assertEqual(
            scan.scan_wiki(self.root), ["b.md:1: email", "c.md:1: email"]
        )
        self.assertEqual(
            scan.allowed_hits(self.root), ["a.md:1: email (allow-listed)"]
        )
        self.assertEqual(scan.load_allow(self.root), {
            ("a.md", "noreply@example.com"), ("c.md", "noreply@example.com"),
        })

    def test_allow_list_by_hash_page_scoped(self):
        self.write("a.md", "contact noreply@example.com\n")
        self.write("b.md", "contact noreply@example.com\n")
        key = scan.allow_key("noreply@example.com")
        self.write(".wikify-allow", f"a.md|{key}\n")
        self.assertEqual(scan.scan_wiki(self.root), ["b.md:1: email"])
        self.assertEqual(scan.allowed_hits(self.root), ["a.md:1: email (allow-listed)"])
        errors, keys, _ = scan.report(self.root)
        self.assertEqual(keys, [f"ALLOW-LIST KEY: b.md:1: email -> b.md|{key}"])
        self.assertNotIn("noreply@example.com", "\n".join(errors + keys))

    def test_unreadable_file_is_a_hit(self):
        self.write("a.md", "fine\n")
        self.write("b.md", GHP + "\n")
        real = Path.read_bytes

        def fake(path):
            if path.name == "a.md":
                raise PermissionError("denied")
            return real(path)

        with mock.patch.object(Path, "read_bytes", fake):
            self.assertEqual(
                scan.scan_wiki(self.root), ["a.md:0: unreadable", "b.md:1: github-token"]
            )
        for entry in ("a.md|unreadable", f"a.md|{scan.allow_key('unreadable')}"):
            self.write(".wikify-allow", entry + "\n")
            with mock.patch.object(Path, "read_bytes", fake):
                self.assertEqual(  # sentinels are never allow-listable
                    scan.scan_wiki(self.root), ["a.md:0: unreadable", "b.md:1: github-token"]
                )

    def test_too_large_file_is_a_hit_and_not_read(self):
        (self.wiki / "big.md").write_bytes(b"a" * ((1 << 20) + 1))
        self.write("b.md", GHP + "\n")
        real = Path.read_bytes

        def fake(path):
            self.assertNotEqual(path.name, "big.md")
            return real(path)

        with mock.patch.object(Path, "read_bytes", fake):
            self.assertEqual(
                scan.scan_wiki(self.root), ["b.md:1: github-token", "big.md:0: too-large"]
            )

    def test_too_large_not_allow_listable(self):
        (self.wiki / "big.md").write_bytes(b"a" * ((1 << 20) + 1))
        self.write(".wikify-allow", f"big.md|too-large\nbig.md|{scan.allow_key('too-large')}\n")
        self.assertEqual(scan.scan_wiki(self.root), ["big.md:0: too-large"])

    def test_allow_file_itself_not_scanned(self):
        self.write(".wikify-allow", "a.md|noreply@example.com\n")
        self.assertEqual(scan.scan_wiki(self.root), [])
        self.assertEqual(scan.allowed_hits(self.root), [])


class ExternalCase(unittest.TestCase):
    def test_external_scanner(self):
        with mock.patch.object(scan.shutil, "which", side_effect=lambda n: "/x/" + n if n == "trufflehog" else None):
            self.assertEqual(scan.external_scanner(), "trufflehog")
        with mock.patch.object(scan.shutil, "which", return_value=None):
            self.assertIsNone(scan.external_scanner())


class StateFileScanTests(unittest.TestCase):
    """Hash-map keys embed cited symbol names; they must not read as secret assignments."""

    def write(self, root, payload):
        path = Path(root) / "docs/wiki/.wikify.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def test_symbol_names_in_the_baseline_maps_are_not_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.write(tmp, {
                "version": 1, "covered": "abc",
                "citations": {
                    "p.md|a/refresh_token.go:9-28|RefreshToken": "4138532df1c2",
                    "p.md|a/auth.go:809-868|ResetPassword": "83feb576b074",
                    "p.md|a/c.go:1-2|ApiSecretKey": "0123456789ab",
                },
                "imported": {"specs/password-policy.md": "0123456789abcdef"},
            })
            self.assertEqual(scan.scan_wiki(tmp), [])

    def test_other_state_keys_are_still_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.write(tmp, {"version": 1, "api_key": "AKIAABCDEFGHIJKLMNOP", "citations": {}})
            self.assertTrue(scan.scan_wiki(tmp))

    def test_an_unparseable_state_file_is_scanned_whole(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "docs/wiki/.wikify.json"
            path.parent.mkdir(parents=True)
            path.write_text('{"token": "AKIAABCDEFGHIJKLMNOP"')
            self.assertTrue(scan.scan_wiki(tmp))


if __name__ == "__main__":
    unittest.main()
