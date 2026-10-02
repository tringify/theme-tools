#!/usr/bin/env python3
"""Build in isolation, validate, and atomically publish a runtime theme bundle."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path

from archive import BUNDLE_DIRECTORIES, BUNDLE_FILES, ds_store_ignore, write_archive
from build import build
from validate import check_archive


def package(root: Path, output: Path, mode: str = "sealed", checker: str | None = None) -> int:
    root = root.resolve()
    output = output.resolve()
    if output == root or (output.is_relative_to(root) and output.relative_to(root).parts[0] != "dist"):
        raise ValueError("outputs inside the source tree must be under dist/")
    with tempfile.TemporaryDirectory(prefix="tringify-theme-package-") as directory:
        staged = Path(directory) / "source"
        staged.mkdir()
        for name in (*BUNDLE_DIRECTORIES, "src", *BUNDLE_FILES):
            source = root / name
            if source.is_symlink():
                raise ValueError(f"theme source symlinks are not supported: {name}")
            if source.is_dir():
                shutil.copytree(source, staged / name, symlinks=True, ignore=ds_store_ignore)
            elif source.is_file():
                shutil.copy2(source, staged / name)
        if any(path.is_symlink() for path in staged.rglob("*")):
            raise ValueError("theme source symlinks are not supported")
        if (staged / "src" / "sections").is_dir():
            build(staged)
        archive = Path(directory) / "theme.zip"
        count = write_archive(staged, archive)
        check_archive(archive, mode, checker)
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".theme-", suffix=".zip", dir=output.parent)
        os.close(descriptor)
        try:
            shutil.copyfile(archive, temporary)
            os.chmod(temporary, 0o644)
            os.replace(temporary, output)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("theme_root")
    parser.add_argument("output")
    parser.add_argument("--mode", choices=("sealed", "development"), default="sealed")
    args = parser.parse_args()
    try:
        count = package(Path(args.theme_root), Path(args.output), args.mode)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"theme packaging failed: {exc}\n")
    print(f"packaged {count} files: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
