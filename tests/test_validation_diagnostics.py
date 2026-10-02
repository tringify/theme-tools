import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validate import check_archive


class ValidationDiagnosticsTest(unittest.TestCase):
    def test_checker_file_and_reason_reach_the_author(self):
        payload = {"valid": False, "error": "Theme section is invalid.", "code": "THEME_IMPORT_INVALID_SECTION",
                   "details": {"file": "sections/hero.vasc", "reason": "Unknown setting type: colour"}}
        with patch("validate.subprocess.run", return_value=subprocess.CompletedProcess([], 1, json.dumps(payload), "")):
            with self.assertRaisesRegex(ValueError, "(?s)File: sections/hero.vasc.*Reason: Unknown setting type: colour"):
                check_archive(Path("theme.zip"), checker="themecheck")

    def test_check_cli_reports_diagnostics_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "theme.json").write_text("{}")
            (root / "tokens.json").write_text("{}")
            checker = root / "checker"
            checker.write_text('#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps({"error":"Invalid template.","details":{"file":"templates/home.json","reason":"Section is not allowed on this surface"}}))\nsys.exit(1)\n')
            checker.chmod(0o755)
            result = subprocess.run([sys.executable, str(ROOT / "theme.py"), "check", str(root), "--checker", str(checker)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("File: templates/home.json", result.stderr)
            self.assertIn("Reason: Section is not allowed", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertNotIn('"error":', result.stderr)

    def test_older_checker_text_errors_remain_visible(self):
        with patch("validate.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "Invalid theme archive")):
            with self.assertRaisesRegex(ValueError, "Invalid theme archive"):
                check_archive(Path("theme.zip"), checker="themecheck")
