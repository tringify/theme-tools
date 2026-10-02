"""Inspect the exact demo CTX produced by the bundled preview renderer."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from package import package
from preview import renderer_path


def inspect_context(
    root: Path,
    page: str,
    entity: str,
    preset: str,
    renderer: str | None,
    checker: str | None,
) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("theme root must be a directory")
    with tempfile.TemporaryDirectory(prefix="tringify-theme-context-") as directory:
        bundle = Path(directory) / "theme.zip"
        package(root, bundle, checker=checker)
        command = [
            renderer_path(renderer),
            "--bundle",
            str(bundle),
            "--context",
            "--page",
            page,
            "--base",
            "/preview",
        ]
        if entity:
            command.extend(("--entity", entity))
        if preset:
            command.extend(("--preset", preset))
        result = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    if result.returncode:
        raise ValueError((result.stderr or result.stdout).strip() or "theme context inspection failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("theme preview renderer returned invalid context JSON") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or payload.get("page") != page
        or not isinstance(payload.get("context"), dict)
    ):
        raise ValueError("theme preview renderer returned an invalid context result")
    return payload
