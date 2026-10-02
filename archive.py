"""Write the deterministic runtime archive consumed by the theme importer."""

from __future__ import annotations

import zipfile
from pathlib import Path


BUNDLE_DIRECTORIES = ("assets", "blocks", "config", "demo", "locales", "sections", "templates")
BUNDLE_FILES = ("theme.json", "tokens.json")
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
DS_STORE_NAME = ".DS_Store"


def is_ds_store(path: Path) -> bool:
    return path.name == DS_STORE_NAME and not path.is_symlink() and path.is_file()


def ds_store_ignore(directory: str, names: list[str]) -> list[str]:
    return [name for name in names if is_ds_store(Path(directory) / name)]


def bundle_paths(root: Path) -> list[Path]:
    missing = [name for name in BUNDLE_FILES if not (root / name).is_file()]
    if missing:
        raise ValueError(f"missing runtime bundle file: {', '.join(missing)}")

    paths: list[Path] = []
    for directory in BUNDLE_DIRECTORIES:
        base = root / directory
        if base.is_dir():
            paths.extend(path for path in base.rglob("*") if path.is_file() and not is_ds_store(path))
    paths.extend(root / filename for filename in BUNDLE_FILES)
    return sorted(set(paths), key=lambda path: path.relative_to(root).as_posix())


def write_archive(root: Path, output: Path) -> int:
    root = root.resolve()
    paths = bundle_paths(root)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in paths:
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError(f"symlink outside package contract: {path}")
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(relative, ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return len(paths)
