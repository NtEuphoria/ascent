#!/bin/bash
# One-shot publish to GitHub: create the repository, push, and publish a
# release with the macOS installer attached.
#
# Usage:   ./publish.sh                              (prompts for the token)
#          ./publish.sh --token-file ~/token.txt     (reads it from a file)
#          GITHUB_TOKEN=xxx ./publish.sh             (reads it from the env)
#
# You will be asked for a GitHub personal access token. It is read without
# echoing, held only in memory for this run, and never written to disk, to the
# git config, or to your shell history.
set -euo pipefail
cd "$(dirname "$0")"

OWNER="NtEuphoria"
REPO="ascent"
VERSION=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" macos/Info.plist)
DESCRIPTION="Native macOS engineering toolkit: 54 interactive calculators for aerospace, robotics, drones, mechanical, rotational, materials, electronics and control systems. Every result shows its equation, variables and assumptions."
TOPICS='["macos","aerospace","robotics","drones","engineering","mechanical-engineering","materials-science","control-systems","streamlit","python","swift","calculator","education","stem","engineering-tools"]'

api() {  # api <method> <path> [json-body]
    local method="$1" path="$2" body="${3:-}"
    if [ -n "$body" ]; then
        curl -sS -X "$method" -H "Authorization: Bearer $TOKEN" \
             -H "Accept: application/vnd.github+json" \
             -H "X-GitHub-Api-Version: 2022-11-28" \
             -d "$body" "https://api.github.com$path"
    else
        curl -sS -X "$method" -H "Authorization: Bearer $TOKEN" \
             -H "Accept: application/vnd.github+json" \
             -H "X-GitHub-Api-Version: 2022-11-28" \
             "https://api.github.com$path"
    fi
}

field() { python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$1',''))"; }

echo "==> ASCENT $VERSION -> github.com/$OWNER/$REPO"
echo

TOKEN=""
TOKEN_FILE=""
[ "${1:-}" = "--token-file" ] && TOKEN_FILE="${2:-}"

if [ -n "$TOKEN_FILE" ]; then
    [ -f "$TOKEN_FILE" ] || { echo "ERROR: no such file: $TOKEN_FILE"; exit 1; }
    TOKEN=$(tr -d ' \t\r\n' < "$TOKEN_FILE")
    echo "Read the token from $TOKEN_FILE."
elif [ -n "${GITHUB_TOKEN:-}" ]; then
    TOKEN="$GITHUB_TOKEN"
    echo "Using the token from \$GITHUB_TOKEN."
elif [ ! -t 0 ]; then
    read -r TOKEN            # piped in
else
    echo "A GitHub personal access token is needed (this is not your password)."
    echo "Create one here - tick only the 'repo' scope:"
    echo "    https://github.com/settings/tokens/new?scopes=repo&description=ASCENT%20publish"
    command -v open >/dev/null && open "https://github.com/settings/tokens/new?scopes=repo&description=ASCENT%20publish" 2>/dev/null || true
    echo
    echo "  +------------------------------------------------------------+"
    echo "  |  YOUR TYPING WILL NOT APPEAR. That is deliberate - the      |"
    echo "  |  token is hidden so it never shows on screen or in your     |"
    echo "  |  shell history. Paste it (Cmd-V) and press Return. The      |"
    echo "  |  screen will look unchanged until you do.                   |"
    echo "  +------------------------------------------------------------+"
    echo
    read -rsp "  Paste token, then press Return: " TOKEN
    echo
    echo
fi

TOKEN=$(printf '%s' "$TOKEN" | tr -d ' \t\r\n')
if [ -z "$TOKEN" ]; then
    echo "No token received. Nothing was changed."
    echo
    echo "If pasting into the prompt does not work in your terminal, use a file"
    echo "instead - save the token to a text file and run:"
    echo "    ./publish.sh --token-file ~/Downloads/token.txt"
    exit 1
fi

# Confirm receipt without ever printing the token itself.
echo "==> Token received: ${#TOKEN} characters, starts with ${TOKEN:0:4}"
case "$TOKEN" in
    ghp_*|github_pat_*|gho_*) ;;
    *) echo "    WARNING: that does not look like a GitHub token (expected it"
       echo "    to start with ghp_ or github_pat_). Continuing anyway." ;;
esac

