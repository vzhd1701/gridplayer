#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

list_proofread() {
    # output: LANG PERCENT
    crowdin status proofreading --no-progress --no-colors -c "$SCRIPT_DIR/crowdin.yml" --identity ".local/crowdin.yml" | grep "%" | grep -v " 0%" | sed -E "s/[[:space:]]*- (.+): [[:digit:]]+%/\1/"
}

if [ "$1" == "list" ]; then
    list_proofread
    exit 0
fi

if [ -n "$1" ]; then
    echo "Selected languages: $@"
    IFS=' ' read -a LANUAGES <<< "$@"
else
    LANUAGES=$(list_proofread | cut -d' ' -f1)
fi

for CUR_LANG in ${LANUAGES[@]}; do
    echo "Downloading language '$CUR_LANG'"
    crowdin download -c "$SCRIPT_DIR/crowdin.yml" --identity ".local/crowdin.yml" --skip-untranslated-strings --export-only-approved --language="$CUR_LANG"
done
