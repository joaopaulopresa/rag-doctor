#!/usr/bin/env bash
# Records the three demo videos from the running Docker Compose stack, then converts them.
#
#   docker compose up -d && bash e2e/demo/record.sh
#
# The application's data is reset first (the model cache is kept), so every recording starts
# from the same state; a second recording costs nothing because every model call is cached.
set -euo pipefail
cd "$(dirname "$0")/../.."
out=e2e/demo/output
media=docs/media

docker compose exec -T api ragdoctor reset --yes
docker compose exec -T api ragdoctor bootstrap
rm -rf "$out"
npx playwright test --project=demo

mkdir -p "$media"
for name in chat doctor external; do
  ffmpeg -y -loglevel error -i "$out/$name.webm" \
    -c:v libx264 -pix_fmt yuv420p -crf 23 -preset slow -movflags +faststart "$media/$name.mp4"
done

# Hero animation: the first chat question, its answer and the cited passage, cut at the marks
# the chat demo wrote.
read -r start length < <(python3 -c "
import json; m = json.load(open('$out/chat.marks.json'))
print(round(m['hero_start'] + 0.3, 2), round(m['hero_end'] - m['hero_start'] - 0.3, 2))")
filters="fps=12,scale=960:-1:flags=lanczos"
ffmpeg -y -loglevel error -ss "$start" -t "$length" -i "$out/chat.webm" \
  -vf "$filters,palettegen=stats_mode=diff" "$out/palette.png"
ffmpeg -y -loglevel error -ss "$start" -t "$length" -i "$out/chat.webm" -i "$out/palette.png" \
  -lavfi "$filters [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" "$media/hero.gif"
if command -v gifsicle >/dev/null; then
  gifsicle -O3 --lossy=40 -b "$media/hero.gif"
fi
cp "$out"/screens/*.png "$media/"
ls -la "$media"
