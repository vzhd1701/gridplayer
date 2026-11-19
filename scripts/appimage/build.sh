#!/bin/bash

set -e

# For the machine's architecture. x86_64 on manylinux_2_34 (EL9), the oldest
# with a libmpv new enough in its packages; aarch64 on manylinux_2_39, as
# PyQt6's aarch64 wheels are. APPIMAGE_ARCH=aarch64 builds one on an x86_64
# machine, slowly, through QEMU (binfmt set up for Docker)
ARCH=${APPIMAGE_ARCH:-$(uname -m)}

case "$ARCH" in
    x86_64) BASE_IMAGE_NAME="manylinux_2_34_x86_64"; PLATFORM="linux/amd64" ;;
    aarch64) BASE_IMAGE_NAME="manylinux_2_39_aarch64"; PLATFORM="linux/arm64" ;;
    *) echo "No AppImage for $ARCH" >&2; exit 1 ;;
esac

BASE_IMAGE_URL="quay.io/pypa/$BASE_IMAGE_NAME"
NAME="appimage_build_$ARCH"

if [ "$1" == "test" ]; then
    docker run --rm -it --platform "$PLATFORM" \
        -v $(pwd)/:/build/ \
        -w /build/ \
        "$BASE_IMAGE_URL" bash
    exit 0
fi

# A container kept from a build on another image is made anew
if [ "$(docker ps -a -q -f name=$NAME)" ] && \
   [ "$(docker inspect -f '{{.Config.Image}}' "$NAME")" != "$BASE_IMAGE_URL" ]; then
    echo "Removing container of another image"

    docker rm "$NAME"
fi

if [ ! "$(docker ps -a -q -f name=$NAME)" ]; then
    echo "Creating new container"

    docker run --name "$NAME" --platform "$PLATFORM" \
        -v $(pwd)/:/build/ \
        -w /build/ \
        "$BASE_IMAGE_URL" \
        bash "scripts/appimage/build_docker.sh"
else
    echo "Re-running existing container"

    docker start -a "$NAME"
fi
