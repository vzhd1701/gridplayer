#!/bin/bash

if ! command -v realpath &> /dev/null; then
    realpath() {
        [[ $1 = /* ]] && echo "$1" || echo "$PWD/${1#./}"
    }
fi

replace_app_vars() {
    TARGET_FILE="$1"

    [ ! -f "$TARGET_FILE" ] && return

    VARS=(APP_MODULE APP_DISP_NAME APP_NAME APP_ID APP_VERSION APP_VERSION_DATE APP_AUTHOR APP_AUTHOR_CONTACT APP_URL APP_BUGTRACKER_URL)

    for var in "${VARS[@]}"; do
        eval replace='$'$var
        sed -i "s#{$var}#$replace#g" "$TARGET_FILE"
    done
}

copy_with_app_vars() {
    SOURCE_FILE="$1"
    DESTINATION="$2"

    if [ -d "$DESTINATION" ]; then
        DEST_FILE="$(realpath $DESTINATION)/$(basename $SOURCE_FILE)"
    else
        DEST_FILE="$DESTINATION"
    fi

    cp "$SOURCE_FILE" "$DEST_FILE"
    replace_app_vars "$DEST_FILE"
}

init_venv() {
    VENV_DIR="$1"

    if [ ! -d "$VENV_DIR" ]; then
        python -m venv "$VENV_DIR"

        activate_venv "$VENV_DIR"

        python -m pip install --upgrade pip
    else
        activate_venv "$VENV_DIR"
    fi
}

activate_venv() {
    VENV_DIR="$1"

    if [ -f "$VENV_DIR/Scripts/activate" ]; then
        . "$VENV_DIR/Scripts/activate"
    else
        . "$VENV_DIR/bin/activate"
    fi
}

#ROOT_DIR="$(realpath $(dirname $( cd "$( dirname $0 )" && pwd ))/..)"
export ROOT_DIR="$(realpath $(pwd))"

export RESOURCES_DIR="$ROOT_DIR/resources"
export BUILD_DIR="$ROOT_DIR/build"
export DIST_DIR="$ROOT_DIR/dist"
export SCRIPTS_DIR="$ROOT_DIR/scripts"

export APP_MODULE="gridplayer"
export APP_BASE_DIR=$(realpath "./$APP_MODULE")

export APP_DISP_NAME=$(sed -n 's/__display_name__ = "\([^"]*\).*/\1/p' "$APP_BASE_DIR/version.py")
export APP_NAME=$(sed -n 's/__app_name__ = "\([^"]*\).*/\1/p' "$APP_BASE_DIR/version.py")
export APP_ID=$(sed -n 's/__app_id__ = "\([^"]*\).*/\1/p' "$APP_BASE_DIR/version.py")
export APP_VERSION=$(sed -n 's/__version__ = "\([^"]*\).*/\1/p' "$APP_BASE_DIR/version.py")
export APP_VERSION_DATE=$(sed -n 's/__version_date__ = "\([^"]*\).*/\1/p' "$APP_BASE_DIR/version.py")
export APP_AUTHOR=$(sed -n 's/__author_name__ = "\([^"]*\).*/\1/p' "$APP_BASE_DIR/version.py")
export APP_AUTHOR_CONTACT=$(sed -n 's/__author_contact__ = "\([^"]*\).*/\1/p' "$APP_BASE_DIR/version.py")
export APP_URL=$(sed -n 's/__app_url__ = "\([^"]*\).*/\1/p' "$APP_BASE_DIR/version.py")
export APP_BUGTRACKER_URL=$(sed -n 's/__app_bugtracker_url__ = "\([^"]*\).*/\1/p' "$APP_BASE_DIR/version.py")
