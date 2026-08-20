#!/bin/bash

set -e

REPO="https://origin.archive.neon.kde.org/release jammy main"
REPO_KEY_URL="https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x444DABCF3667D0283F894EDDE6D4736255751E5D"

generate_apt_conf() {
cat <<EOF > "$1/apt.conf"
Dir::Etc::main "$1";
Dir::Etc::Parts "$1/apt.conf.d";
Dir::Etc::sourcelist "$1/sources.list";
Dir::Etc::sourceparts "$1/sources.list.d";
Dir::State "$1";
Dir::State::status "$1/status";
Dir::Cache "$1";
EOF
}

APT_TMP_DIR="$(pwd)/apt-tmp"
APT_CONF_PATH="$APT_TMP_DIR/apt.conf"

if [ ! -d "$APT_TMP_DIR" ]; then
    mkdir -p "$APT_TMP_DIR/lists/partial"

    generate_apt_conf "$APT_TMP_DIR"
    touch "$APT_TMP_DIR/status"

    REPO_KEY_PATH="$APT_TMP_DIR/repo_key.gpg"
    wget -qO- "$REPO_KEY_URL" | gpg --dearmor | tee "$REPO_KEY_PATH" >/dev/null

    echo "deb [signed-by=${REPO_KEY_PATH}] $REPO" > "$APT_TMP_DIR/sources.list"
fi

apt-get -c "$APT_CONF_PATH" update
apt-get -c "$APT_CONF_PATH" download "$@"
