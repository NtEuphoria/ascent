#!/bin/bash
# Build ASCENT.app into dist/. Requires the Xcode Command Line Tools (swiftc).
set -euo pipefail
cd "$(dirname "$0")"

APP="dist/ASCENT.app"
echo "==> Building $APP"

command -v swiftc >/dev/null 2>&1 || {
    echo "ERROR: swiftc not found. Install Apple's developer tools:"
    echo "    xcode-select --install"
    exit 1
}

mkdir -p dist
[ -d "$APP" ] && rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/app"

echo "  - compiling the native window (Apple Silicon + Intel)"
mkdir -p dist/arch
swiftc -swift-version 5 -O -target arm64-apple-macos11 \
    -o dist/arch/ASCENT-arm64 macos/main.swift
if swiftc -swift-version 5 -O -target x86_64-apple-macos11 \
        -o dist/arch/ASCENT-x86_64 macos/main.swift 2>/dev/null; then
    lipo -create dist/arch/ASCENT-arm64 dist/arch/ASCENT-x86_64 \
        -output "$APP/Contents/MacOS/ASCENT"
    echo "    universal: $(lipo -archs "$APP/Contents/MacOS/ASCENT")"
else
    echo "    WARNING: Intel slice unavailable, building Apple Silicon only"
    cp dist/arch/ASCENT-arm64 "$APP/Contents/MacOS/ASCENT"
fi
rm -rf dist/arch

echo "  - copying the calculation engine into the bundle"
cp app.py requirements.txt "$APP/Contents/Resources/app/"
# Every top-level Python package, found rather than listed. The list used to
# be hardcoded as "calculators utils", so adding the studios package built an
# app that passed every test and then died on launch with
# ModuleNotFoundError - the dev server runs from the source tree and never
# notices what the bundle is missing.
PACKAGES=$(find . -maxdepth 2 -name '__init__.py' \
    -not -path './.venv/*' -not -path './dist/*' -not -path './build/*' \
    -not -path './tests/*' -not -path './plugins/*' \
    | xargs -n1 dirname | sed 's|^\./||' | sort -u)
if [ -z "$PACKAGES" ]; then
    echo "    ERROR: found no Python packages to bundle" >&2
    exit 1
fi
echo "    packages: $(echo $PACKAGES | tr '\n' ' ')"
cp -R $PACKAGES "$APP/Contents/Resources/app/"
# Non-package data the app reads at runtime. assets/ holds no __init__.py, so
# the package search above cannot see it - and without it the Studios card
# silently falls back to its drawn placeholder in the installed app while
# looking correct in the dev server.
for DATA in assets; do
    [ -d "$DATA" ] && cp -R "$DATA" "$APP/Contents/Resources/app/"
done
cp -R .streamlit "$APP/Contents/Resources/app/"
find "$APP/Contents/Resources/app" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

cp macos/Info.plist "$APP/Contents/Info.plist"
cp macos/AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"

# Ad-hoc signature. This is not an Apple Developer signature - it does not
# avoid Gatekeeper on a downloaded copy - but it keeps the bundle internally
# consistent so macOS never reports it as "damaged".
echo "  - ad-hoc signing"
codesign --force --deep --sign - "$APP" 2>/dev/null \
    && echo "    signed: $(codesign -dv "$APP" 2>&1 | grep -c Signature) ok" \
    || echo "    WARNING: codesign unavailable, continuing unsigned"

echo "==> Done: $APP"
echo "    Install it with:  ./install.sh"
echo "    Or package it:    ./package.sh"
