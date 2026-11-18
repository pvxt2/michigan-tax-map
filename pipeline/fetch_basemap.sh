#!/usr/bin/env bash
# Cut the basemap out of the newest Protomaps daily world build, as two files:
#
#   site/data/basemap-overview.pmtiles  zooms 0-9, the whole rectangle in config.json
#       (Michigan plus the neighbouring states and lakes). Small; it also fills in
#       land and water beyond the detailed area when zoomed in.
#   site/data/basemap.pmtiles           zooms 10-14 (13 if needed to stay under the size
#       limit), only a band around Michigan (work/region.geojson, from build_layers.py).
#       Kept under 480 MB so it uploads through cPanel's File Manager.
#
# Only the needed byte ranges are downloaded, not the whole world file.
set -euo pipefail
cd "$(dirname "$0")/.."
BBOX=$(python3 -c "import json;print(','.join(map(str,json.load(open('config.json'))['basemap']['bbox'])))")
MAXZ=$(python3 -c "import json;print(json.load(open('config.json'))['basemap']['maxzoom'])")
LIMIT_MB=480
REGION=work/region.geojson
[ -f "$REGION" ] || { echo "Missing $REGION (made by build_layers.py)" >&2; exit 1; }
mkdir -p site/data

URL=""
for i in $(seq 0 14); do
  D=$(date -u -d "-$i day" +%Y%m%d)
  if curl -sfI "https://build.protomaps.com/$D.pmtiles" >/dev/null; then URL="https://build.protomaps.com/$D.pmtiles"; break; fi
done
[ -n "$URL" ] || { echo "No Protomaps daily build found in the last 15 days" >&2; exit 1; }
echo "Using Protomaps build $D"

pmtiles extract "$URL" site/data/basemap-overview.pmtiles --bbox="$BBOX" --maxzoom=9

for Z in $(seq "$MAXZ" -1 12); do
  pmtiles extract "$URL" site/data/basemap.pmtiles --region="$REGION" --minzoom=10 --maxzoom="$Z"
  MB=$(( $(stat -c %s site/data/basemap.pmtiles) / 1048576 ))
  echo "Detailed basemap to zoom $Z: ${MB} MB"
  if [ "$MB" -le "$LIMIT_MB" ]; then break; fi
  if [ "$Z" -le 12 ]; then echo "Basemap is still over ${LIMIT_MB} MB at zoom 12" >&2; exit 1; fi
  echo "Over ${LIMIT_MB} MB; trying one zoom level less"
done

echo "$D z$Z" > site/data/basemap-build.txt
ls -lh site/data/basemap-overview.pmtiles site/data/basemap.pmtiles
