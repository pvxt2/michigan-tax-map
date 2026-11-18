#!/usr/bin/env bash
# Copy the map libraries and label fonts into the site, so it loads nothing from other servers.
set -euo pipefail
cd "$(dirname "$0")/.."
TMP=$(mktemp -d)
( cd "$TMP" && npm init -y >/dev/null && npm install --no-audit --no-fund maplibre-gl@^5 pmtiles@^4 >/dev/null )
mkdir -p site/vendor
cp "$TMP/node_modules/maplibre-gl/dist/maplibre-gl.js" site/vendor/
cp "$TMP/node_modules/maplibre-gl/dist/maplibre-gl.css" site/vendor/
# pmtiles.js is the browser build that defines the global "pmtiles".
cp "$TMP/node_modules/pmtiles/dist/pmtiles.js" site/vendor/pmtiles.js
node -e "for (const p of ['maplibre-gl','pmtiles']) console.log(p, require('$TMP/node_modules/'+p+'/package.json').version)" > site/vendor/VERSIONS.txt

# Fonts (glyph files) from Protomaps' basemap assets.
git clone --depth 1 --filter=blob:none --sparse https://github.com/protomaps/basemaps-assets "$TMP/assets" >/dev/null 2>&1
( cd "$TMP/assets" && git sparse-checkout set "fonts/Noto Sans Regular" "fonts/Noto Sans Medium" "fonts/Noto Sans Italic" )
rm -rf site/fonts && mkdir -p site/fonts
cp -r "$TMP/assets/fonts/"* site/fonts/
rm -rf "$TMP"
cat site/vendor/VERSIONS.txt
