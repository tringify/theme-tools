# Tringify theme tools

Command-line tools for building Tringify storefront themes. Create a theme from the [starter theme](https://github.com/tringify/theme-starter), preview it locally with sample content, validate it, and package it for upload in the Tringify Developer Portal.

New to Tringify themes? Follow [Build your first theme](https://dev-docs.tringify.com/themes/build-your-first-theme).

## Install

Python 3.10 or newer is required.

macOS and Linux:

```sh
curl -fsSL https://raw.githubusercontent.com/tringify/theme-tools/main/install.sh | sh
```

The script downloads the release for your platform, verifies its SHA-256 checksum, installs it in `~/.tringify/theme-tools`, and adds a `tringify-theme` command to `~/.local/bin`. Set `TRINGIFY_THEME_TOOLS_VERSION` to install a specific release tag.

Windows (PowerShell):

```powershell
irm https://raw.githubusercontent.com/tringify/theme-tools/main/install.ps1 | iex
```

This installs in `%LOCALAPPDATA%\Tringify\theme-tools` and adds that directory to your user `PATH`.

To install manually, download the archive for your platform from [Releases](https://github.com/tringify/theme-tools/releases), check it against `SHA256SUMS`, unzip it, and run `tringify-theme` (or `tringify-theme.cmd` on Windows) from the extracted directory. On macOS, an archive downloaded with a browser may need `xattr -dr com.apple.quarantine tringify-theme-tools` before its binaries can run.

Releases are available for macOS (Apple silicon and Intel), Linux (x86-64 and ARM64), and Windows (x86-64). Each archive contains the command-line source from this repository and two platform binaries: `themecheck`, the theme validator, and `theme-preview-render`, the local preview renderer.

## Quick start

```sh
git clone https://github.com/tringify/theme-starter
tringify-theme init my-theme --from theme-starter --name "My Theme"
cd my-theme
tringify-theme preview
```

Open the printed URL, edit a section under `src/sections/`, and the preview rebuilds. When you are ready to upload:

```sh
tringify-theme check
tringify-theme package dist/my-theme.zip
```

Upload the ZIP in the Developer Portal under **Themes**, install it on a development store, and test it with that store's products before publishing.

## Commands

Every command prints a concise message and exits non-zero on failure. `ROOT` defaults to the current directory.

| Command | What it does |
| --- | --- |
| `init DESTINATION --from SOURCE --name NAME` | Creates a new theme from a local theme directory, such as the starter theme. |
| `build [ROOT]` | Compiles `src/sections/<name>` into `sections/<name>.vasc` and updates the section index in `theme.json`. |
| `preview [ROOT]` | Serves a live preview with sample content and rebuilds when source files change. |
| `check [ROOT]` | Validates the compiled theme with the same rules used when a theme is uploaded. |
| `package [ROOT] OUTPUT` | Builds, validates, and writes an upload-ready ZIP. |
| `contract` | Prints the theme author contract as JSON. |
| `context [ROOT] --page PAGE` | Prints the sample data a page receives in the preview. |

### init

```sh
tringify-theme init DESTINATION --from SOURCE --name NAME
```

Copies a local theme into a new directory, sets its display name, builds the section sources, and validates the result. `DESTINATION` must not exist and must be outside the source theme. `NAME` must be 1–100 characters. The source is never modified, and nothing is created if validation fails.

`init` works offline. It keeps `README.md`, `LICENSE`, and `NOTICE` files, and leaves out Git history, dependencies, environment files, and previous build archives. Symlinks, unsupported source files, more than 2,000 files, or more than 100 MiB of source are rejected.

### build

```sh
tringify-theme build [ROOT]
```

Compiles each `src/sections/<name>/` directory into `sections/<name>.vasc` and updates the section entries in `theme.json`. It does not change surface permissions or templates; update those when you rename or remove a section.

### preview

```sh
tringify-theme preview [ROOT] [--port 9292] [--preset NAME] [--host ADDRESS]
```

Starts a local preview at `127.0.0.1:9292`. Choose a page and switch between desktop and mobile widths. The preview rebuilds in a temporary copy when sections, templates, settings, translations, assets, or demo content change. A failed edit shows the error and keeps the last successful page. Use `--preset` to preview a style preset.

The preview uses the theme's `demo/catalog.json`. Without a demo pack it supplies sample products, a cart, collections, categories, vendors, brands, an article, and an About page in English and USD.

Forms, sign-in, cart changes, checkout, and network requests from theme scripts are disabled in the preview. Test those on a development store.

To open the preview from another device on a trusted network, pass the computer's LAN address with `--host`. Stop the server with Ctrl+C.

### check

```sh
tringify-theme check [ROOT] [--mode sealed|development]
```

Validates the compiled theme without rebuilding it. Errors name the affected file and the reason. Fix the source under `src/`, run `build`, then run `check` again. `--mode` defaults to `sealed`, which applies upload rules.

### package

```sh
tringify-theme package [ROOT] OUTPUT
```

Rebuilds the section sources in a temporary copy, validates the theme, and writes `OUTPUT` atomically. A failed validation never replaces an existing package. Outputs inside the theme must be under `dist/`. Packages are deterministic and leave out editable sources and repository files.

### contract

```sh
tringify-theme contract
```

Prints the versioned author contract: every `ctx_needs` root and its fields, value types, editor setting and resource picker types, nesting limits, the demo schema version, and the hosted form actions a theme can use.

### context

```sh
tringify-theme context . --page product --entity ceramic-mug
tringify-theme context . --page collection --preset "Soft Neutral"
```

Prints the exact sample data the preview gives a page, validated against the contract. Pages include `home`, `product`, `collection`, `category`, `vendor`, `brand`, `blog`, and `page`. Omit `--entity` to use the first matching record in the demo pack.

## Binary locations

The commands look for `themecheck` and `theme-preview-render` in this order: the `--checker` or `--renderer` option, the `TRINGIFY_THEME_CHECK` or `TRINGIFY_THEME_PREVIEW` environment variable, your `PATH`, then the directory containing `theme.py`.

## Theme source

Edit sections in `src/sections/<name>/` as `body.html`, `style.css`, and `schema.json`, with shared styles in `src/_shared.css`, or write `sections/*.vasc` files directly. A package is assembled from `assets`, `blocks`, `config`, `demo`, `locales`, `sections`, and `templates`, plus `theme.json` and `tokens.json`.

Keep `src/.generated-sections.json` in version control. It records which section files the builder generated, so removing a source section also removes its output safely.

## Documentation

- [Build your first theme](https://dev-docs.tringify.com/themes/build-your-first-theme)
- [Theme development](https://dev-docs.tringify.com/themes/)
- [Theme package structure](https://dev-docs.tringify.com/themes/theme-package-structure)
- [Demo content](https://dev-docs.tringify.com/themes/demo-content)
- [Vascula template language](https://vascula.dev)

## Development

Run the tests with:

```sh
python3 -m unittest discover -s tests
```

## License

The source in this repository is available under the [MIT License](LICENSE).
