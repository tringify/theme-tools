import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from context_data import inspect_context


class ContextDataTests(unittest.TestCase):
    def test_packages_theme_and_returns_renderer_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "theme"
            root.mkdir()
            payload = {"schema_version": 1, "page": "product", "entity": "mug", "context": {"product": {"title": "Mug"}}}
            with patch("context_data.package") as package, patch(
                "context_data.renderer_path", return_value="renderer"
            ), patch(
                "context_data.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""),
            ) as run:
                result = inspect_context(root, "product", "mug", "Editorial", None, "checker")
            self.assertEqual(result, payload)
            package.assert_called_once()
            command = run.call_args.args[0]
            self.assertEqual(command[0], "renderer")
            self.assertIn("--context", command)
            self.assertEqual(command[command.index("--page") + 1], "product")
            self.assertEqual(command[command.index("--entity") + 1], "mug")
            self.assertEqual(command[command.index("--preset") + 1], "Editorial")

    def test_rejects_invalid_renderer_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("context_data.package"), patch(
                "context_data.renderer_path", return_value="renderer"
            ), patch(
                "context_data.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout='{"page":"home"}', stderr=""),
            ):
                with self.assertRaisesRegex(ValueError, "invalid context result"):
                    inspect_context(root, "home", "", "", None, None)

    def test_surfaces_renderer_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("context_data.package"), patch(
                "context_data.renderer_path", return_value="renderer"
            ), patch(
                "context_data.subprocess.run",
                return_value=SimpleNamespace(returncode=1, stdout="", stderr='demo product "missing" not found'),
            ):
                with self.assertRaisesRegex(ValueError, "demo product"):
                    inspect_context(root, "product", "missing", "", None, None)


if __name__ == "__main__":
    unittest.main()
