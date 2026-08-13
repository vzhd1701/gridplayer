#!/bin/bash

# package test (from dist root, after build):
#   choco install gridplayer.install -dv -y -s .
#   choco install gridplayer.portable -dv -y -s .
#   choco install gridplayer -dv -y -s .
#
# push (install/portable first, meta last):
#   choco apikey add -s https://push.chocolatey.org/ -k YOUR_API_KEY
#   choco push gridplayer.install.*.nupkg --source https://push.chocolatey.org/
#   choco push gridplayer.portable.*.nupkg --source https://push.chocolatey.org/
#   choco push gridplayer.*.nupkg --source https://push.chocolatey.org/

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

ensure_prerequisites() {
    if ! command -v choco >/dev/null 2>&1; then
        die "Chocolatey (choco) is not available on PATH. Install from https://chocolatey.org/install"
    fi

    if ! command -v jq >/dev/null 2>&1; then
        die "jq is required. Install jq and ensure it is on PATH."
    fi

    if ! command -v curl >/dev/null 2>&1; then
        die "curl is required. Install curl and ensure it is on PATH."
    fi

    local validation_pkg="chocolatey-community-validation.extension"
    if ! choco list --exact --limit-output "$validation_pkg" 2>/dev/null \
        | grep -qi 'chocolatey-community-validation'; then
        die "$validation_pkg" is required.
    fi
}

