#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

if [ "$1" == "run" ]; then
    flatpak run ${APP_ID} "${@:2}"
    exit 0
elif [ "$1" == "del" ]; then
    flatpak uninstall -y ${APP_ID}
    exit 0
fi

if ! command -v flatpak; then
    sudo apt install flatpak
    flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

    flatpak install flathub org.kde.Platform//5.15-22.08
    flatpak install flathub org.kde.Sdk//5.15-22.08
fi

poetry build -f sdist
poetry export --without-hashes -f requirements.txt --output "$DIST_DIR/requirements.txt"

bash "$SCRIPTS_DIR/linux_meta/build.sh"
bash "$SCRIPTS_DIR/flatpak/generate_dependencies.sh"

bash "$SCRIPTS_DIR/flatpak/build.sh" "$@"
