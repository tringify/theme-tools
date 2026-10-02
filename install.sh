#!/bin/sh
# Install the Tringify theme tools on macOS or Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/tringify/theme-tools/main/install.sh | sh
#
# Environment:
#   TRINGIFY_THEME_TOOLS_VERSION  release tag to install (default: latest)
#   TRINGIFY_THEME_TOOLS_HOME     installation directory (default: ~/.tringify/theme-tools)
#   TRINGIFY_THEME_TOOLS_BIN      directory for the tringify-theme command (default: ~/.local/bin)
set -eu

repo="tringify/theme-tools"
version="${TRINGIFY_THEME_TOOLS_VERSION:-latest}"
home_dir="${TRINGIFY_THEME_TOOLS_HOME:-$HOME/.tringify/theme-tools}"
bin_dir="${TRINGIFY_THEME_TOOLS_BIN:-$HOME/.local/bin}"

fail() { echo "tringify-theme install: $*" >&2; exit 1; }

case "$(uname -s)" in
  Darwin) os=darwin ;;
  Linux) os=linux ;;
  *) fail "unsupported operating system $(uname -s); on Windows use install.ps1" ;;
esac
case "$(uname -m)" in
  x86_64|amd64) arch=amd64 ;;
  arm64|aarch64) arch=arm64 ;;
  *) fail "unsupported architecture $(uname -m)" ;;
esac
platform="$os-$arch"

python=""
for candidate in python3 python3.13 python3.12 python3.11 python3.10; do
  if command -v "$candidate" >/dev/null 2>&1 &&
    "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    python="$(command -v "$candidate")"
    break
  fi
done
[ -n "$python" ] || fail "Python 3.10 or newer is required"
command -v curl >/dev/null 2>&1 || fail "curl is required"
command -v unzip >/dev/null 2>&1 || fail "unzip is required"

if [ "$version" = latest ]; then
  base="https://github.com/$repo/releases/latest/download"
else
  base="https://github.com/$repo/releases/download/$version"
fi
archive="tringify-theme-tools-$platform.zip"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT INT TERM

echo "Downloading $archive ($version)"
curl -fsSL "$base/$archive" -o "$work/$archive" || fail "download failed: $base/$archive"
curl -fsSL "$base/SHA256SUMS" -o "$work/SHA256SUMS" || fail "download failed: $base/SHA256SUMS"

expected="$(awk -v name="$archive" '$2 == name || $2 == "*" name { print $1 }' "$work/SHA256SUMS")"
[ -n "$expected" ] || fail "no checksum published for $archive"
if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "$work/$archive" | awk '{print $1}')"
else
  actual="$(shasum -a 256 "$work/$archive" | awk '{print $1}')"
fi
[ "$expected" = "$actual" ] || fail "checksum mismatch for $archive"

unzip -q "$work/$archive" -d "$work/extract"
[ -f "$work/extract/tringify-theme-tools/theme.py" ] || fail "unexpected archive layout"

mkdir -p "$(dirname "$home_dir")" "$bin_dir"
rm -rf "$home_dir.new"
mv "$work/extract/tringify-theme-tools" "$home_dir.new"
rm -rf "$home_dir"
mv "$home_dir.new" "$home_dir"
chmod 0755 "$home_dir/themecheck" "$home_dir/theme-preview-render"

cat > "$bin_dir/tringify-theme" <<WRAPPER
#!/bin/sh
exec "$python" "$home_dir/theme.py" "\$@"
WRAPPER
chmod 0755 "$bin_dir/tringify-theme"

echo "Installed $(cat "$home_dir/VERSION" 2>/dev/null || echo "$version") to $home_dir"
case ":$PATH:" in
  *":$bin_dir:"*) echo "Run: tringify-theme --help" ;;
  *) echo "Add $bin_dir to your PATH, then run: tringify-theme --help" ;;
esac
