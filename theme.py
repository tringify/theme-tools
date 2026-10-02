#!/usr/bin/env python3
"""Create, build, check, and package Tringify themes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from build import build
from initialize import initialize
from package import package
from validate import author_contract, validate


def _run_preview(args: argparse.Namespace) -> None:
    from preview import serve

    try:
        serve(Path(args.root), args.host, args.port, args.renderer, args.checker, args.preset)
    except (OSError, ValueError) as exc:
        print(f"theme preview failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


def _run_init(source: Path, destination: Path, name: str, checker: str | None) -> None:
    try:
        initialize(source, destination, name, checker)
    except (OSError, ValueError) as exc:
        print(f"theme initialization failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    print(f"Created {name.strip()}: {destination.resolve()}")
    print("Built and validated for import. Edit the source, then run build, check, or package.")


def _run_build(root: Path) -> None:
    try:
        names = build(root)
    except (OSError, ValueError) as exc:
        print(f"theme build failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    print(f"built {len(names)} sections: {', '.join(names)}")


def _run_check(root: Path, mode: str, checker: str | None) -> None:
    try:
        sections = validate(root, mode, checker)
    except (OSError, ValueError) as exc:
        print(f"theme validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    print(f"theme validation passed: {len(sections)} source sections")


def _run_contract(checker: str | None) -> None:
    try:
        contract = author_contract(checker)
    except (OSError, ValueError) as exc:
        print(f"theme contract failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(contract, indent=2, ensure_ascii=False))


def _run_context(args: argparse.Namespace) -> None:
    from context_data import inspect_context

    try:
        payload = inspect_context(
            Path(args.root), args.page, args.entity, args.preset, args.renderer, args.checker
        )
    except (OSError, ValueError) as exc:
        print(f"theme context failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _run_package(paths: list[str], mode: str, checker: str | None) -> None:
    if len(paths) == 1:
        root, output = Path("."), Path(paths[0])
    elif len(paths) == 2:
        root, output = Path(paths[0]), Path(paths[1])
    else:
        print(
            "theme packaging failed: expected OUTPUT or THEME_ROOT OUTPUT",
            file=sys.stderr,
        )
        raise SystemExit(1)
    try:
        count = package(root, output, mode, checker)
    except (OSError, ValueError) as exc:
        print(f"theme packaging failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    print(f"packaged {count} files: {output.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a validated theme from an existing local theme")
    init_parser.add_argument("destination", help="new directory to create (must not exist)")
    init_parser.add_argument("--from", dest="source", required=True, help="local theme source directory to start from")
    init_parser.add_argument("--name", required=True, help="display name for the new theme")
    init_parser.add_argument("--checker", default=None, help="path to themecheck (default: TRINGIFY_THEME_CHECK or PATH)")
    init_parser.set_defaults(handler=lambda args: _run_init(Path(args.source), Path(args.destination), args.name, args.checker))

    build_parser = subparsers.add_parser("build", help="compile src/sections into sections/*.vasc")
    build_parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="theme repository root (default: current directory)",
    )
    build_parser.set_defaults(
        handler=lambda args: _run_build(Path(args.root)),
    )

    check_parser = subparsers.add_parser(
        "check",
        help="validate existing compiled artifacts with the server theme gate",
    )
    check_parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="theme repository root (default: current directory)",
    )
    check_parser.add_argument(
        "--mode",
        choices=("sealed", "development"),
        default="sealed",
        help="themecheck mode (default: sealed)",
    )
    check_parser.add_argument(
        "--checker",
        default=None,
        help="path to themecheck (default: TRINGIFY_THEME_CHECK or PATH)",
    )
    check_parser.set_defaults(
        handler=lambda args: _run_check(Path(args.root), args.mode, args.checker),
    )

    contract_parser = subparsers.add_parser(
        "contract",
        help="print the exact CTX, editor-control, and hosted-action author contract",
    )
    contract_parser.add_argument(
        "--checker",
        default=None,
        help="path to themecheck (default: TRINGIFY_THEME_CHECK or PATH)",
    )
    contract_parser.set_defaults(handler=lambda args: _run_contract(args.checker))

    context_parser = subparsers.add_parser(
        "context",
        help="print the exact sample CTX for one preview page",
    )
    context_parser.add_argument("root", nargs="?", default=".")
    context_parser.add_argument("--page", default="home", help="template page type (default: home)")
    context_parser.add_argument("--entity", default="", help="product, collection, article, or page handle")
    context_parser.add_argument("--preset", default="", help="theme style preset name")
    context_parser.add_argument("--renderer", help="path to theme-preview-render")
    context_parser.add_argument("--checker", help="path to themecheck")
    context_parser.set_defaults(handler=_run_context)

    package_parser = subparsers.add_parser(
        "package",
        help="build a runtime archive in an isolated copy and publish it atomically",
    )
    package_parser.add_argument(
        "paths",
        nargs="+",
        metavar="path",
        help="OUTPUT, or THEME_ROOT OUTPUT",
    )
    package_parser.add_argument(
        "--mode",
        choices=("sealed", "development"),
        default="sealed",
        help="themecheck mode (default: sealed)",
    )
    package_parser.add_argument(
        "--checker",
        default=None,
        help="path to themecheck (default: TRINGIFY_THEME_CHECK or PATH)",
    )
    package_parser.set_defaults(
        handler=lambda args: _run_package(args.paths, args.mode, args.checker),
    )

    preview_parser = subparsers.add_parser("preview", help="watch source and preview with sample data")
    preview_parser.add_argument("root", nargs="?", default=".")
    preview_parser.add_argument("--host", default="127.0.0.1", help="specific IPv4 interface (default: local only)")
    preview_parser.add_argument("--port", type=int, default=9292)
    preview_parser.add_argument("--renderer", help="path to theme-preview-render")
    preview_parser.add_argument("--checker", help="path to themecheck")
    preview_parser.add_argument("--preset", default="", help="theme style preset name")
    preview_parser.set_defaults(handler=_run_preview)

    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
