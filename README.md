# Tringify theme tools

The theme validator and the preview renderer for Tringify storefront themes, published as releases for the [Tringify CLI](https://github.com/tringify/cli).

To build themes, install the CLI and use its `tringify theme` commands:

```sh
curl -fsSL https://raw.githubusercontent.com/tringify/cli/main/install.sh | sh
tringify theme init my-theme
cd my-theme
tringify theme preview
```

The CLI downloads the newest release from this repository the first time you check, package or preview a theme, verifies it against `SHA256SUMS`, and looks for a newer release at most every 15 minutes. New to Tringify themes? Follow [Build your first theme](https://dev-docs.tringify.com/themes/build-your-first-theme).

## Releases

Each release has one archive per platform: macOS (Apple silicon and Intel), Linux (x86-64 and ARM64) and Windows (x86-64, which also runs on Windows on Arm). An archive holds two programs:

- `themecheck`, the theme validator: the same rules a theme upload is checked with. `themecheck -json` gives the stable error `code` and structured `details` for scripts.
- `theme-preview-render`, the preview renderer: it renders a theme with sample content the way a store renders it.

The CLI uses them for you. To use a release other than the newest, set `TRINGIFY_THEME_TOOLS_VERSION`; to use copies you already have, set `TRINGIFY_THEME_CHECK` and `TRINGIFY_THEME_PREVIEW`.

## License

[MIT](LICENSE)
