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

cut() { # index, clip, seconds in, extension [more of ffmpeg's options, before its input]
    out="mix$1_$2.$4"; in=$2; at=$3; shift 4
    [ -s "$out" ] && return
    ffmpeg -nostdin -v error -y "$@" -ss "$at" -i "$in.mp4" -c copy "$out" && echo "made $out" || echo "CUT FAILED $out"
}

cut 00 h264_1080p30 5 mp4
cut 01 h264_1080p30 17 mp4
cut 02 h264_1080p24 3 mkv
cut 03 h264_1080p24 23 mkv
cut 04 h264_720p30 7 mp4
cut 05 h264_720p30 29 mp4
cut 06 h264_720p30 11 mp4
cut 07 phone_1080p30 2 mp4 -display_rotation 90
cut 08 phone_1080p30 19 mp4 -display_rotation 90
cut 09 h264_1080p60_nob 13 mp4
cut 10 hevc10_1080p30 5 mp4
cut 11 hevc10_1080p30 21 mp4
cut 12 h264_2160p30 9 mp4
cut 13 h264_1080p60 31 mp4
cut 14 hevc_1080p60 15 mp4
cut 15 h264_540p60 4 mp4
