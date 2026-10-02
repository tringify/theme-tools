import hashlib
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

import test_tooling as fixtures
from build import build
from package import package


class SourceWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.fixtures = fixtures.ThemeToolingTest()

    def snapshot(self, root):
        return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob("*") if p.is_file() and "dist" not in p.relative_to(root).parts}

    def test_package_builds_latest_source_without_mutating_author_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixtures.make_theme(root)
            build(root)
            (root / "src/sections/hero/body.html").write_text("<section>Fresh content</section>")
            checker = self.fixtures.make_checker(root)
            before = self.snapshot(root)
            output = root / "dist/theme.zip"
            package(root, output, checker=str(checker))
            with zipfile.ZipFile(output) as archive:
                self.assertIn(b"Fresh content", archive.read("sections/hero.vasc"))
                self.assertNotIn("src/.generated-sections.json", archive.namelist())
            self.assertEqual(before, self.snapshot(root))

    def test_build_refreshes_manifest_and_only_prunes_owned_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixtures.make_theme(root)
            manifest = json.loads((root / "theme.json").read_text())
            manual = {"name": "manual", "file": "sections/manual.vasc", "kind": "section"}
            manifest["sections"].append(manual)
            (root / "theme.json").write_text(json.dumps(manifest))
            (root / "sections/manual.vasc").write_text("Authored directly")
            build(root)
            shutil.move(str(root / "src/sections/hero"), str(root / "src/sections/banner"))
            (root / "src/sections/banner/schema.json").write_text(json.dumps({"name": "banner", "kind": "section"}))
            build(root)
            self.assertFalse((root / "sections/hero.vasc").exists())
            self.assertEqual((root / "sections/manual.vasc").read_text(), "Authored directly")
            entries = json.loads((root / "theme.json").read_text())["sections"]
            self.assertEqual([entry["name"] for entry in entries], ["manual", "banner"])

    def test_modified_stale_output_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixtures.make_theme(root)
            build(root)
            (root / "sections/hero.vasc").write_text("Preserve my edit")
            shutil.rmtree(root / "src/sections/hero")
            with self.assertRaisesRegex(ValueError, "previously generated section was edited"):
                build(root)
            self.assertEqual((root / "sections/hero.vasc").read_text(), "Preserve my edit")

    def test_runtime_only_themes_can_still_be_packaged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixtures.make_theme(root)
            build(root)
            shutil.rmtree(root / "src")
            checker = self.fixtures.make_checker(root)
            package(root, root / "dist/theme.zip", checker=str(checker))

    def test_symlinks_cannot_read_or_overwrite_files_outside_theme(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "theme"
            self.fixtures.make_theme(root)
            outside = base / "private.txt"
            outside.write_text("outside")
            target = root / "sections/hero.vasc"
            target.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symlinks"):
                build(root)
            with self.assertRaisesRegex(ValueError, "symlinks"):
                package(root, root / "dist/theme.zip")
            self.assertEqual(outside.read_text(), "outside")

    def test_output_cannot_be_the_theme_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixtures.make_theme(root)
            with self.assertRaisesRegex(ValueError, "outputs inside"):
                package(root, root)

    def test_invalid_schema_names_the_file_and_keeps_compiled_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixtures.make_theme(root)
            build(root)
            previous = (root / "sections/hero.vasc").read_bytes()
            (root / "src/sections/hero/schema.json").write_text("{invalid")
            with self.assertRaisesRegex(ValueError, r"src/sections/hero/schema.json:1:2:"):
                build(root)
            self.assertEqual((root / "sections/hero.vasc").read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
