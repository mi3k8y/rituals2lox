#!/bin/bash
# Usage: ./build.sh /path/to/plugin-source  [version]
# The plugin source folder must contain plugin.cfg at its root
# (plus bin/, webfrontend/, templates/, icons/, daemon/, etc.).
set -euo pipefail

SRC="${1:?path to plugin source folder}"
VER="${2:-$(grep -m1 '^VERSION=' "$SRC/plugin.cfg" | cut -d= -f2)}"
OUT="rituals2lox-v${VER}.zip"

[ -f "$SRC/plugin.cfg" ] || { echo "ERROR: plugin.cfg not at root of $SRC"; exit 1; }
for s in 64 128 256 512; do
  [ -f "$SRC/icons/icon_${s}.png" ] || echo "WARN: icons/icon_${s}.png missing"
done

# secrets check
if grep -rIniE '(password|token|secret|apikey)[[:space:]]*[=:][[:space:]]*["'\'']?[A-Za-z0-9._-]{12,}' "$SRC" \
     --exclude-dir=.git --exclude='*.md' >/dev/null; then
  echo "WARN: possible hard-coded credentials found - review before publishing:"
  grep -rIniE '(password|token|secret|apikey)[[:space:]]*[=:][[:space:]]*["'\'']?[A-Za-z0-9._-]{12,}' "$SRC" \
     --exclude-dir=.git --exclude='*.md' | head
fi

# non-ASCII check on Perl/shell sources (past encoding issues)
find "$SRC" -type f \( -name '*.pl' -o -name '*.cgi' -o -name '*.pm' -o -name '*.sh' \) \
  -exec grep -lP '[^\x00-\x7F]' {} \; | sed 's/^/WARN: non-ASCII: /' || true

rm -f "$OUT"
( cd "$SRC" && zip -qr "$OLDPWD/$OUT" . -x '.git/*' '.DS_Store' '*.zip' )
echo "Built $OUT"
unzip -l "$OUT" | grep -E ' plugin\.cfg$' || { echo "ERROR: plugin.cfg not at archive root"; exit 1; }
