#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

if [ "$1" == "run" ]; then
    flatpak run ${APP_ID}
    exit 0
elif [ "$1" == "del" ]; then
    flatpak uninstall -y ${APP_ID}
    exit 0
fi

if ! command -v flatpak; then
    sudo apt install flatpak
    flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

    flatpak install flathub org.kde.Platform//5.15
    flatpak install flathub org.kde.Sdk//5.15
fi

poetry build -f wheel

bash "$SCRIPTS_DIR/linux_meta/build.sh"

bash "$SCRIPTS_DIR/flatpak/build.sh" "$@"
