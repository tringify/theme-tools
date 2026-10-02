#!/usr/bin/env python3
"""Compile editable theme section sources into standalone Vascula sections."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

# Template sources are Vascula files.
SOURCE_EXT = ".vasc"


def read_json(path: Path, root: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.relative_to(root)}:{exc.lineno}:{exc.colno}: {exc.msg}") from None


def build(root: Path) -> list[str]:
    root = root.resolve()
    source_root = root / "src" / "sections"
    output_root = root / "sections"
    for name in ("src", "src/sections", "src/_shared.css", "src/.generated-sections.json", "sections", "theme.json"):
        if (root / name).is_symlink():
            raise ValueError(f"theme source symlinks are not supported: {name}")
    shared_css = (root / "src" / "_shared.css").read_text(encoding="utf-8")
    manifest_path = root / "theme.json"
    manifest = read_json(manifest_path, root)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("sections", []), list):
        raise ValueError("theme.json must contain a sections list")
    entries = manifest.get("sections", [])
    if any(not isinstance(entry, dict) or not isinstance(entry.get("name"), str) for entry in entries):
        raise ValueError("theme.json sections must be named objects")
    if len({entry["name"] for entry in entries}) != len(entries):
        raise ValueError("theme.json contains duplicate section names")
    index = {entry["name"]: entry for entry in entries}
    ownership_path = root / "src" / ".generated-sections.json"
    previous = {}
    if ownership_path.exists():
        state = read_json(ownership_path, root)
        if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("sections"), dict):
            raise ValueError("invalid generated-section ownership file")
        previous = state["sections"]
        for name, digest in previous.items():
            if not name or name in (".", "..") or "/" in name or "\\" in name or not isinstance(digest, str):
                raise ValueError("invalid generated-section ownership entry")

    built: list[str] = []
    outputs: dict[str, str] = {}
    generated_entries = []
    for source_dir in sorted(path for path in source_root.iterdir() if path.is_dir()):
        name = source_dir.name
        if source_dir.is_symlink() or any((source_dir / part).is_symlink() for part in ("body.html", "style.css", "schema.json")):
            raise ValueError(f"theme source symlinks are not supported: {name}")
        body = (source_dir / "body.html").read_text(encoding="utf-8").strip()
        style = (source_dir / "style.css").read_text(encoding="utf-8").strip()
        schema = read_json(source_dir / "schema.json", root)
        if not isinstance(schema, dict):
            raise ValueError(f"{name}: schema must be an object")
        if schema.get("name") != name:
            raise ValueError(f"{name}: schema name must match the section directory")
        source = (
            f"<style>\n{shared_css}\n{style}\n</style>\n{body}\n"
            f"{{% schema %}}\n{json.dumps(schema, indent=2)}\n{{% endschema %}}\n"
        )
        outputs[name] = source
        entry = dict(index.get(name, {}))
        entry.update(name=name, kind=schema.get("kind", "section"), file=f"sections/{name}{SOURCE_EXT}", origin="override")
        if schema.get("target"):
            entry["target"] = schema["target"]
        else:
            entry.pop("target", None)
        generated_entries.append(entry)
        built.append(name)

    stale = set(previous) - set(outputs)
    for name in set(outputs) | stale:
        if (output_root / f"{name}{SOURCE_EXT}").is_symlink():
            raise ValueError(f"theme output symlinks are not supported: {name}")
    for name in stale:
        path = output_root / f"{name}{SOURCE_EXT}"
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != previous[name]:
            raise ValueError(f"{name}: previously generated section was edited; reconcile it before removing its source")
    output_root.mkdir(parents=True, exist_ok=True)
    for name, source in outputs.items():
        (output_root / f"{name}{SOURCE_EXT}").write_text(source, encoding="utf-8")
    for name in stale:
        (output_root / f"{name}{SOURCE_EXT}").unlink(missing_ok=True)
    preserved = [entry for entry in entries if entry["name"] not in outputs and entry["name"] not in stale]
    manifest["sections"] = preserved + generated_entries
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    ownership_path.write_text(json.dumps({"version": 1, "sections": {
        name: hashlib.sha256(body.encode("utf-8")).hexdigest() for name, body in outputs.items()
    }}, indent=2) + "\n", encoding="utf-8")
    return built


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "theme_root",
        nargs="?",
        default=os.environ.get("THEME_ROOT", "."),
        help="theme repository root (default: THEME_ROOT or current directory)",
    )
    names = build(Path(parser.parse_args().theme_root))
    print(f"built {len(names)} sections: {', '.join(names)}")


if __name__ == "__main__":
    main()
