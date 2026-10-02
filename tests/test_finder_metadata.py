"""Finder metadata must not break authoring or weaken source rejection."""

import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from archive import write_archive
from build import build
from initialize import initialize
from package import package
from validate import validate
import test_tooling


class FinderMetadataTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        test_tooling.ThemeToolingTest.make_theme(self, self.source)
        self.checker = test_tooling.ThemeToolingTest.make_checker(self, self.root)
        (self.source / "assets/images").mkdir(parents=True)
        build(self.source)

    def test_regular_metadata_is_omitted_without_modifying_source(self):
        for folder in ("", "src", "src/sections", "src/sections/hero", "assets", "assets/images", "templates"):
            (self.source / folder / ".DS_Store").write_bytes(b"Finder metadata")
        before = {str(p.relative_to(self.source)): p.read_bytes() for p in self.source.rglob("*") if p.is_file()}
        destination = self.root / "new-theme"
        initialize(self.source, destination, "New theme", str(self.checker))
        self.assertEqual(list(destination.rglob(".DS_Store")), [])
        self.assertTrue((destination / "src/.generated-sections.json").is_file())
        validate(self.source, checker=str(self.checker))
        output = self.root / "theme.zip"
        package(self.source, output, checker=str(self.checker))
        first = output.read_bytes()
        package(self.source, output, checker=str(self.checker))
        self.assertEqual(output.read_bytes(), first)
        with zipfile.ZipFile(output) as archive:
            self.assertFalse(any(Path(name).name == ".DS_Store" for name in archive.namelist()))
        self.assertEqual(before, {str(p.relative_to(self.source)): p.read_bytes() for p in self.source.rglob("*") if p.is_file()})

    def test_metadata_symlinks_are_rejected_by_all_commands(self):
        sentinel = self.root / "sentinel"
        sentinel.write_text("Do not follow or ignore this link")
        (self.source / "assets/.DS_Store").symlink_to(sentinel)
        for operation in (
            lambda: initialize(self.source, self.root / "new-theme", "New theme", str(self.checker)),
            lambda: package(self.source, self.root / "theme.zip", checker=str(self.checker)),
            lambda: validate(self.source, checker=str(self.checker)),
        ):
            with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, "symlink"):
                operation()
        self.assertFalse((self.root / "new-theme").exists())
        self.assertFalse((self.root / "theme.zip").exists())
        self.assertEqual(sentinel.read_text(), "Do not follow or ignore this link")

    def test_same_named_directory_is_not_silently_dropped(self):
        directory = self.source / "assets/.DS_Store"
        directory.mkdir()
        (directory / "image.svg").write_text("<svg></svg>")
        archive_path = self.root / "archive.zip"
        write_archive(self.source, archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            self.assertIn("assets/.DS_Store/image.svg", archive.namelist())

    def test_other_hidden_source_files_remain_invalid(self):
        (self.source / "src/.not-a-section").write_text("Unexpected source")
        with self.assertRaisesRegex(ValueError, "unsupported editable source file"):
            initialize(self.source, self.root / "new-theme", "New theme", str(self.checker))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "Unix special-file protection")
    def test_same_named_fifo_is_rejected_without_reading(self):
        os.mkfifo(self.source / "assets/.DS_Store")
        with self.assertRaisesRegex(ValueError, "regular files"):
            initialize(self.source, self.root / "new-theme", "New theme", str(self.checker))
        with self.assertRaises(OSError):
            package(self.source, self.root / "theme.zip", checker=str(self.checker))