build_one() {
    local BUILD_TYPE="$1"

    local CHOCO_ID=""
    local CHOCO_TITLE=""
    local DEPENDENCIES=""
    local PACKAGE_PATTERN=""
    local INSTALL_SCRIPT=""
    local UNINSTALL_SCRIPT=""
    local PACKAGE_PARAMETERS=""
    local INCLUDE_TOOLS=0

    if [ "$BUILD_TYPE" == "meta" ]; then
        CHOCO_ID="$APP_MODULE"
        CHOCO_TITLE="$APP_NAME"
        DEPENDENCIES="<dependencies><dependency id=\"${APP_MODULE}.install\" version=\"[${APP_VERSION}]\" /></dependencies>"
    elif [ "$BUILD_TYPE" == "install" ]; then
        CHOCO_ID="$APP_MODULE.install"
        CHOCO_TITLE="$APP_NAME (Install)"
        PACKAGE_PATTERN="GridPlayer-.*-win64-install.exe"
        INSTALL_SCRIPT="$SCRIPT_DIR/chocolateyInstall.install.ps1"
        # Uninstall via Chocolatey auto-uninstaller (Inno Setup ARP entry + softwareName)
        INCLUDE_TOOLS=1
        PACKAGE_PARAMETERS="
## Notes

- Windows x64 only
- Installs via Inno Setup to Program Files"
    elif [ "$BUILD_TYPE" == "portable" ]; then
        CHOCO_ID="$APP_MODULE.portable"
        CHOCO_TITLE="$APP_NAME (Portable)"
        PACKAGE_PATTERN="GridPlayer-.*-win64-portable.zip"
        INSTALL_SCRIPT="$SCRIPT_DIR/chocolateyInstall.portable.ps1"
        UNINSTALL_SCRIPT="$SCRIPT_DIR/chocolateyUninstall.portable.ps1"
        INCLUDE_TOOLS=1
        PACKAGE_PARAMETERS="
## Package Install Parameters

- \`/DesktopIcon\` - Create a Desktop shortcut for the current user.
- \`/NoStart\` - Do not create a Start Menu shortcut.

## Notes

- Windows x64 only
- Extracts to the Chocolatey tools location (app files at package root) and adds a PATH shim"
    else
        die "Unknown build type '$BUILD_TYPE' (expected: meta, install, portable, or all)"
    fi

    local BUILD_DIR_CHOCO="$BUILD_DIR/chocolatey/$BUILD_TYPE"
    local NUSPEC_PATH="$BUILD_DIR_CHOCO/${CHOCO_ID}.nuspec"

    rm -rf "$BUILD_DIR_CHOCO"
    mkdir -p "$BUILD_DIR_CHOCO"

    if [ "$INCLUDE_TOOLS" -eq 1 ]; then
        mkdir -p "$BUILD_DIR_CHOCO/tools"

        copy_with_app_vars "$SCRIPT_DIR/chocolateyBeforeModify.ps1" "$BUILD_DIR_CHOCO/tools/chocolateyBeforeModify.ps1"
        copy_with_app_vars "$INSTALL_SCRIPT" "$BUILD_DIR_CHOCO/tools/chocolateyInstall.ps1"

        if [ -n "$UNINSTALL_SCRIPT" ]; then
            copy_with_app_vars "$UNINSTALL_SCRIPT" "$BUILD_DIR_CHOCO/tools/chocolateyUninstall.ps1"
        fi

        local ASSET_JSON PACKAGE_URL PACKAGE_SHA256
        ASSET_JSON=$(curl "${CURL_OPTS[@]}" "$RELEASE_URL" | jq -c ".assets[] | select(.name|test(\"${PACKAGE_PATTERN}\"))")
        PACKAGE_URL=$(echo "$ASSET_JSON" | jq -r ".browser_download_url")
        # GitHub API provides digest as "sha256:<hex>"; strip the prefix for Chocolatey
        PACKAGE_SHA256=$(echo "$ASSET_JSON" | jq -r ".digest | ltrimstr(\"sha256:\")")

        if [ -z "$PACKAGE_URL" ] || [ "$PACKAGE_URL" = "null" ]; then
            die "No package URL for pattern '$PACKAGE_PATTERN' in release v${APP_VERSION}"
        fi
        if [ -z "$PACKAGE_SHA256" ] || [ "$PACKAGE_SHA256" = "null" ]; then
            die "No checksum (asset digest) for pattern '$PACKAGE_PATTERN' in release v${APP_VERSION}"
        fi

        sed -i "s#{PACKAGE_URL}#$PACKAGE_URL#g" "$BUILD_DIR_CHOCO/tools/chocolateyInstall.ps1"
        sed -i "s#{PACKAGE_SHA256}#$PACKAGE_SHA256#g" "$BUILD_DIR_CHOCO/tools/chocolateyInstall.ps1"
    fi

    copy_with_app_vars "$SCRIPT_DIR/template.nuspec" "$NUSPEC_PATH"
    awk -i inplace -v r="$PACKAGE_PARAMETERS" '{gsub(/{PACKAGE_PARAMETERS}/,r)}1' "$NUSPEC_PATH"
    awk -i inplace -v r="$DEPENDENCIES" '{gsub(/{DEPENDENCIES}/,r)}1' "$NUSPEC_PATH"
    sed -i "s#{CHOCO_ID}#$CHOCO_ID#g" "$NUSPEC_PATH"
    sed -i "s#{CHOCO_TITLE}#$CHOCO_TITLE#g" "$NUSPEC_PATH"

    # Meta package is dependency-only; no tools scripts or files section
    if [ "$INCLUDE_TOOLS" -eq 0 ]; then
        sed -i '/<files>/,/<\/files>/d' "$NUSPEC_PATH"
    fi

    (cd "$BUILD_DIR_CHOCO" && choco pack)

    mkdir -p "$DIST_DIR"
    mv "$BUILD_DIR_CHOCO"/*.nupkg "$DIST_DIR"

    echo "Built ${CHOCO_ID} ${APP_VERSION} -> $DIST_DIR"
}

ensure_prerequisites

RELEASE_URL="https://api.github.com/repos/${APP_REPO_SLUG}/releases/tags/v${APP_VERSION}"
CURL_OPTS=(-sS)
if [ -n "${GITHUB_TOKEN:-}" ]; then
    CURL_OPTS+=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
fi

BUILD_TYPE="${1:-}"

if [ -z "$BUILD_TYPE" ]; then
    die "Usage: $0 <meta|install|portable|all>"
fi

if [ "$BUILD_TYPE" == "all" ]; then
    build_one install
    build_one portable
    build_one meta
    echo "All Chocolatey packages built in $DIST_DIR"
    exit 0
fi

build_one "$BUILD_TYPE"
