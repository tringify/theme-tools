"""Initialization preserves originals and publishes only validated editable source."""

import json
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

import test_cli


class InitializeTests(unittest.TestCase):
    run_cli = test_cli.ThemeCliTest.run_cli
    make_theme = test_cli.ThemeCliTest.make_theme
    make_checker = test_cli.ThemeCliTest.make_checker

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "starter"
        self.destination = self.root / "new-theme"
        self.make_theme(self.source)
        self.checker = self.make_checker(self.root)

    def initialize(self, **options):
        return self.run_cli(
            "init", str(options.get("destination", self.destination)),
            "--from", str(options.get("source", self.source)),
            "--name", options.get("name", "Studio Élan"),
            "--checker", str(options.get("checker", self.checker)),
        )

    def test_creates_editable_source_and_rebuilds_without_changing_original(self):
        for name in (".env", "setup.py", "README.md", "LICENSE", "NOTICE.txt"):
            (self.source / name).write_text("Template text: " + name)
        (self.source / "src/sections/hero/body.html").chmod(0o755)
        for name in (".git", "node_modules", "dist"):
            (self.source / name).mkdir()
            (self.source / name / "unwanted").write_text("Do not copy")
        (self.source / "sections/hero.vasc").write_text("Stale output")
        before = {str(path.relative_to(self.source)): path.read_bytes() for path in self.source.rglob("*") if path.is_file()}
        result = self.initialize()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Created Studio Élan", result.stdout)
        manifest = json.loads((self.destination / "theme.json").read_text())
        self.assertEqual(manifest["name"], "Studio Élan")
        self.assertEqual(manifest["status"], "draft")
        self.assertEqual(manifest["surfaces"][0]["required_sections"], ["hero"])
        self.assertIn("<section>Hero</section>", (self.destination / "sections/hero.vasc").read_text())
        self.assertTrue((self.destination / "src/.generated-sections.json").is_file())
        for name in ("README.md", "LICENSE", "NOTICE.txt"):
            self.assertEqual((self.destination / name).read_bytes(), (self.source / name).read_bytes())
        for name in (".git", "node_modules", "dist", ".env", "setup.py"):
            self.assertFalse((self.destination / name).exists(), name)
        self.assertEqual(stat.S_IMODE((self.destination / "src/sections/hero/body.html").stat().st_mode), 0o644)
        self.assertEqual(before, {str(path.relative_to(self.source)): path.read_bytes() for path in self.source.rglob("*") if path.is_file()})

    def test_existing_directory_or_file_is_never_overwritten(self):
        self.destination.mkdir()
        sentinel = self.destination / "keep.txt"
        sentinel.write_text("Existing work")
        result = self.initialize()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists", result.stderr)
        self.assertEqual(sentinel.read_text(), "Existing work")
        sentinel.unlink()
        self.assertNotEqual(self.initialize().returncode, 0)  # Empty directory also belongs to someone.
        self.destination.rmdir()
        self.destination.write_text("Existing file")
        self.assertNotEqual(self.initialize().returncode, 0)
        self.assertEqual(self.destination.read_text(), "Existing file")

    def test_checker_failure_leaves_no_destination_or_staging_files(self):
        rejected = self.make_checker(self.root, accept=False)
        before = set(self.root.iterdir())
        result = self.initialize(checker=rejected)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.destination.exists())
        self.assertEqual(before, set(self.root.iterdir()))

    def test_destination_created_during_validation_is_preserved(self):
        self.checker.write_text(
            "#!/usr/bin/env python3\nfrom pathlib import Path\n"
            f"destination = Path({str(self.destination)!r})\n"
            "destination.mkdir()\n(destination / 'keep.txt').write_text('Concurrent work')\n"
            "print('{\"valid\":true}')\n"
        )
        result = self.initialize()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.destination / "keep.txt").read_text(), "Concurrent work")
        self.assertEqual([path.name for path in self.destination.iterdir()], ["keep.txt"])

    def test_rejects_symlink_sources_and_destinations(self):
        link = self.root / "linked-source"
        link.symlink_to(self.source, target_is_directory=True)
        self.assertNotEqual(self.initialize(source=link).returncode, 0)
        self.destination.symlink_to(self.root / "does-not-exist")
        self.assertNotEqual(self.initialize().returncode, 0)
        self.assertTrue(self.destination.is_symlink())
        self.destination.unlink()
        (self.source / "assets").mkdir()
        (self.source / "assets/outside.png").symlink_to(self.root / "does-not-exist")
        result = self.initialize()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertFalse(self.destination.exists())

    def test_rejects_nested_destination_and_unrecognized_source(self):
        self.assertNotEqual(self.initialize(destination=self.source / "nested").returncode, 0)
        (self.source / "src/.env").write_text("must not be copied")
        result = self.initialize()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported editable source file", result.stderr)
        self.assertFalse(self.destination.exists())

    def test_name_validation_happens_before_writing(self):
        for name in ("", "   ", "A" * 101, "Injected\nname", "A\x7fB"):
            with self.subTest(name=name):
                self.assertNotEqual(self.initialize(name=name).returncode, 0)
                self.assertFalse(self.destination.exists())

    def test_accepts_direct_vein_theme_and_preserves_section_identifiers(self):
        shutil.rmtree(self.source / "src")
        original = '<h1>{{ shop.name }}</h1>{% schema %}{"name":"hero","kind":"section","ctx_needs":["shop"]}{% endschema %}'
        (self.source / "sections/hero.vasc").write_text(original)
        result = self.initialize()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.destination / "sections/hero.vasc").read_text(), original)
        self.assertFalse((self.destination / "src").exists())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO source protection applies on Unix")
    def test_non_regular_source_is_rejected_without_reading(self):
        (self.source / "assets").mkdir()
        os.mkfifo(self.source / "assets/wait.png")
        result = self.initialize()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("regular files", result.stderr)
        self.assertFalse(self.destination.exists())