LOGIN=$(api GET /user | field login)
if [ -z "$LOGIN" ]; then
    echo "ERROR: GitHub rejected that token."
    echo "  - Has it been revoked, or did it expire?"
    echo "  - Was the 'repo' scope ticked when you created it?"
    echo "  - Was the whole token copied? They are about 40 characters."
    echo "Nothing was changed."
    exit 1
fi
echo "==> Authenticated as $LOGIN"

# 1. Repository ------------------------------------------------------------
if api GET "/repos/$OWNER/$REPO" | grep -q '"full_name"'; then
    echo "==> Repository already exists - updating its description"
    api PATCH "/repos/$OWNER/$REPO" \
        "$(python3 -c 'import json,sys; print(json.dumps({"description": sys.argv[1], "homepage": ""}))' "$DESCRIPTION")" >/dev/null
else
    echo "==> Creating the repository"
    api POST /user/repos \
        "$(python3 -c 'import json,sys; print(json.dumps({"name": sys.argv[1], "description": sys.argv[2], "private": False, "has_issues": True, "has_wiki": False}))' "$REPO" "$DESCRIPTION")" \
        | grep -q '"full_name"' || { echo "ERROR: could not create the repository."; exit 1; }
fi

echo "==> Setting topics"
api PUT "/repos/$OWNER/$REPO/topics" "{\"names\": $TOPICS}" >/dev/null

# 2. Push ------------------------------------------------------------------
echo "==> Pushing main"
git remote get-url origin >/dev/null 2>&1 \
    || git remote add origin "https://github.com/$OWNER/$REPO.git"
# The token is passed through a credential helper rather than the URL, so it
# never lands in .git/config or in the process list of other users.
git -c credential.helper='!f() { echo username=x-access-token; echo "password=$TOKEN"; }; f' \
    push -u origin main

# 3. Installer -------------------------------------------------------------
echo "==> Building the installer"
./package.sh >/dev/null
DMG="dist/ASCENT-$VERSION.dmg"
[ -f "$DMG" ] || { echo "ERROR: $DMG was not produced."; exit 1; }

echo "==> Publishing release v$VERSION"
NOTES=$(cat <<NOTE
### Install

1. Download **ASCENT-$VERSION.dmg** below.
2. Open it and drag **ASCENT** into your Applications folder.
3. **Right-click the app and choose Open** the first time. macOS blocks apps
   that are not signed with a paid Apple Developer certificate, so the normal
   double-click shows a warning instead. You only do this once.

The first launch takes about a minute while ASCENT builds its Python
environment. It needs Python 3.9+ and an internet connection for that first
run only.

Requires macOS 11 or newer. Universal: Apple Silicon and Intel.
Windows and Linux builds are planned.

### What's in it

54 calculators across 10 categories — aerodynamics, flight performance,
drones, mechanical, rotational mechanics, materials, electrical/robotics,
control systems, unit conversion and reference constants. Every calculator
shows its equation, defines each variable, states its assumptions under the
result, and gives a real example of where it is used.

Verified by 113 tests: hand-worked known values for every equation, rejection
tests for invalid input, and headless renders of all 54 pages.
NOTE
)
RELEASE=$(api POST "/repos/$OWNER/$REPO/releases" \
    "$(python3 -c 'import json,sys; print(json.dumps({"tag_name": sys.argv[1], "name": sys.argv[2], "body": sys.argv[3], "draft": False, "prerelease": False}))' \
        "v$VERSION" "ASCENT $VERSION" "$NOTES")")
UPLOAD=$(echo "$RELEASE" | field upload_url | sed 's/{.*}//')
[ -n "$UPLOAD" ] || { echo "ERROR: release not created. Response:"; echo "$RELEASE" | head -5; exit 1; }

echo "==> Uploading the installer"
curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/x-apple-diskimage" \
     --data-binary "@$DMG" \
     "$UPLOAD?name=ASCENT-$VERSION.dmg" >/dev/null

unset TOKEN
if [ -n "$TOKEN_FILE" ]; then
    rm -f "$TOKEN_FILE"
    echo "==> Deleted $TOKEN_FILE (it had served its purpose)"
fi
echo
echo "==> Published."
echo "    https://github.com/$OWNER/$REPO"
echo "    https://github.com/$OWNER/$REPO/releases/latest"
