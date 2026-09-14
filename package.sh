#!/bin/bash
# Build a drag-to-Applications disk image: dist/ASCENT-<version>.dmg
#
# The window is styled rather than left as Finder's default two icons on grey.
# That means building a *writable* image first, telling Finder how to show it,
# and compressing only afterwards: the view settings live in the volume's
# .DS_Store, which cannot be written to a read-only image.
set -euo pipefail
cd "$(dirname "$0")"

VERSION=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" macos/Info.plist)
VOLUME="ASCENT ${VERSION}"
DMG="dist/ASCENT-${VERSION}.dmg"
STAGE="dist/dmg-stage"
RW="dist/dmg-rw.dmg"
MOUNT="dist/dmg-mount"

# Window geometry, in points. macos/dmg_background.py generates the backdrop at
# exactly these dimensions, and again at 2x - change one and regenerate.
WIN_W=640
WIN_H=420
# Finder's window `bounds` include the title bar, so asking for WIN_H gives a
# content area WIN_H minus this - measured at 33pt - and the bottom of the
# backdrop is silently cropped. The artwork keeps a clear strip at the foot as
# well, so a different title bar on a future macOS costs nothing.
TITLE_BAR=33
ICON_SIZE=96
APP_X=170;  APP_Y=196
DEST_X=470; DEST_Y=196

./build.sh

echo "==> Packaging $DMG"
rm -rf "$STAGE" "$MOUNT" "$RW"
[ -f "$DMG" ] && rm -f "$DMG"
mkdir -p "$STAGE"
cp -R dist/ASCENT.app "$STAGE/ASCENT.app"
ln -s /Applications "$STAGE/Applications"

# The backdrop, as a multi-resolution TIFF so the window is sharp on Retina.
# A lone 1x PNG is visibly soft; a lone 2x PNG gets drawn at double size.
if [ -f macos/dmg-background.png ] && [ -f "macos/dmg-background@2x.png" ]; then
    mkdir -p "$STAGE/.background"
    tiffutil -cathidpicheck macos/dmg-background.png \
        "macos/dmg-background@2x.png" \
        -out "$STAGE/.background/background.tiff" >/dev/null
    echo "  - backdrop: 1x + 2x"
else
    echo "  - WARNING: no backdrop found, window will be plain"
fi

# Content plus slack for the .DS_Store Finder is about to write. Without the
# headroom the styling fails with "no space left on device" and the image still
# builds, just plain - which is the confusing kind of failure.
SIZE_MB=$(( $(du -sm "$STAGE" | cut -f1) + 25 ))
hdiutil create -volname "$VOLUME" -srcfolder "$STAGE" -fs HFS+ \
    -size "${SIZE_MB}m" -ov -format UDRW "$RW" >/dev/null

# Two things about this mount are load-bearing, both learned the hard way.
#
# Under /Volumes, not a mountpoint of our choosing: Finder resolves the
# background file against the real volume and fails with -10006 otherwise.
#
# And *without* -nobrowse. With it, Finder never treats the volume as properly
# mounted, so it accepts every styling command, reports no error, and never
# writes .DS_Store - the image builds clean and opens completely unstyled.
MOUNT=$(hdiutil attach "$RW" -noautoopen \
        | grep -oE '/Volumes/.*$' | head -1)
[ -n "$MOUNT" ] || { echo "ERROR: could not mount $RW"; exit 1; }

echo "  - arranging the window"
# Finder addresses the volume by name, not by our mountpoint path.
osascript >/dev/null <<APPLESCRIPT || echo "    WARNING: Finder styling failed; image is still valid"
tell application "Finder"
    tell disk "${VOLUME}"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set the bounds of container window to {240, 140, $((240 + WIN_W)), $((140 + WIN_H + TITLE_BAR))}
        set opts to the icon view options of container window
        set arrangement of opts to not arranged
        set icon size of opts to ${ICON_SIZE}
        set text size of opts to 12
        set label position of opts to bottom
        -- An absolute POSIX path. The "file .background:background.tiff" form
        -- that most DMG scripts use fails here with -10006.
        set background picture of opts to POSIX file "${MOUNT}/.background/background.tiff"
        set position of item "ASCENT.app" of container window to {${APP_X}, ${APP_Y}}
        set position of item "Applications" of container window to {${DEST_X}, ${DEST_Y}}
        -- Close and reopen so the settings are flushed to .DS_Store.
        close
        open
        update without registering applications
        delay 3
    end tell
end tell
APPLESCRIPT

# .DS_Store is written lazily; without the close and the sync the styling is
# lost on detach. 10KB or so should exist by now - say so if it does not,
# rather than shipping a plain window and calling it done.
osascript -e "tell application \"Finder\" to close every window whose name contains \"${VOLUME}\"" >/dev/null 2>&1 || true

# The volume's own icon, written after the styling rather than staged before
# it: a .VolumeIcon.icns present while Finder has the volume open gets
# consumed and the file disappears from the finished image.
if [ -f macos/AppIcon.icns ]; then
    cp macos/AppIcon.icns "$MOUNT/.VolumeIcon.icns"
    SetFile -a C "$MOUNT" 2>/dev/null || true
fi

sync
sleep 1
if [ -s "$MOUNT/.DS_Store" ]; then
    echo "  - window settings written ($(stat -f%z "$MOUNT/.DS_Store") bytes)"
else
    echo "    WARNING: no .DS_Store - the window will open unstyled"
fi
hdiutil detach "$MOUNT" >/dev/null 2>&1 || hdiutil detach "$MOUNT" -force >/dev/null

hdiutil convert "$RW" -format UDZO -imagekey zlib-level=9 -o "$DMG" >/dev/null
rm -rf "$STAGE" "$RW"

echo "==> Done: $DMG"
echo "    Open it and drag ASCENT into Applications."
