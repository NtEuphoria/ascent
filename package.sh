#!/bin/bash
# Build a drag-to-Applications disk image: dist/ASCENT-<version>.dmg
set -euo pipefail
cd "$(dirname "$0")"

VERSION=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" macos/Info.plist)
DMG="dist/ASCENT-${VERSION}.dmg"
STAGE="dist/dmg-stage"

./build.sh

echo "==> Packaging $DMG"
[ -d "$STAGE" ] && rm -rf "$STAGE"
[ -f "$DMG" ] && rm -f "$DMG"
mkdir -p "$STAGE"
cp -R dist/ASCENT.app "$STAGE/ASCENT.app"
ln -s /Applications "$STAGE/Applications"

hdiutil create -volname "ASCENT ${VERSION}" -srcfolder "$STAGE" \
    -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"

echo "==> Done: $DMG"
echo "    Open it and drag ASCENT into Applications."
