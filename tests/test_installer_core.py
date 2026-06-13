import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import installer_core as core


class InstallerCorePrimitivesTests(unittest.TestCase):
    """Unit tests for shared installer primitives in installer_core.py."""

    def test_read_text_reads_utf8_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hello.txt"
            path.write_text("hello world", encoding="utf-8")
            self.assertEqual(core.read_text(path), "hello world")

    def test_write_text_creates_missing_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a" / "b" / "file.txt"
            core.write_text(path, "content")
            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(encoding="utf-8"), "content")

    def test_timestamp_is_utc_and_sortable(self):
        ts = core.timestamp()
        self.assertRegex(ts, r"^\d{8}T\d{6}Z$")

    def test_backup_copies_file_to_backups_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "config"
            base.mkdir()
            original = base / "settings.json"
            original.write_text("{}", encoding="utf-8")

            result = core.backup(original, base)

            self.assertIsNotNone(result)
            assert result is not None
            self.assertTrue(result.exists())
            self.assertEqual(result.read_text(encoding="utf-8"), "{}")
            self.assertIn("backups/vibe-engineering/", str(result.relative_to(base)))

    def test_backup_returns_none_for_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "config"
            base.mkdir()
            missing = base / "nope.txt"
            self.assertIsNone(core.backup(missing, base))

    def test_load_manifest_reads_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            template_dir.mkdir()
            manifest = {"managed_files": ["a.md", "b.md"]}
            (template_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            loaded = core.load_manifest(template_dir)
            self.assertEqual(loaded["managed_files"], ["a.md", "b.md"])

    def test_target_files_builds_src_dst_rel_tuples(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            target_dir = Path(tmp) / "target"
            manifest = {"managed_files": ["a.md", "sub/b.md"]}

            result = core.target_files(template_dir, target_dir, manifest)

            self.assertEqual(len(result), 2)
            self.assertEqual(result[0], (template_dir / "a.md", target_dir / "a.md", "a.md"))
            self.assertEqual(result[1], (template_dir / "sub/b.md", target_dir / "sub/b.md", "sub/b.md"))

    def test_manifest_state_contains_required_keys(self):
        state = core.manifest_state("test-kit", ["x.md", "y.md"])
        self.assertEqual(state["tool"], "vibe-engineering")
        self.assertEqual(state["kit"], "test-kit")
        self.assertIn("installed_at", state)
        self.assertEqual(state["managed_files"], ["x.md", "y.md"])
        self.assertIn("notes", state)

    def test_manifest_state_sorts_managed_files(self):
        state = core.manifest_state("test-kit", ["z.md", "a.md"])
        self.assertEqual(state["managed_files"], ["a.md", "z.md"])

    def test_load_existing_install_manifest_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            self.assertIsNone(core.load_existing_install_manifest(path))

    def test_load_existing_install_manifest_returns_dict_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text('{"kit": "test"}', encoding="utf-8")
            self.assertEqual(core.load_existing_install_manifest(path), {"kit": "test"})

    def test_load_existing_install_manifest_returns_none_on_bad_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text("not json", encoding="utf-8")
            self.assertIsNone(core.load_existing_install_manifest(path))

    def test_confirm_returns_true_when_yes_is_true(self):
        self.assertTrue(core.confirm("prompt", yes=True))

    def test_planned_changes_copy_style_reports_create_update_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            target_dir = Path(tmp) / "target"
            template_dir.mkdir()
            target_dir.mkdir()

            (template_dir / "new.md").write_text("new", encoding="utf-8")
            (template_dir / "changed.md").write_text("changed", encoding="utf-8")
            (target_dir / "changed.md").write_text("old", encoding="utf-8")
            (template_dir / "same.md").write_text("same", encoding="utf-8")
            (target_dir / "same.md").write_text("same", encoding="utf-8")

            files = [
                (template_dir / "new.md", target_dir / "new.md", "new.md"),
                (template_dir / "changed.md", target_dir / "changed.md", "changed.md"),
                (template_dir / "same.md", target_dir / "same.md", "same.md"),
            ]
            changes = core.planned_changes_copy_style(files)
            self.assertIn("create new.md", changes)
            self.assertIn("update changed.md", changes)
            self.assertIn("unchanged same.md", changes)

    def test_install_copy_style_file_creates_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            target_dir = Path(tmp) / "target"
            template_dir.mkdir()
            target_dir.mkdir()
            src = template_dir / "file.md"
            src.write_text("content", encoding="utf-8")
            dst = target_dir / "file.md"

            self.assertTrue(core.install_copy_style_file(src, dst, target_dir))
            self.assertEqual(dst.read_text(encoding="utf-8"), "content")

    def test_install_copy_style_file_returns_false_when_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            target_dir = Path(tmp) / "target"
            template_dir.mkdir()
            target_dir.mkdir()
            src = template_dir / "file.md"
            src.write_text("content", encoding="utf-8")
            dst = target_dir / "file.md"
            dst.write_text("content", encoding="utf-8")

            self.assertFalse(core.install_copy_style_file(src, dst, target_dir))

    def test_install_copy_style_file_backups_existing_before_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            target_dir = Path(tmp) / "target"
            template_dir.mkdir()
            target_dir.mkdir()
            src = template_dir / "file.md"
            src.write_text("new", encoding="utf-8")
            dst = target_dir / "file.md"
            dst.write_text("old", encoding="utf-8")

            self.assertTrue(core.install_copy_style_file(src, dst, target_dir))
            backups = list((target_dir / "backups").rglob("*"))
            backup_files = [b for b in backups if b.is_file()]
            self.assertEqual(len(backup_files), 1)
            self.assertEqual(backup_files[0].read_text(encoding="utf-8"), "old")

    def test_uninstall_unchanged_file_removes_identical_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            target_dir = Path(tmp) / "target"
            template_dir.mkdir()
            target_dir.mkdir()
            src = template_dir / "file.md"
            src.write_text("content", encoding="utf-8")
            dst = target_dir / "file.md"
            dst.write_text("content", encoding="utf-8")

            self.assertTrue(core.uninstall_unchanged_file(src, dst))
            self.assertFalse(dst.exists())

    def test_uninstall_unchanged_file_keeps_modified_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            target_dir = Path(tmp) / "target"
            template_dir.mkdir()
            target_dir.mkdir()
            src = template_dir / "file.md"
            src.write_text("template", encoding="utf-8")
            dst = target_dir / "file.md"
            dst.write_text("modified", encoding="utf-8")

            self.assertFalse(core.uninstall_unchanged_file(src, dst))
            self.assertTrue(dst.exists())

    def test_uninstall_unchanged_file_returns_false_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            target_dir = Path(tmp) / "target"
            template_dir.mkdir()
            src = template_dir / "file.md"
            src.write_text("content", encoding="utf-8")
            dst = target_dir / "file.md"

            self.assertFalse(core.uninstall_unchanged_file(src, dst))

    def test_diff_copy_style_returns_false_when_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            target_dir = Path(tmp) / "target"
            template_dir.mkdir()
            target_dir.mkdir()
            src = template_dir / "file.md"
            src.write_text("content", encoding="utf-8")
            dst = target_dir / "file.md"
            dst.write_text("content", encoding="utf-8")

            self.assertFalse(core.diff_copy_style(src, dst, "file.md"))

    def test_diff_copy_style_returns_true_when_different(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            target_dir = Path(tmp) / "target"
            template_dir.mkdir()
            target_dir.mkdir()
            src = template_dir / "file.md"
            src.write_text("new", encoding="utf-8")
            dst = target_dir / "file.md"
            dst.write_text("old", encoding="utf-8")

            self.assertTrue(core.diff_copy_style(src, dst, "file.md"))

    def test_diff_copy_style_returns_true_when_dst_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = Path(tmp) / "templates"
            target_dir = Path(tmp) / "target"
            template_dir.mkdir()
            src = template_dir / "file.md"
            src.write_text("content", encoding="utf-8")
            dst = target_dir / "file.md"

            self.assertTrue(core.diff_copy_style(src, dst, "file.md"))


if __name__ == "__main__":
    unittest.main()
