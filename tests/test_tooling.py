import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build import build
from package import package
from validate import validate


class ThemeToolingTest(unittest.TestCase):
    def make_theme(self, root: Path) -> None:
        for directory in ("sections", "src/sections/hero", "templates"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        (root / "src/_shared.css").write_text("html { color: black; }\n", encoding="utf-8")
        (root / "src/sections/hero/body.html").write_text("<section>Hero</section>\n", encoding="utf-8")
        (root / "src/sections/hero/style.css").write_text("section { display: block; }\n", encoding="utf-8")
        (root / "src/sections/hero/schema.json").write_text(
            json.dumps({"name": "hero", "kind": "section"}), encoding="utf-8"
        )
        (root / "theme.json").write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "name": "Test",
                    "source": "uploaded",
                    "status": "draft",
                    "default_locale": "en",
                    "sections": [
                        {
                            "name": "hero",
                            "kind": "section",
                            "file": "sections/hero.vasc",
                            "origin": "override",
                        }
                    ],
                    "surfaces": [{"surface_key": "home", "required_sections": ["hero"]}],
                }
            ),
            encoding="utf-8",
        )
        (root / "surfaces.json").write_text("{}\n", encoding="utf-8")
        (root / "tokens.json").write_text("{}\n", encoding="utf-8")
        (root / "templates/home.json").write_text(
            json.dumps({"page_type": "home", "sections": [{"type": "hero", "position": 0}]}),
            encoding="utf-8",
        )

    def make_checker(self, root: Path, *, accept: bool = True) -> Path:
        checker = root / "themecheck"
        checker.write_text(
            """#!/usr/bin/env python3
import sys
import zipfile

assert sys.argv[1:3] == ["-json", "-mode"]
assert sys.argv[3] in ("sealed", "development")
with zipfile.ZipFile(sys.argv[4]) as archive:
    names = archive.namelist()
assert "theme.json" in names
assert "surfaces.json" not in names
print('{"valid":true}')
sys.exit(%d)
"""
            % (0 if accept else 1),
            encoding="utf-8",
        )
        checker.chmod(0o755)
        return checker

    def test_validate_and_package_invoke_checker_for_runtime_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_theme(root)
            build(root)
            checker = self.make_checker(root)

            self.assertEqual(validate(root, checker=str(checker)), ["hero"])
            output = root / "dist/theme.zip"
            package(root, output, checker=str(checker))
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
            self.assertIn("theme.json", names)
            self.assertIn("sections/hero.vasc", names)
            self.assertNotIn("surfaces.json", names)
            self.assertNotIn("src/_shared.css", names)

    def test_failed_gate_does_not_replace_existing_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_theme(root)
            build(root)
            output = root / "dist/theme.zip"
            good_checker = self.make_checker(root)
            package(root, output, checker=str(good_checker))
            accepted = output.read_bytes()

            bad_checker = self.make_checker(root, accept=False)
            with self.assertRaises(ValueError):
                package(root, output, checker=str(bad_checker))
            self.assertEqual(output.read_bytes(), accepted)

    def test_missing_checker_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_theme(root)
            build(root)
            with patch.dict(os.environ, {}, clear=True), patch("validate.shutil.which", return_value=None):
                with self.assertRaisesRegex(ValueError, "themecheck is required"):
                    validate(root)


if __name__ == "__main__":
    unittest.main()
