#!/bin/bash
# Build ASCENT and install it into /Applications.
set -euo pipefail
cd "$(dirname "$0")"

./build.sh

TARGET="/Applications/ASCENT.app"
echo "==> Installing to $TARGET"
if [ -d "$TARGET" ]; then
    echo "  - removing the previous version"
    rm -rf "$TARGET"
fi
cp -R dist/ASCENT.app "$TARGET"
touch "$TARGET"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$TARGET" >/dev/null 2>&1 || true

echo "==> Installed."
echo "    Open it from Launchpad or Applications."
echo "    The first launch builds its Python environment (about a minute)."
