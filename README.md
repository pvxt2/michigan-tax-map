# Michigan property tax map

An interactive map of estimated property tax across Michigan. It works on phones, tablets and computers.

- **Whole state:** counties are colored by their typical (area-weighted average) rate.
- **Zoomed in:** cities and townships appear, then every tax area (city or township × school district × village).
- **Roads** come from the basemap and follow a hierarchy. Interstates show first, then highways, county roads and finally local streets, each widening as you zoom in.
- **Controls:** enter a property value and pick homestead or non-homestead; every area recolors instantly.
- **Details:** tap any area for its breakdown.
- **Search** for a place by name.
- **Sharing:** the web address keeps the current view, so links can be shared.

The site is plain files with no server code. GitHub builds it and uploads it to Bluehost.

## How it works

```
Treasury rates PDF ─┐
State boundaries ───┼─► build on GitHub ─► site/ ─► upload to Bluehost
Protomaps basemap ──┘
```

| Step | Script | What it does |
|---|---|---|
| 1 | `pipeline/fetch_boundaries.py` | Downloads counties, cities and townships, villages and school districts from the State of Michigan's map service |
| 2 | `pipeline/parse_rates.py` | Reads Treasury's *Total Property Tax Rates in Michigan* PDF into a table |
| 3 | `pipeline/build_layers.py` | Matches each rate row to its city or township, school district and village, and builds the map layers. It also writes a match report |
| 4 | `pipeline/make_tiles.sh` | Packs the layers into one map file, `tax.pmtiles` |
| 5 | `pipeline/fetch_basemap.sh` | Cuts Michigan out of the free Protomaps world map into `basemap.pmtiles` (once a month) |
| 6 | `pipeline/vendor.sh` | Copies the map library (MapLibre) and label fonts into the site |

The page itself is `site/index.html`, `site/app.js` (controls) and `site/style.js` (colors, zoom levels, road hierarchy).

## One-time setup

### 1. Bluehost: make the subdomain

1. In Bluehost, open **cPanel → Domains** and create the subdomain (for example `taxmap.yoursite.com`).
2. Note its **document root**, the folder it serves from (for example `/home/youruser/taxmap.yoursite.com` or `/home/youruser/public_html/taxmap`).
3. Make sure SSL is on for the subdomain (Bluehost does this automatically, but it can take a few minutes).

### 2. Bluehost: a login GitHub can upload with

Choose one of these:

- **SSH/SFTP (recommended).** In cPanel, open **SSH Access** and turn it on. GitHub then uploads with your cPanel username and password.
- **FTP account.** In cPanel, open **FTP Accounts** and create an account limited to the subdomain's folder. GitHub then uploads over encrypted FTP (FTPS).

### 3. GitHub: add the Bluehost login as secrets

In this repository, go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret | Value |
|---|---|
| `BLUEHOST_HOST` | your server name, as shown in cPanel (for example `box1234.bluehost.com`) or your domain |
| `BLUEHOST_USER` | your cPanel username (SFTP) or the FTP account's full username |
| `BLUEHOST_PASSWORD` | the matching password |
| `BLUEHOST_PATH` | the subdomain's folder from step 1. For an FTP account limited to that folder, use `/` |
| `BLUEHOST_PROTOCOL` | only if you chose FTP: `ftps` (leave it out for SFTP) |
| `BLUEHOST_PORT` | only if Bluehost gives you a port other than 22 (SFTP) or 21 (FTP) |

GitHub encrypts secrets, and nobody can read them back, including you.

## Building and publishing

1. Open the **Actions** tab, then **Build and deploy**.
2. Click **Run workflow**, then **Run workflow** again.

The first run takes longer, roughly 30–60 minutes, because it builds the mapping tools and the basemap. Later runs reuse both.

When it finishes, the run page shows the **data match report**, and the site is live on your subdomain. If the Bluehost secrets aren't set yet, the run skips the upload. You can then download the finished site (**site** under Artifacts) and upload it yourself with FileZilla.

Changing a file in `site/` and committing it re-uploads just the page files within a minute or two. The data stays as it is.

## Every year: new rates

1. Treasury posts the new *Total Property Tax Rates* report on its [millage rates page](https://www.michigan.gov/taxes/property/estimator/related/millage-rates).
2. Copy the PDF's link into `rates_pdf_url` in `config.json` and change `year`.
3. Commit the change, then run **Build and deploy**.

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
| `year`, `rates_pdf_url` | The rates report to use |
| `boundaries_service`, `boundary_layers` | Where the state boundaries come from |
| `basemap.bbox`, `basemap.maxzoom` | Area and detail of the basemap. Zoom 14 shows every street. Zoom 15 roughly doubles the file size for little visible gain |
| `default_value` | Property value shown on first visit |
| `sliver_m2` | Boundary slivers smaller than this (square metres) are ignored |

## Estimates, not bills

Tax = SEV × total mills ÷ 1,000, where SEV is half the value entered. The map uses Treasury's total rates without special assessments and assumes taxable value equals SEV. Actual bills differ. The full disclaimer is on the page.

## Credits

- **Millage rates:** Michigan Department of Treasury.
- **Boundaries:** Michigan Geographic Framework (State of Michigan).
- **Basemap:** [Protomaps](https://protomaps.com), built from [OpenStreetMap](https://www.openstreetmap.org/copyright) data © OpenStreetMap contributors.
- **Map library:** [MapLibre GL JS](https://maplibre.org).
