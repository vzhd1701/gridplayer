#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

list_proofread() {
    # output: LANG PERCENT
    crowdin status proofreading --no-progress --no-colors -c "$SCRIPT_DIR/crowdin.yml" --identity ".local/crowdin.yml" | grep "%" | grep -v " 0%" | sed -E "s/[[:space:]]*- (.+): [[:digit:]]+%/\1/"
}

retry_cmd() {
    local n=1
    local max=3
    while ! "$@"; do
        if (( n >= max )); then
            return 1
        else
            echo "Attempt $n failed. Retrying..."
            sleep 2
            ((n++))
        fi
    done
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
    retry_cmd crowdin download -c "$SCRIPT_DIR/crowdin.yml" --identity ".local/crowdin.yml" --skip-untranslated-strings --export-only-approved --language="$CUR_LANG"
    sleep 10
done

# Strip locations

for ts_file in resources/translations/*.ts; do
    if [[ $(basename "$ts_file") == "en_US.ts" ]]; then
        continue
    fi

    sed -i -E '/^[[:space:]]*<location .*\/>$/d' "$ts_file"
done
