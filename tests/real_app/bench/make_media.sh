#!/bin/bash
# Real footage (Big Buck Bunny, the 4K 60 fps master, about 700 MB to fetch) to clips of known
# size, rate and codec, with no audio. Made once each, in BENCH_MEDIA.
set -u
M=${BENCH_MEDIA:-build/bench-media}
F4=bbb_sunflower_2160p_60fps_normal.mp4
mkdir -p "$M/src"
cd "$M" || exit 1

if [ ! -s "src/$F4" ]; then
    wget -q -O src/master.zip "https://download.blender.org/demo/movies/BBB/$F4.zip" || { echo "DOWNLOAD FAILED"; exit 1; }
    python3 -c "import zipfile; zipfile.ZipFile('src/master.zip').extract('$F4', 'src')" || { echo "UNZIP FAILED"; exit 1; }
    rm -f src/master.zip
fi

enc() { # name filter codec bitrate-kbit keyframe-interval [more of ffmpeg's options]
    name=$1; vf=$2; codec=$3; kb=$4; gop=$5; shift 5
    [ -s "$name.mp4" ] && return
    ffmpeg -nostdin -v error -y -ss 120 -t 60 -i "src/$F4" -an -vf "$vf" -c:v "$codec" -preset veryfast \
        -b:v "${kb}k" -maxrate "$((kb * 3 / 2))k" -bufsize "$((kb * 2))k" -g "$gop" -pix_fmt yuv420p "$@" "tmp_$name.mp4" \
        && mv "tmp_$name.mp4" "$name.mp4" && echo "made $name" || echo "ENCODE FAILED $name"
}

enc h264_1080p30 fps=30,scale=1920:1080 libx264 8000 60
enc h264_1080p60 fps=60,scale=1920:1080 libx264 12000 120
enc h264_1440p60 fps=60,scale=2560:1440 libx264 24000 120
enc h264_2160p30 fps=30 libx264 30000 60
enc h264_2160p60 fps=60 libx264 50000 120
enc hevc_1080p60 fps=60,scale=1920:1080 libx265 8000 120 -x265-params log-level=error
# cheap to decode, so what runs out is the player and not the decoder
enc h264_360p60 fps=60,scale=640:360 libx264 1500 120
enc h264_540p60 fps=60,scale=960:540 libx264 3000 120
# nothing for skipping frames to skip
enc h264_1080p60_nob fps=60,scale=1920:1080 libx264 12000 120 -bf 0

# a grid as it might be: what a phone, a camera or a download would give, each cell a file of its own
enc h264_720p30 fps=30,scale=1280:720 libx264 4000 60
enc h264_1080p24 fps=24000/1001,scale=1920:1080 libx264 6000 48
enc phone_1080p30 fps=30,scale=1920:1080 libx264 17000 30 -bf 0
enc hevc10_1080p30 fps=30,scale=1920:1080 libx265 6000 60 -pix_fmt yuv420p10le -x265-params log-level=error

# many small videos, the cheap end: tall and 16 fps, as an image model's clips come
enc portrait_960p16 "fps=16,crop=ih*3/4:ih,scale=720:960" libx264 1200 32

cut() { # set and index, clip, seconds in, extension [more of ffmpeg's options, before its input]
    out="$1_$2.$4"; in=$2; at=$3; shift 4
    [ -s "$out" ] && return
    ffmpeg -nostdin -v error -y "$@" -ss "$at" -i "$in.mp4" -c copy "$out" && echo "made $out" || echo "CUT FAILED $out"
}

cut mix00 h264_1080p30 5 mp4
cut mix01 h264_1080p30 17 mp4
cut mix02 h264_1080p24 3 mkv
cut mix03 h264_1080p24 23 mkv
cut mix04 h264_720p30 7 mp4
cut mix05 h264_720p30 29 mp4
cut mix06 h264_720p30 11 mp4
cut mix07 phone_1080p30 2 mp4 -display_rotation 90
cut mix08 phone_1080p30 19 mp4 -display_rotation 90
cut mix09 h264_1080p60_nob 13 mp4
cut mix10 hevc10_1080p30 5 mp4
cut mix11 hevc10_1080p30 21 mp4
cut mix12 h264_2160p30 9 mp4
cut mix13 h264_1080p60 31 mp4
cut mix14 hevc_1080p60 15 mp4
cut mix15 h264_540p60 4 mp4

# the small set, each from a part of its own
cut small00 portrait_960p16 1 mp4
cut small01 portrait_960p16 5 mp4
cut small02 portrait_960p16 9 mp4
cut small03 portrait_960p16 13 mp4
cut small04 portrait_960p16 17 mp4
cut small05 portrait_960p16 21 mp4
cut small06 portrait_960p16 25 mp4
cut small07 portrait_960p16 29 mp4
cut small08 portrait_960p16 33 mp4
cut small09 portrait_960p16 37 mp4
cut small10 portrait_960p16 41 mp4
cut small11 portrait_960p16 45 mp4
cut small12 portrait_960p16 49 mp4
cut small13 portrait_960p16 52 mp4
cut small14 portrait_960p16 55 mp4
