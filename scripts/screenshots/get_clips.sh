#!/bin/bash
# Clips of Blender's open movies for the screenshots, into SHOTS_MEDIA: wide/ (16:9) and mixed/
# (of every shape), 40 s each with the moment to show 15 s in, where shots.py pauses them (AT_S).
#
# The films are CC BY (see CREDITS.md), fetched whole once into src/, about 640 MB in all:
# Wikimedia turns away a client that seeks around in its files, one request after another.
set -u
M=${SHOTS_MEDIA:-build/screenshot-media}
# Wikimedia asks a script to say what it is, with a link
UA="gridplayer-screenshot-clips/1.0 (+https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia)"
COMMONS=https://upload.wikimedia.org/wikipedia/commons
mkdir -p "$M/src"
cd "$M" || exit 1

fetch() { # file URL
    [ -s "src/$1" ] && return
    echo "fetching $1"
    curl -fsS -A "$UA" -o "src/$1.part" "$2" && mv "src/$1.part" "src/$1" || { echo "DOWNLOAD FAILED $1"; exit 1; }
}

if [ ! -s src/bbb.mp4 ]; then
    echo "fetching bbb.mp4"
    curl -fsS -o src/bbb.zip https://download.blender.org/demo/movies/BBB/bbb_sunflower_1080p_30fps_normal.mp4.zip || { echo "DOWNLOAD FAILED bbb"; exit 1; }
    python3 -c "import zipfile; z = zipfile.ZipFile('src/bbb.zip'); open('src/bbb.mp4', 'wb').write(z.read('bbb_sunflower_1080p_30fps_normal.mp4'))" || { echo "UNZIP FAILED bbb"; exit 1; }
    rm -f src/bbb.zip
fi
fetch spring.webm "$COMMONS/a/a5/Spring_-_Blender_Open_Movie.webm"
fetch coffee_run.webm "$COMMONS/3/3f/Coffee_Run_-_Blender_Open_Movie-full_movie.webm"
fetch wing_it.webm "$COMMONS/3/38/WING_IT%21_-_Blender_Open_Movie-full_movie.webm"
fetch hero.webm "$COMMONS/a/a9/HERO_-_Blender_Open_Movie-full_movie.webm"
fetch sprite_fright.webm "$COMMONS/7/76/Sprite_Fright_-_Blender_Open_Movie-full_movie.webm"

clip() { # folder, title (the file's name, what the cell shows), film, second to show,
         # shape (W:H, or "film" as it is), where across the film to cut it from (0 to 1)
    out="$1/$2.mp4"; film=$3; at=$4; shape=${5:-16:9}; across=${6:-0.5}
    [ -s "$out" ] && return
    if [ "$shape" = film ]; then
        vf="scale=-2:720,setsar=1"
    else
        w=${shape%:*}; h=${shape#*:}
        vf="crop='min(iw,ih*$w/$h)':'min(ih,iw*$h/$w)':'(iw-ow)*$across',setsar=1"
        # tall ones as tall as a phone's
        if [ "$h" -gt "$w" ]; then vf="$vf,scale=-2:960"; else vf="$vf,scale=-2:720"; fi
    fi
    mkdir -p "$1"
    ffmpeg -nostdin -v error -y -ss "$((at - 15))" -i "src/$film" -t 40 -vf "$vf" \
        -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -c:a aac -b:a 96k "tmp_clip.mp4" \
        && mv tmp_clip.mp4 "$out" && echo "made $out" || { echo "ENCODE FAILED $out"; exit 1; }
}

# in name order: the first four are the first shot, all six the menu and settings shots
clip wide "Big Buck Bunny" bbb.mp4 98
clip wide "Coffee Run" coffee_run.webm 50
clip wide "Hero" hero.webm 50
clip wide "Spring" spring.webm 391
clip wide "Sprite Fright" sprite_fright.webm 180
clip wide "Wing It" wing_it.webm 50

# shapes of every kind, for the fourth: phone, square, old TV, HD and cinema
clip mixed "Big Buck Bunny" bbb.mp4 98 16:9
clip mixed "Coffee Run" coffee_run.webm 39 4:3 0.35
clip mixed "Hero" hero.webm 50 1:1 0.6
clip mixed "Spring" spring.webm 231 9:16 0.5
clip mixed "Sprite Fright" sprite_fright.webm 180 film
clip mixed "Wing It" wing_it.webm 77 9:16 0.58
