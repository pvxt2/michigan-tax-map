#!/usr/bin/env bash
# Cut Michigan out of the newest Protomaps daily world build: site/data/basemap.pmtiles.
# Only the needed byte ranges are downloaded, not the whole world file.
set -euo pipefail
cd "$(dirname "$0")/.."
BBOX=$(python3 -c "import json;print(','.join(map(str,json.load(open('config.json'))['basemap']['bbox'])))")
MAXZ=$(python3 -c "import json;print(json.load(open('config.json'))['basemap']['maxzoom'])")
mkdir -p site/data
for i in $(seq 0 14); do
  D=$(date -u -d "-$i day" +%Y%m%d)
  URL="https://build.protomaps.com/$D.pmtiles"
  if curl -sfI "$URL" >/dev/null; then
    echo "Using Protomaps build $D"
    pmtiles extract "$URL" site/data/basemap.pmtiles --bbox="$BBOX" --maxzoom="$MAXZ"
    echo "$D" > site/data/basemap-build.txt
    ls -lh site/data/basemap.pmtiles
    exit 0
  fi
done
echo "No Protomaps daily build found in the last 15 days" >&2
exit 1
