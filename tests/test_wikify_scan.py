import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents.wikify import scan

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


if __name__ == "__main__":
    unittest.main()
