#!/usr/bin/env bash
# Turn the GeoJSON layers into one map-tile file: site/data/tax.pmtiles.
# Each feature carries its own zoom range (written by build_layers.py).
set -euo pipefail
cd "$(dirname "$0")/.."
L=work/layers
mkdir -p site/data
tippecanoe -o site/data/tax.pmtiles --force \
  -Z4 -z14 \
  --detect-shared-borders \
  --no-tile-size-limit --no-feature-limit \
  -r1 -P \
  --name="Michigan property tax areas" \
  --attribution="Michigan Department of Treasury; Michigan Geographic Framework" \
  -L counties:$L/counties.geojsonl \
  -L munis:$L/munis.geojsonl \
  -L areas:$L/areas.geojsonl \
  -L villages:$L/villages.geojsonl \
  -L county_labels:$L/county_labels.geojsonl \
  -L muni_labels:$L/muni_labels.geojsonl \
  -L school_labels:$L/school_labels.geojsonl \
  -L area_labels:$L/area_labels.geojsonl
ls -lh site/data/tax.pmtiles
