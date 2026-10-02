#!/usr/bin/env python3
"""Validate a runtime archive with the same theme gate used by the server."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from archive import write_archive


def checker_executable(checker: str | None = None) -> str:
    executable = checker or os.environ.get("TRINGIFY_THEME_CHECK") or shutil.which("themecheck")
    if not executable:
        sibling = Path(__file__).with_name("themecheck.exe" if os.name == "nt" else "themecheck")
        if sibling.is_file():
            executable = str(sibling)
    if not executable:
        raise ValueError("themecheck is required: set TRINGIFY_THEME_CHECK or install themecheck on PATH")
    return str(executable)


def author_contract(checker: str | None = None) -> dict:
    result = subprocess.run(
        [checker_executable(checker), "-contract"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError((result.stdout + result.stderr).strip() or "themecheck failed")
    try:
        contract = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("themecheck returned an invalid author contract") from exc
    required = ("schema_version", "ctx_needs", "setting_types", "hosted_actions")
    ctx = contract.get("ctx") if isinstance(contract, dict) else None
    roots = ctx.get("roots") if isinstance(ctx, dict) else None
    definitions = ctx.get("definitions") if isinstance(ctx, dict) else None
    root_names = [root.get("name") for root in roots] if isinstance(roots, list) and all(
        isinstance(root, dict) for root in roots
    ) else None
    if (
        not isinstance(contract, dict)
        or contract.get("schema_version") != 3
        or any(not isinstance(contract.get(key), list) for key in required[1:])
        or not isinstance(ctx, dict)
        or ctx.get("schema_version") != 1
        or not isinstance(definitions, dict)
        or root_names != contract.get("ctx_needs")
    ):
        raise ValueError("themecheck returned an invalid author contract")
    return contract


def check_archive(path: Path, mode: str = "sealed", checker: str | None = None) -> str:
    result = subprocess.run(
        [checker_executable(checker), "-json", "-mode", mode, str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError(checker_failure(result.stdout, result.stderr))
    return result.stdout


def checker_failure(stdout: str, stderr: str) -> str:
    """Keep the checker's machine-readable result readable in author commands."""
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return (stdout + stderr).strip() or "themecheck failed"
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), str):
        return (stdout + stderr).strip() or "themecheck failed"
    message = payload["error"]
    if payload.get("code"):
        message += f" ({payload['code']})"
    details = payload.get("details")
    if isinstance(details, dict):
        for key, value in details.items():
            if value is None or value == "":
                continue
            label = str(key).replace("_", " ").capitalize()
            text = json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else str(value)
            message += f"\n  {label}: {text}"
    elif details:
        message += f"\n  {details}"
    return message


def validate(root: Path, mode: str = "sealed", checker: str | None = None) -> list[str]:
    root = root.resolve()
    with tempfile.TemporaryDirectory(prefix="tringify-theme-check-") as directory:
        archive = Path(directory) / "theme.zip"
        write_archive(root, archive)
        check_archive(archive, mode, checker)
    return sorted(path.stem for path in (root / "sections").glob("*.vasc"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("theme_root", nargs="?", default=".")
    parser.add_argument("--mode", choices=("sealed", "development"), default="sealed")
    try:
        args = parser.parse_args()
        sections = validate(Path(args.theme_root), args.mode)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"theme validation failed: {exc}\n")
    print(f"theme validation passed: {len(sections)} source sections")


if __name__ == "__main__":
    main()
