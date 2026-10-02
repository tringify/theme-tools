"""Create an editable theme from a local source without running template code."""

from __future__ import annotations

import json
import shutil
import stat
import tempfile
from pathlib import Path

from archive import BUNDLE_DIRECTORIES, BUNDLE_FILES, is_ds_store, write_archive
from build import build
from validate import check_archive


MAX_SOURCE_FILES = 2000
MAX_SOURCE_BYTES = 100 * 1024 * 1024
SOURCE_PARTS = {"body.html", "style.css", "schema.json"}


def _source_files(root: Path) -> list[Path]:
    files: list[Path] = []

    def collect(path: Path) -> None:
        if path.is_symlink():
            raise ValueError(f"theme source symlinks are not supported: {path.relative_to(root)}")
        mode = path.stat().st_mode
        if stat.S_ISDIR(mode):
            for child in sorted(path.iterdir()):
                collect(child)
        elif stat.S_ISREG(mode):
            if is_ds_store(path):
                return
            files.append(path)
            if len(files) > MAX_SOURCE_FILES:
                raise ValueError("theme source exceeds the 2000-file initialization limit")
        else:
            raise ValueError(f"theme source must contain regular files: {path.relative_to(root)}")

    for name in (*BUNDLE_DIRECTORIES, *BUNDLE_FILES, "src"):
        path = root / name
        if path.exists() or path.is_symlink():
            collect(path)
    for path in sorted(root.iterdir()):
        if path.name in ("README.md", "NOTICE", "LICENSE") or path.name.startswith(("LICENSE.", "NOTICE.")):
            collect(path)

    for path in files:
        parts = path.relative_to(root).parts
        if parts[0] == "src" and not (
            parts in (("src", "_shared.css"), ("src", ".generated-sections.json"))
            or (len(parts) == 4 and parts[1] == "sections" and parts[3] in SOURCE_PARTS)
        ):
            raise ValueError(f"unsupported editable source file: {path.relative_to(root)}")
    if sum(path.stat().st_size for path in files) > MAX_SOURCE_BYTES:
        raise ValueError("theme source exceeds the 100 MiB initialization limit")
    return files


def initialize(source: Path, destination: Path, name: str, checker: str | None = None) -> int:
    name = name.strip()
    if not 1 <= len(name) <= 100 or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError("theme name must be 1–100 characters without control characters")
    if source.is_symlink() or not source.is_dir():
        raise ValueError("source must be a local theme directory, not a symlink")
    source = source.resolve()
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("destination already exists; choose a new directory")
    if not destination.parent.is_dir():
        raise ValueError("destination parent directory must already exist")
    destination = destination.parent.resolve() / destination.name
    if destination.is_relative_to(source):
        raise ValueError("destination must be outside the source theme")

    files = _source_files(source)
    with tempfile.TemporaryDirectory(prefix=".tringify-theme-init-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "theme"
        staged.mkdir()
        for path in files:
            output = staged / path.relative_to(source)
            output.parent.mkdir(parents=True, exist_ok=True)
            # Copy bytes only. A source executable never becomes an executable hook.
            output.write_bytes(path.read_bytes())
            output.chmod(0o644)
        manifest_path = staged / "theme.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("theme.json must contain an object")
        manifest.update(name=name, status="draft")
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        if (staged / "src" / "sections").is_dir():
            build(staged)
        archive = Path(temporary) / "theme.zip"
        write_archive(staged, archive)
        check_archive(archive, "sealed", checker)
        section_count = len(json.loads(manifest_path.read_text(encoding="utf-8")).get("sections", []))
        (staged / ".gitignore").write_text("dist/\n.DS_Store\n__pycache__/\n.env\n.env.*\n", encoding="utf-8")

        # Reserve the destination exclusively after validation. Unlike rename(),
        # mkdir() cannot replace an empty directory created by someone else.
        destination.mkdir()
        try:
            for child in staged.iterdir():
                child.rename(destination / child.name)
        except OSError:
            shutil.rmtree(destination)
            raise
        return section_count
