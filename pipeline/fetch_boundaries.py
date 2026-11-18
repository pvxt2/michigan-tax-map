"""Download the Michigan Geographic Framework boundary layers as GeoJSON.

Uses the State of Michigan ArcGIS MapServer listed in config.json. Features are
fetched in batches of object IDs, which works even where the server does not
support paging.

Usage: python pipeline/fetch_boundaries.py [outdir]   (default: work/raw)
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text())
BATCH = 100


def get_json(url, params, tries=5):
    data = urllib.parse.urlencode(params).encode()
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "michigan-tax-map-build"})
            with urllib.request.urlopen(req, timeout=180) as r:
                out = json.loads(r.read().decode("utf-8"))
            if "error" in out:
                raise RuntimeError(out["error"])
            return out
        except Exception as e:  # noqa: BLE001 - retry anything, then give up
            if attempt == tries - 1:
                raise
            wait = 5 * (attempt + 1)
            print(f"  retrying in {wait}s after: {e}", flush=True)
            time.sleep(wait)


def fetch_layer(layer_id):
    base = f"{CFG['boundaries_service']}/{layer_id}/query"
    ids = get_json(base, {"where": "1=1", "returnIdsOnly": "true", "f": "json"})["objectIds"] or []
    ids.sort()
    feats = []
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        fc = get_json(base, {
            "objectIds": ",".join(map(str, chunk)),
            "outFields": "*",
            "outSR": "4326",
            "returnGeometry": "true",
            "geometryPrecision": "6",
            "f": "geojson",
        })
        feats.extend(fc.get("features", []))
        print(f"  {len(feats)}/{len(ids)}", flush=True)
    return {"type": "FeatureCollection", "features": feats}


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "work" / "raw"
    out.mkdir(parents=True, exist_ok=True)
    for name, layer_id in CFG["boundary_layers"].items():
        print(f"Downloading {name} (layer {layer_id})", flush=True)
        fc = fetch_layer(layer_id)
        if not fc["features"]:
            sys.exit(f"No features returned for {name}")
        (out / f"{name}.geojson").write_text(json.dumps(fc))
        print(f"  saved {len(fc['features'])} features", flush=True)


if __name__ == "__main__":
    main()
