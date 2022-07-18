#!/bin/bash

if [ "$1" == "all" ]; then
    conventional-changelog -u
    exit 0
fi

conventional-changelog -p conventionalcommits
