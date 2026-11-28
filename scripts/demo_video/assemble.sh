#!/bin/sh
# Put a voice-over on the silent demo video: ./assemble.sh voice.m4a
# Writes Praecedens_demo.mp4 next to this script from Praecedens_demo_silent.mp4.
set -eu
dir=$(cd "$(dirname "$0")" && pwd)
voice=${1:?usage: assemble.sh VOICE_FILE (e.g. voice.m4a)}
length=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$dir/Praecedens_demo_silent.mp4")
ffmpeg -y -loglevel error -i "$dir/Praecedens_demo_silent.mp4" -i "$voice" \
  -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -af apad -t "$length" -movflags +faststart \
  "$dir/Praecedens_demo.mp4"
echo "wrote $dir/Praecedens_demo.mp4"
