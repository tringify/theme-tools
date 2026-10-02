import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEME_CLI = ROOT / "theme.py"


class ThemeCliTest(unittest.TestCase):
    def run_cli(self, *args: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(THEME_CLI), *args]
        merged = os.environ.copy() if env is None else env
        return subprocess.run(
            command,
            cwd=cwd or ROOT,
            env=merged,
            capture_output=True,
            text=True,
            check=False,
        )

    def make_theme(self, root: Path) -> None:
        for directory in ("sections", "src/sections/hero", "templates"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        (root / "src/_shared.css").write_text("html { color: black; }\n", encoding="utf-8")
        (root / "src/sections/hero/body.html").write_text("<section>Hero</section>\n", encoding="utf-8")
        (root / "src/sections/hero/style.css").write_text("section { display: block; }\n", encoding="utf-8")
        (root / "src/sections/hero/schema.json").write_text(
            json.dumps({"name": "hero", "kind": "section"}),
            encoding="utf-8",
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

    def make_contract_checker(self, root: Path, *, valid: bool = True) -> Path:
        checker = root / "themecheck-contract"
        payload = (
            '{"schema_version":3,"ctx_needs":["cart","shop"],"setting_types":["text"],'
            '"hosted_actions":[{"kind":"cart_add","path":"/cart/add"}],'
            '"ctx":{"schema_version":1,"roots":[{"name":"cart"},{"name":"shop"}],"definitions":{}}}'
            if valid
            else '{"schema_version":3,"ctx_needs":"cart"}'
        )
        checker.write_text(
            "#!/usr/bin/env python3\nimport sys\nassert sys.argv[1:] == ['-contract']\nprint(" + repr(payload) + ")\n",
            encoding="utf-8",
        )
        checker.chmod(0o755)
        return checker

    def test_build_check_and_package_subcommands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            theme_root = Path(directory)
            self.make_theme(theme_root)
            checker = self.make_checker(theme_root)

            build = self.run_cli("build", str(theme_root))
            self.assertEqual(build.returncode, 0, build.stderr)
            self.assertIn("built 1 sections: hero", build.stdout)

            check = self.run_cli(
                "check",
                str(theme_root),
                "--checker",
                str(checker),
            )
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertIn("theme validation passed: 1 source sections", check.stdout)

            output = theme_root / "dist/theme.zip"
            package = self.run_cli(
                "package",
                str(theme_root),
                str(output),
                "--checker",
                str(checker),
            )
            self.assertEqual(package.returncode, 0, package.stderr)
            self.assertIn(f"packaged ", package.stdout)
            self.assertIn(str(output.resolve()), package.stdout)
            with zipfile.ZipFile(output) as archive:
                self.assertIn("sections/hero.vasc", archive.namelist())

    def test_contract_prints_the_canonical_machine_readable_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checker = self.make_contract_checker(Path(directory))
            result = self.run_cli("contract", "--checker", str(checker))
            self.assertEqual(result.returncode, 0, result.stderr)
            contract = json.loads(result.stdout)
            self.assertEqual(contract["ctx_needs"], ["cart", "shop"])
            self.assertEqual(contract["hosted_actions"][0]["kind"], "cart_add")
            self.assertEqual(contract["ctx"]["roots"][0]["name"], "cart")

    def test_contract_rejects_an_invalid_checker_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checker = self.make_contract_checker(Path(directory), valid=False)
            result = self.run_cli("contract", "--checker", str(checker))
            self.assertEqual(result.returncode, 1)
            self.assertIn("invalid author contract", result.stderr)
            self.assertNotIn("Traceback", result.stderr + result.stdout)

    def test_package_accepts_output_only_with_default_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            theme_root = Path(directory)
            self.make_theme(theme_root)
            build = self.run_cli("build", str(theme_root))
            self.assertEqual(build.returncode, 0, build.stderr)
            checker = self.make_checker(theme_root)
            output = theme_root / "dist/theme.zip"

            package = self.run_cli(
                "package",
                "dist/theme.zip",
                "--checker",
                str(checker),
                cwd=theme_root,
            )
            self.assertEqual(package.returncode, 0, package.stderr)
            self.assertTrue(output.is_file())

    def test_missing_checker_prints_actionable_error_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            theme_root = Path(directory)
            self.make_theme(theme_root)
            build = self.run_cli("build", str(theme_root))
            self.assertEqual(build.returncode, 0, build.stderr)

            env = {key: value for key, value in os.environ.items() if key != "TRINGIFY_THEME_CHECK"}
            check = self.run_cli("check", str(theme_root), env={**env, "PATH": ""})
            self.assertEqual(check.returncode, 1)
            self.assertIn("themecheck is required", check.stderr)
            self.assertNotIn("Traceback", check.stderr + check.stdout)

    def test_build_failure_is_concise(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            theme_root = Path(directory)
            result = self.run_cli("build", str(theme_root))
            self.assertEqual(result.returncode, 1)
            self.assertIn("theme build failed:", result.stderr)
            self.assertNotIn("Traceback", result.stderr + result.stdout)

    def test_package_rejects_extra_paths(self) -> None:
        result = self.run_cli("package", ".", "dist/a.zip", "dist/b.zip")
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected OUTPUT or THEME_ROOT OUTPUT", result.stderr)
        self.assertNotIn("Traceback", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
