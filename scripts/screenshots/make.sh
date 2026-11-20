#!/bin/bash
# Fresh screenshots for the README and the stores, into resources/public: `just screenshots`.
#
# Flathub wants the window as the desktop draws it, so this runs on Ubuntu, in a terminal of
# the GNOME session, at a scale of 100% and with the desktop's own look (light, Yaru). Close
# GridPlayer and GNOME Screenshot first. It takes over the screen for a minute: leave it be.
#
# The clips are get_clips.sh's (made the first time); SHOTS_MEDIA takes others, laid out the
# same way. Each run's report, log and the desktop's raw shots stay in build/screenshots.
set -u
OUT=build/screenshots
PUBLIC=resources/public

case "${XDG_CURRENT_DESKTOP:-}" in
*GNOME*) ;;
*) echo "Run this in a GNOME session"; exit 1 ;;
esac

./scripts/screenshots/get_clips.sh || exit 1

rm -rf "$OUT"
for shot in 1 2 3 4; do
    name=$(printf "screenshot-%03d" "$shot")
    SHOT=$shot REAL_APP_QT_PLATFORM=auto uv run python -m tests.real_app.run \
        scripts/screenshots/shots.py --out "$OUT/$shot" >"$OUT-$shot.log" 2>&1 \
        || { echo "SHOT $shot FAILED: see $OUT/$shot/report.json and $OUT-$shot.log"; exit 1; }
    mv "$OUT-$shot.log" "$OUT/$shot/run.log"

    cp "$OUT/$shot/$name.png" "$PUBLIC/$name.png"
    ffmpeg -nostdin -v error -y -i "$PUBLIC/$name.png" -vf scale=300:-1 "$PUBLIC/$name-thumb.png" \
        || { echo "THUMBNAIL FAILED $name"; exit 1; }
    echo "made $PUBLIC/$name.png"
done

# smaller, the way the earlier ones were: optional, as neither is in Ubuntu by default
if command -v pngquant >/dev/null; then
    pngquant --force --skip-if-larger --quality 85-100 --ext .png "$PUBLIC"/screenshot-*.png
fi
if command -v optipng >/dev/null; then
    optipng -quiet -o2 "$PUBLIC"/screenshot-*.png
fi

ls -l "$PUBLIC"/screenshot-*.png
