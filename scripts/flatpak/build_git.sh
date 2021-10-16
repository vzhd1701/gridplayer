#!/bin/bash

set -e

if [ "$1" == "--generate" ]; then
    [ -z "$2" ] && exit 1
    GENERATE_FOR_COMMIT="$2"
fi

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

update_flatpak_git() {
    BUILD_DIR_FLATPAK_SRC="$BUILD_DIR/flatpak_git/src"
    rm -rf "$BUILD_DIR_FLATPAK_SRC"
    mkdir -p "$BUILD_DIR_FLATPAK_SRC"

    git clone "https://${GIT_TOKEN}@github.com/${FLATPAK_GIT_REPO}.git" "$BUILD_DIR_FLATPAK_SRC"

    # Clean out repo
    find "$BUILD_DIR_FLATPAK_SRC" -mindepth 1 -maxdepth 1 -type f,d \
        ! -path '*/.git' \
        -exec rm -rf "{}" \;

    tar xf "$DIST_DIR"/*.tar.gz --strip-components=1 --directory="$BUILD_DIR_FLATPAK_SRC"
    cp -R "$BUILD_DIR"/meta "$BUILD_DIR_FLATPAK_SRC"

    pushd "$BUILD_DIR_FLATPAK_SRC"

    rm -f CHANGELOG.md README.md pyproject.toml

    #git config user.name "$GIT_USER"
    #git config user.email "$GIT_EMAIL"

    #git config user.name "action"
    #git config user.email "action@github.com"

    git config user.name "github-actions[bot]"
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

    git add .

    if [ $(git status --porcelain | wc -l) -gt 0 ]; then
        git commit -m "chore: release ${APP_VERSION}"
        git push origin master
    fi

    RETURN_VAL=$(git rev-parse HEAD)
    popd

    echo "Latest commit: $RETURN_VAL"
}

update_flathub_git_local() {
    FLATPAK_GIT_COMMIT="$1"

    BUILD_DIR_FLATHUB="$BUILD_DIR/flatpak_git/hub"
    rm -rf "$BUILD_DIR_FLATHUB"
    mkdir -p "$BUILD_DIR_FLATHUB"

    generate_flathub_git "$FLATPAK_GIT_COMMIT" "$BUILD_DIR_FLATHUB"
}

update_flathub_git() {
    FLATPAK_GIT_COMMIT="$1"

    BRANCH_NAME="release-${APP_VERSION}"

    if git ls-remote --exit-code --heads "https://github.com/${FLATHUB_GIT_REPO}.git" "$BRANCH_NAME"; then
        echo "$BRANCH_NAME branch already exists!"
        return 1
    fi

    BUILD_DIR_FLATHUB="$BUILD_DIR/flatpak_git/hub"
    rm -rf "$BUILD_DIR_FLATHUB"
    mkdir -p "$BUILD_DIR_FLATHUB"

    git clone --recursive "https://${GIT_TOKEN}@github.com/${FLATHUB_GIT_REPO}.git" "$BUILD_DIR_FLATHUB"

    pushd "$BUILD_DIR_FLATHUB"

    git checkout -b "$BRANCH_NAME"

    # Clean out repo
    find . -mindepth 1 -maxdepth 1 -type f,d \
        ! -path '*/.git' \
        ! -path '*/.gitmodules' \
        ! -path "*/shared-modules" \
        -exec rm -rf "{}" \;

    generate_flathub_git "$FLATPAK_GIT_COMMIT" "$BUILD_DIR_FLATHUB"

    git config user.name "$GIT_USER"
    git config user.email "$GIT_EMAIL"

    git submodule add https://github.com/flathub/shared-modules || true
    (cd "$BUILD_DIR_FLATHUB/shared-modules" && git checkout -q 83be76b6f07d5c5d6cac2d93e09ffc9c1ade07d0)

    git add .

    if [ $(git status --porcelain | wc -l) -gt 0 ]; then
        git commit -m "chore: release ${APP_VERSION}"
        git push origin "$BRANCH_NAME"
    fi

    popd
}

generate_flathub_git() {
    FLATPAK_GIT_COMMIT="$1"
    BUILD_DIR_FLATHUB="$2"

    cp "$SCRIPT_DIR"/dependencies/*.yml "$BUILD_DIR_FLATHUB"
    cp "$SCRIPT_DIR"/libvlc/* "$BUILD_DIR_FLATHUB"

    cat "$SCRIPT_DIR/app.yml" "$SCRIPT_DIR/app_git.yml" > "$BUILD_DIR_FLATHUB/$APP_ID.yml"
    replace_app_vars "$BUILD_DIR_FLATHUB/$APP_ID.yml"

    FLATPAK_GIT_REPO_URL="https://github.com/${FLATPAK_GIT_REPO}.git"

    sed -i "s#{GIT_URL}#$FLATPAK_GIT_REPO_URL#g" "$BUILD_DIR_FLATHUB/$APP_ID.yml"
    sed -i "s#{GIT_COMMIT}#$FLATPAK_GIT_COMMIT#g" "$BUILD_DIR_FLATHUB/$APP_ID.yml"
}

if [ -n "$GENERATE_FOR_COMMIT" ]; then
    update_flathub_git_local "$GENERATE_FOR_COMMIT"
    exit 0
fi

update_flatpak_git
FLATPAK_GIT_COMMIT=$RETURN_VAL

if [ -n "$FLATHUB_GIT_REPO" ]; then
    update_flathub_git "$FLATPAK_GIT_COMMIT"
fi
