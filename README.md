# Michigan property tax map

An interactive map of estimated property tax across Michigan. It works on phones, tablets and computers.

- **Whole state:** counties are colored by their typical (area-weighted average) rate.
- **Zoomed in:** cities and townships appear, then every tax area (city or township × school district × village).
- **Roads** come from the basemap and follow a hierarchy. Interstates show first, then highways, county roads and finally local streets, each widening as you zoom in.
- **Controls:** enter a property value and pick homestead or non-homestead; every area recolors instantly.
- **Details:** tap any area for its breakdown.
- **Search** for a place by name.
- **Sharing:** the web address keeps the current view, so links can be shared.

The site is plain files with no server code. GitHub builds it, and you upload the result to Bluehost.

## How it works

```
Treasury rates PDF ─┐
State boundaries ───┼─► build on GitHub ─► download zip ─► upload to Bluehost
Protomaps basemap ──┘
```

| Step | Script | What it does |
|---|---|---|
| 1 | `pipeline/fetch_boundaries.py` | Downloads counties, cities and townships, villages and school districts from the State of Michigan's map service |
| 2 | `pipeline/parse_rates.py` | Reads Treasury's *Total Property Tax Rates in Michigan* PDF (saved in `data/rates`) into a table |
| 3 | `pipeline/build_layers.py` | Matches each rate row to its city or township, school district and village, and builds the map layers. It also writes a match report |
| 4 | `pipeline/make_tiles.sh` | Packs the layers into one map file, `tax.pmtiles` |
| 5 | `pipeline/fetch_basemap.sh` | Cuts two files from the free Protomaps world map (once a year): `basemap-overview.pmtiles` for the zoomed-out view of Michigan and its neighbours, and `basemap.pmtiles` with street detail for a band around Michigan, kept under 480 MB |
| 6 | `pipeline/vendor.sh` | Copies the map library (MapLibre) and label fonts into the site |

The page itself is `site/index.html`, `site/app.js` (controls) and `site/style.js` (colors, zoom levels, road hierarchy).

## Building

1. Open the **Actions** tab, then **Build site**.
2. Click **Run workflow**, then **Run workflow** again.

The first run takes longer, roughly 30–60 minutes, because it builds the mapping tools and the basemap. Later runs reuse both.

When it finishes, the run page shows the **data match report** and, under **Artifacts**, one or two downloads:

- **site-update** (under 100 MB): the page, the tax map file, the overview basemap and everything else. You upload it every time.
- **basemap** (under 480 MB): street-level roads, water and place names for Michigan. It is only included when it is new, which happens on the first run and then once a year. Tick **Include the basemap file** when starting a run if you ever need it again.

GitHub never connects to your Bluehost account. You download the files and upload them yourself.

## Publishing on Bluehost

**First time: make the subdomain**

1. In Bluehost, open **cPanel → Domains** and create the subdomain (for example `taxmap.yoursite.com`).
2. Note its **document root**, the folder it serves from.
3. Make sure SSL is on for the subdomain (Bluehost does this automatically, but it can take a few minutes).

**Each time: upload**

1. Download **site-update** (and **basemap** if the run has one) from the run page. Don't unzip them.
2. In cPanel, open **File Manager** and go to the subdomain's folder.
3. Click **Upload** and upload the zip file.
4. Back in File Manager, right-click the zip, choose **Extract**, and extract into the same folder. Say yes to replacing the existing files.
5. Delete the zip.
6. Do the same with the basemap zip if you have one. It extracts into the `data` folder by itself.

The site includes a hidden file, `.htaccess`, which stops Bluehost from compressing the map files (compression breaks them). To see it in File Manager, use **Settings → Show Hidden Files**.

Both zips stay under File Manager's 500 MB upload limit. If the street-level basemap would go over 480 MB, the build drops its most detailed zoom level to fit.

**Check it:** open the subdomain in a browser. If the map stays blank, check that `data/tax.pmtiles`, `data/basemap-overview.pmtiles`, `data/basemap.pmtiles` and `.htaccess` are all in the subdomain folder.

## Every year: new rates

1. Download the new *Total Property Tax Rates* report from Treasury's [millage rates page](https://www.michigan.gov/taxes/property/estimator/related/millage-rates).
2. In this repository, open the `data/rates` folder, choose **Add file → Upload files**, and upload it named for its year (for example `2026.pdf`).
3. In `config.json`, change `year` and `rates_pdf` to match (for example `"year": 2026` and `"rates_pdf": "data/rates/2026.pdf"`).
4. Run **Build site**, then upload **site-update** to Bluehost.

The build reads the PDF saved in the repository, because michigan.gov doesn't reliably allow automated downloads. It only falls back to downloading `rates_pdf_url` when no saved file exists.

## The match report

Treasury lists school districts by shortened names (for example `WHITMORE LAKE PUB SC`), so the build matches them to the state's school district map by name, one city or township at a time. The report on each run says how many matched. The **match-report** download has the details:

- `areas_without_rates.csv`: areas on the map without a rate. They draw in gray.
- `treasury_rows_not_on_map.csv`: rate rows that didn't land anywhere.
- `unmatched_cities_townships.csv` and `treasury_units_without_boundary.csv`: city and township name mismatches.
- `villages_using_township_rate.csv`: village areas where no village row was found.

To fix a school-district mismatch by hand, add a line to `data/overrides.csv` with the city or township code, the school name exactly as Treasury prints it, and the district code. Then rerun the build. The build stops rather than publishing if less than 80% of the state's area gets a rate.

## Settings (`config.json`)

| Setting | Meaning |
|---|---|
| `year`, `rates_pdf` | The rates report to use (a PDF saved in `data/rates`); `rates_pdf_url` is only a fallback |
| `boundaries_service`, `boundary_layers` | Where the state boundaries come from |
| `basemap.bbox`, `basemap.maxzoom` | Area of the overview basemap, and the most detailed zoom of the street-level one (14 shows every street; the build lowers it if the file would pass 480 MB) |
| `default_value` | Property value shown on first visit |
| `sliver_m2` | Boundary slivers smaller than this (square metres) are ignored |

## Estimates, not bills

Tax = SEV × total mills ÷ 1,000, where SEV is half the value entered. The map uses Treasury's total rates without special assessments and assumes taxable value equals SEV. Actual bills differ. The full disclaimer is on the page.

## Credits

- **Millage rates:** Michigan Department of Treasury.
- **Boundaries:** Michigan Geographic Framework (State of Michigan).
- **Basemap:** [Protomaps](https://protomaps.com), built from [OpenStreetMap](https://www.openstreetmap.org/copyright) data © OpenStreetMap contributors.
- **Map library:** [MapLibre GL JS](https://maplibre.org).
