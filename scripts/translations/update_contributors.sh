#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

CONTRIB_OUT="gridplayer/params/languages_contrib.py"

uv run --frozen "$SCRIPT_DIR/list_top_members.py" --identity ".local/crowdin.yml" --admin-username vzhd1701 "$CONTRIB_OUT"
uv run --frozen ruff format "$CONTRIB_OUT"
