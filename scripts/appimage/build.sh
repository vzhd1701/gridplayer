#!/bin/bash

set -e

BASE_IMAGE_NAME="manylinux_2_34_x86_64"
BASE_IMAGE_URL="quay.io/pypa/$BASE_IMAGE_NAME"
NAME="appimage_build"

if [ "$1" == "test" ]; then
    docker run --rm -it \
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

    docker run --name "$NAME" \
        -v $(pwd)/:/build/ \
        -w /build/ \
        "$BASE_IMAGE_URL" \
        bash "scripts/appimage/build_docker.sh"
else
    echo "Re-running existing container"

    docker start -a "$NAME"
fi
