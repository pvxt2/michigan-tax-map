"""Join Treasury millage rates to the state boundary layers and write map layers.

Inputs (from earlier steps):
    work/raw/{counties,mcd,villages,schools}.geojson   fetch_boundaries.py
    work/rates.csv                                     parse_rates.py
    data/overrides.csv                                 optional manual matches

Outputs:
    work/layers/*.geojsonl     one GeoJSON feature per line, with tippecanoe zoom ranges
    site/data/meta.json        color scale domain, year, counts
    site/data/search.json      place search index
    work/qa/*                  match reports (also shown in the GitHub job summary)

How a tax area is built:
    city/township (split at county lines) x school district x village
Each piece takes the Treasury row for its city or township and school district,
or the village row when it lies in a village. Thin slivers that come from
boundary layers not lining up exactly, and that have no Treasury row, are merged
into the neighbouring area of the same city or township.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import make_valid
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text())
RAW = ROOT / "work" / "raw"
OUT = ROOT / "work" / "layers"
QA = ROOT / "work" / "qa"
SITE_DATA = ROOT / "site" / "data"
METRIC = 3078  # Michigan Oblique Mercator (metres)
SLIVER = float(CFG.get("sliver_m2", 40000))
MIN_RATED_SHARE = 0.80

# ----------------------------------------------------------------------------- names

def norm(s):
    s = (s or "").upper().replace("&", " AND ")
    s = re.sub(r"\bST\.?\s", "ST ", s + " ")
    s = re.sub(r"\bSAINT\b", "ST", s)
    s = re.sub(r"\bMOUNT\b", "MT", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return " ".join(s.split())


UNIT_WORDS = {"CHARTER", "TOWNSHIP", "TWP", "CITY", "OF", "THE", "VILLAGE"}


def unit_norm(s):
    n = re.sub(r"\bA MICHIGAN( CITY)?$", "", norm(s)).strip()  # "... Grosse Pointe Shores, a Michigan City"
    words = n.split()
    if words and words[-1] in ("CIT", "CI"):  # name cut off in the report, e.g. "... Village Cit"
        words = words[:-1]
    return " ".join(w for w in words if w not in UNIT_WORDS)


SCHOOL_PREFIX = re.compile(r"^(THE )?(SCHOOL DISTRICT OF (THE )?(CITY OF )?|PUBLIC SCHOOLS OF (THE )?(CITY OF )?|CITY OF |THE )")
# Treasury rows for part of a district with its own debt or college millage, e.g.
# "YPSILANTI SD (WILLOW R", "SHEPHERD SD W/MCC", "JEFFERSON SCHOOLS - R".
QUALIFIED = re.compile(r"\(|\bW/|\s-\s?[A-Z]+$|-[A-Z]$|\bDEBT\b")


def school_norm(s):
    return SCHOOL_PREFIX.sub("", norm(s)).strip()


def school_score(label, sd_name):
    a, b = school_norm(label), school_norm(sd_name)
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b[:len(a)]).ratio()
    fa, fb = a.split()[0], b.split()[0]
    first = 1.0 if fa == fb else (0.6 if fa.startswith(fb) or fb.startswith(fa) else 0.0)
    penalty = 0.08 if QUALIFIED.search((label or "").upper()) else 0.0
    return 0.65 * ratio + 0.35 * first - penalty


def same_district(label_a, label_b):
    """Two Treasury labels for the same district (one usually qualified), e.g.
    YPSILANTI SCHOOL DISTR / YPSILANTI SD (WILLOW R."""
    a, b = school_norm(label_a).split(), school_norm(label_b).split()
    return bool(a and b and a[0] == b[0])


SMALL = {"of", "and", "the", "at"}
KEEP_UPPER = {"ISD", "RESA", "ESA", "II", "III"}


def nice(s):
    if not s or not s.isupper():
        return s
    out = []
    for i, w in enumerate(s.split()):
        if w in KEEP_UPPER:
            out.append(w)
        elif i and w.lower() in SMALL:
            out.append(w.lower())
        else:
            out.append("-".join(p[:1] + p[1:].lower() for p in w.split("-")))
    return " ".join(out)


def unit_display(treasury_name, utype):
    base = re.sub(r"\s+(Twp|Township|City)$", "", treasury_name.strip(), flags=re.I)
    base = nice(base) if base.isupper() else base
    return f"City of {base}" if utype == "C" else f"{base} Township"


# ----------------------------------------------------------------------------- io

def only_polygons(geom):
    """Repair a geometry and keep just its polygon parts (repairs can return mixed collections)."""
    if geom is None or geom.is_empty:
        return None
    geom = make_valid(geom)
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    parts = [p for p in getattr(geom, "geoms", []) if p.geom_type in ("Polygon", "MultiPolygon")]
    return unary_union(parts) if parts else None


LOAD_NOTES = []


def load(name):
    g = gpd.read_file(RAW / f"{name}.geojson")
    if g.crs is None:
        g = g.set_crs(4326)
    # Some framework layers carry more than one version of each boundary (LAYOUT field).
    # Keep the cartographic one, or the most common one.
    lay = next((c for c in g.columns if c.upper() == "LAYOUT"), None)
    fips = next((c for c in g.columns if c.upper() == "FIPSCODE"), None)
    versions = bool(lay and fips and g[lay].nunique() > 1 and g.groupby(fips)[lay].nunique().max() > 1)
    if versions:
        vals = g[lay].value_counts()
        keep = next((v for v in vals.index if "CART" in str(v).upper()), vals.index[0])
        LOAD_NOTES.append(f"{name}: LAYOUT values {dict(vals)}; kept {keep!r}")
        g = g[g[lay] == keep]
    g = g.to_crs(METRIC)
    g["geometry"] = [only_polygons(x) for x in g.geometry]
    return g[g.geometry.notna()]


def col(g, *names):
    for n in names:
        for c in g.columns:
            if c.upper() == n.upper():
                return c
    raise KeyError(f"None of {names} in {list(g.columns)}")


def polys(g):
    g = g[g.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    return g[g.area > 1]


def write_seq(g, path, layer, minzoom, maxzoom, props):
    g = g.to_crs(4326)
    with path.open("w") as f:
        for _, r in g.iterrows():
            if r.geometry is None or r.geometry.is_empty:
                continue
            p = {}
            for k in props:
                v = r[k]
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    continue
                if isinstance(v, (np.integer,)):
                    v = int(v)
                elif isinstance(v, (float, np.floating)):
                    v = round(float(v), 4)
                p[k] = v
            f.write(json.dumps({"type": "Feature", "properties": p,
                                "geometry": r.geometry.__geo_interface__,
                                "tippecanoe": {"layer": layer, "minzoom": minzoom, "maxzoom": maxzoom}}) + "\n")


def label_points(g):
    pts = g.copy()
    pts["geometry"] = g.geometry.representative_point()
    return pts


# ----------------------------------------------------------------------------- main

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    report = []

    rates = pd.read_csv(ROOT / "work" / "rates.csv", dtype=str, keep_default_na=False)
    for c in ("pre", "nh"):
        rates[c] = rates[c].astype(float)
    rates["is_village"] = rates["is_village"].astype(int)
    rates["dup"] = rates["dup"].astype(int)

    # Counties: Treasury county codes (01 Alcona ... 83 Wexford) are matched by name.
    counties = polys(load("counties"))
    cname_col = col(counties, "NAME")
    tr_counties = {unit_norm(n): c for c, n in rates[["county_code", "county_name"]].drop_duplicates().values if n}
    alpha = sorted(counties[cname_col].map(lambda n: norm(n).replace("ST ", "SAINT ")).unique())
    counties["ccode"] = counties[cname_col].map(
        lambda n: tr_counties.get(unit_norm(n)) or f"{alpha.index(norm(n).replace('ST ', 'SAINT ')) + 1:02d}")
    counties["cname"] = counties[cname_col].map(nice)
    counties = counties.dissolve(by=["ccode", "cname"], as_index=False)[["ccode", "cname", "geometry"]]
    report.append(f"Counties: {len(counties)}")

    # Area for the detailed basemap: Michigan plus a 6 km band (see fetch_basemap.sh).
    region = counties.geometry.union_all().buffer(6000).simplify(500)
    gpd.GeoDataFrame(geometry=[region], crs=METRIC).to_crs(4326).to_file(ROOT / "work" / "region.geojson", driver="GeoJSON")

    # Cities and townships, split at county lines.
    mcd = polys(load("mcd"))
    m_name, m_type = col(mcd, "NAME"), col(mcd, "TYPE")
    m_label = col(mcd, "LABEL")
    mcd["mtype"] = [("C" if "CITY" in f"{t} {l}".upper() else "T") for t, l in zip(mcd[m_type], mcd[m_label])]
    report.append("MCD TYPE values: " + ", ".join(f"{k} ({v})" for k, v in mcd[m_type].value_counts().items()))
    mcd["mkey"] = mcd[m_name].map(unit_norm)
    mcd["mlabel"] = mcd[m_label].fillna(mcd[m_name])
    pieces = gpd.overlay(mcd[["mkey", "mtype", "mlabel", "geometry"]], counties, how="intersection", keep_geom_type=True)
    pieces = pieces[pieces.area > SLIVER]

    units = rates.groupby("unit_code").first().reset_index()[["unit_code", "county_code", "unit_name", "unit_type"]]
    units["ukey"] = units["unit_name"].map(unit_norm)
    by_exact = {(r.county_code, r.ukey, r.unit_type): r.unit_code for r in units.itertuples()}
    by_name = defaultdict(list)
    for r in units.itertuples():
        by_name[(r.county_code, r.ukey)].append(r.unit_code)

    def match_unit(ccode, key, mtype):
        if (ccode, key, mtype) in by_exact:
            return by_exact[(ccode, key, mtype)]
        if len(by_name.get((ccode, key), [])) == 1:
            return by_name[(ccode, key)][0]
        pref = [u for (c, k), us in by_name.items() if c == ccode and len(k) >= 8 and len(key) >= 8
                and (k.startswith(key) or key.startswith(k)) for u in us]
        if len(pref) == 1:
            return pref[0]
        cands = units[(units.county_code == ccode) & (units.unit_type == mtype)]
        best, score = None, 0
        for r in cands.itertuples():
            s = SequenceMatcher(None, key, r.ukey).ratio()
            if s > score:
                best, score = r.unit_code, s
        return best if score >= 0.85 else None

    pieces["uid"] = [match_unit(c, k, t) for c, k, t in zip(pieces.ccode, pieces.mkey, pieces.mtype)]
    unmatched_mcd = pieces[pieces.uid.isna()]
    unmatched_mcd[["ccode", "cname", "mlabel"]].drop_duplicates().to_csv(QA / "unmatched_cities_townships.csv", index=False)
    pieces["uid"] = pieces["uid"].fillna("X" + pieces["ccode"] + "-" + pieces["mkey"].str.replace(" ", "_"))
    unit_info = units.set_index("unit_code")
    pieces["uname"] = [unit_display(unit_info.loc[u, "unit_name"], unit_info.loc[u, "unit_type"]) if u in unit_info.index
                       else nice(l) for u, l in zip(pieces.uid, pieces.mlabel)]
    pieces["utype"] = [unit_info.loc[u, "unit_type"] if u in unit_info.index else t for u, t in zip(pieces.uid, pieces.mtype)]
    munis = pieces.dissolve(by="uid", as_index=False, aggfunc="first")[["uid", "uname", "utype", "ccode", "cname", "geometry"]]

    # School districts and villages.
    sd = polys(load("schools"))
    sd["dcode"] = sd[col(sd, "DCODE")].astype(str).str.strip()
    sd["sdname"] = sd[col(sd, "NAME")].map(nice)
    sd = sd.dissolve(by="dcode", as_index=False, aggfunc="first")[["dcode", "sdname", "geometry"]]
    vil = polys(load("villages"))
    vil["vname"] = vil[col(vil, "NAME")].map(lambda s: nice(re.sub(r"^village of\s+", "", s or "", flags=re.I)))
    vil = vil.dissolve(by="vname", as_index=False)[["vname", "geometry"]]

    # Villages that have become cities (e.g. Manchester, 2023) are still villages in the boundary
    # layer. When Treasury lists a city with no boundary, use the same-named village in that county.
    vil_c = gpd.sjoin(label_points(vil), counties[["ccode", "geometry"]], how="left", predicate="within")
    vil_c = vil_c[~vil_c.index.duplicated()]
    promoted = []
    for u in sorted(set(units[units.unit_type == "C"].unit_code) - set(munis.uid)):
        info = unit_info.loc[u]
        hit = vil_c[(vil_c.ccode == info.county_code) & (vil_c.vname.map(unit_norm) == unit_norm(info.unit_name))]
        if hit.empty:
            continue
        vg = vil.loc[hit.index[0], "geometry"]
        munis["geometry"] = [g.difference(vg) if g.intersects(vg) else g for g in munis.geometry]
        c = counties[counties.ccode == info.county_code].iloc[0]
        munis = pd.concat([munis, gpd.GeoDataFrame([{"uid": u, "uname": unit_display(info.unit_name, "C"), "utype": "C",
                                                     "ccode": c.ccode, "cname": c.cname, "geometry": vg}], crs=METRIC)],
                          ignore_index=True)
        vil = vil.drop(index=hit.index[0])
        promoted.append(info.unit_name)
    munis = gpd.GeoDataFrame(munis, geometry="geometry", crs=METRIC)
    munis = munis[~munis.geometry.is_empty]
    if promoted:
        report.append("Cities drawn from their former village boundary: " + ", ".join(promoted))
    missing_units = sorted(set(units.unit_code) - set(munis.uid))
    units[units.unit_code.isin(missing_units)].to_csv(QA / "treasury_units_without_boundary.csv", index=False)
    report.append(f"Cities and townships: {len(munis)} on the map, {len(unmatched_mcd[['mlabel','ccode']].drop_duplicates())} "
                  f"without a Treasury match, {len(missing_units)} Treasury units without a boundary")

    areas = gpd.overlay(munis[["uid", "uname", "utype", "ccode", "cname", "geometry"]], sd, how="intersection", keep_geom_type=True)
    areas = gpd.overlay(areas, vil, how="identity", keep_geom_type=True)
    areas = polys(areas).reset_index(drop=True)
    areas["vname"] = areas["vname"].astype(object).where(areas["vname"].notna(), None)
    areas["m2"] = areas.area

    # Overrides: unit_code,label,dcode
    overrides = {}
    ov_path = ROOT / "data" / "overrides.csv"
    if ov_path.exists():
        for r in csv.DictReader(l for l in ov_path.open() if not l.startswith("#")):
            if r.get("unit_code") and r.get("label") and r.get("dcode"):
                overrides[(r["unit_code"].strip(), r["label"].strip().upper())] = r["dcode"].strip()

    # Match Treasury rows to (unit, school district [, village]).
    assigned = {}            # (uid, dcode, vname|None) -> row
    alts = defaultdict(list)  # same key -> other rows for parts of that district
    paired = []
    stars = set()
    unused_rows = []
    for uid, grp in areas.groupby("uid"):
        rows = rates[rates.unit_code == uid]
        if rows.empty:
            continue
        dup_labels = set(rows[rows.dup == 1].label.str.upper())
        rows = rows[rows.dup == 0]
        sch_rows = rows[rows.is_village == 0]
        dcodes = grp.groupby("dcode").agg(sdname=("sdname", "first"), m2=("m2", "sum"))

        def assign(rowset, dmap, vname):
            pairs, used_r, used_d = [], set(), set()
            for ri, r in rowset.iterrows():
                forced = overrides.get((uid, r.label.upper()))
                if forced and forced in dmap.index:
                    assigned[(uid, forced, vname)] = r
                    used_r.add(ri)
                    used_d.add(forced)
                    continue
                for d, info in dmap.iterrows():
                    pairs.append((school_score(r.school_label if "school_label" in r else r.label, info.sdname), ri, d))
            for s, ri, d in sorted(pairs, reverse=True):
                if s < 0.55 or ri in used_r or d in used_d:
                    continue
                assigned[(uid, d, vname)] = rowset.loc[ri]
                used_r.add(ri)
                used_d.add(d)
                if rowset.loc[ri].label.upper() in dup_labels:
                    stars.add((uid, d, vname))
            # Renamed or merged districts: pair what is left over in this city or township.
            left_r = [ri for ri in rowset.index if ri not in used_r]
            left_d = [d for d in dmap.index if d not in used_d]
            if left_r and left_d and (len(left_d) == 1 or len(left_r) == len(left_d)):
                for sc, ri, d in sorted(((school_score(rowset.loc[ri].get("school_label", rowset.loc[ri].label), dmap.loc[d].sdname), ri, d)
                                         for ri in left_r for d in left_d), reverse=True):
                    if ri in used_r or d in used_d:
                        continue
                    assigned[(uid, d, vname)] = rowset.loc[ri]
                    used_r.add(ri)
                    used_d.add(d)
                    paired.append((uid, rowset.loc[ri].label, dmap.loc[d].sdname))
            # Rows for part of an already-matched district (different debt or college millage).
            for ri in [ri for ri in rowset.index if ri not in used_r]:
                r = rowset.loc[ri]
                home = next((k for k, v in assigned.items() if k[0] == uid and k[2] == vname and same_district(v.label, r.label)), None)
                if home:
                    alts[home].append(r)
                else:
                    unused_rows.append(r)

        assign(sch_rows, dcodes, None)

        vrows = rows[rows.is_village == 1].copy()
        vnames = [v for v in grp.vname.dropna().unique()]
        for v in vnames:
            vg = grp[grp.vname == v]
            vd = vg.groupby("dcode").agg(sdname=("sdname", "first"), m2=("m2", "sum"))
            mine = []
            nv = norm(v)
            for ri, r in vrows.iterrows():
                rv = norm(r.get("village", ""))
                if rv:  # village and school come as separate columns
                    if rv == nv or (len(rv) >= 6 and (nv.startswith(rv) or rv.startswith(nv))):
                        r = r.copy()
                        r["school_label"] = r.get("school", "")
                        mine.append((ri, r))
                    continue
                rest = norm(r.label)[len("VILLAGE OF "):]
                if rest.startswith(nv):
                    r = r.copy()
                    r["school_label"] = rest[len(nv):].strip()
                    mine.append((ri, r))
            if not mine:
                continue
            vset = pd.DataFrame([r for _, r in mine], index=[ri for ri, _ in mine])
            vrows = vrows.drop(vset.index)
            if len(vset) == 1 and len(vd) == 1:
                assigned[(uid, vd.index[0], v)] = vset.iloc[0]
            else:
                assign(vset, vd, v)
        unused_rows.extend(r for _, r in vrows.iterrows())

    def lookup(r):
        has_v = isinstance(r.vname, str) and r.vname != ""
        row = assigned.get((r.uid, r.dcode, r.vname)) if has_v else None
        vil_rate = row is not None
        if row is None:
            row = assigned.get((r.uid, r.dcode, None))
        if row is None:
            return pd.Series({"h": np.nan, "n": np.nan, "vrate": 0, "star": 0, "alt": None})
        key = (r.uid, r.dcode, r.vname if vil_rate else None)
        alt = ";".join(f"{nice(a.label)}|{a.pre}|{a.nh}" for a in alts.get(key, [])) or None
        return pd.Series({"h": row.pre, "n": row.nh, "vrate": int(vil_rate), "star": int(key in stars), "alt": alt})

    areas = pd.concat([areas, areas.apply(lookup, axis=1)], axis=1)
    areas = gpd.GeoDataFrame(areas, geometry="geometry", crs=METRIC)

    # Merge unrated slivers into the neighbouring rated area of the same city or township.
    unit_m2 = areas.groupby("uid").m2.sum()
    rated = areas[areas.h.notna()]
    sidx = rated.sindex
    absorbed = 0
    for i, r in areas[areas.h.isna()].iterrows():
        if r.m2 >= 1_000_000 and r.m2 >= 0.03 * unit_m2[r.uid]:
            continue
        probe = r.geometry.buffer(5)
        cand = rated.iloc[sidx.query(probe, predicate="intersects")]
        same = cand[cand.uid == r.uid]
        cand = same if len(same) else cand
        if cand.empty:
            continue
        best = max(cand.index, key=lambda j: probe.intersection(cand.at[j, "geometry"].boundary).length)
        for k in ("uid", "uname", "utype", "ccode", "cname", "dcode", "sdname", "vname", "h", "n", "vrate", "star", "alt"):
            areas.at[i, k] = areas.at[best, k]
        absorbed += 1

    areas["vkey"] = areas["vname"].fillna("")
    areas = areas.dissolve(by=["uid", "dcode", "vkey"], as_index=False, aggfunc="first")
    areas["m2"] = areas.area
    areas["km2"] = areas.m2 / 1e6
    areas["vname"] = areas["vkey"].astype(object).where(areas["vkey"] != "", None)
    areas = areas.sort_values(["ccode", "uid", "dcode", "vkey"]).reset_index(drop=True)
    areas["id"] = np.arange(1, len(areas) + 1)

    rated_share = areas.loc[areas.h.notna(), "m2"].sum() / areas.m2.sum()
    unrated = areas[areas.h.isna()]
    unrated[["uid", "uname", "cname", "dcode", "sdname", "vname", "km2"]].to_csv(QA / "areas_without_rates.csv", index=False)
    pd.DataFrame(unused_rows).to_csv(QA / "treasury_rows_not_on_map.csv", index=False)
    vil_fallback = areas[areas.vname.notna() & (areas.vrate == 0) & areas.h.notna()]
    vil_fallback[["uname", "cname", "vname", "sdname"]].to_csv(QA / "villages_using_township_rate.csv", index=False)
    report += [
        f"Tax areas: {len(areas)} ({absorbed} slivers merged, {len(paired)} renamed or merged districts paired)",
        f"Area with a rate: {rated_share:.1%}",
        f"Areas without a rate: {len(unrated)} (see areas_without_rates.csv)",
        f"Treasury rows not placed on the map: {len(unused_rows)} (see treasury_rows_not_on_map.csv)",
        f"Village areas using the township rate: {len(vil_fallback)}",
    ]

    # Summaries for the zoomed-out layers: area-weighted averages, with the range inside.
    def summarize(group_col):
        r = areas[areas.h.notna()]
        g = r.groupby(group_col)
        out = pd.DataFrame({
            "h": g.apply(lambda d: np.average(d.h, weights=d.m2)),
            "n": g.apply(lambda d: np.average(d.n, weights=d.m2)),
            "hmin": g.h.min(), "hmax": g.h.max(), "nmin": g.n.min(), "nmax": g.n.max(),
            "cnt": g.size(),
        })
        return out

    munis = munis.merge(summarize("uid"), left_on="uid", right_index=True, how="left")
    counties = counties.merge(summarize("ccode"), left_on="ccode", right_index=True, how="left")
    munis = munis.reset_index(drop=True)
    munis["id"] = np.arange(1, len(munis) + 1)
    counties["id"] = counties["ccode"].astype(int)
    munis["km2"] = munis.area / 1e6

    # Write layers.
    cp = ["id", "cname", "h", "n", "hmin", "hmax", "nmin", "nmax", "cnt"]
    mp = ["id", "uname", "utype", "cname", "h", "n", "hmin", "hmax", "nmin", "nmax", "cnt"]
    ap = ["id", "uname", "cname", "sdname", "vname", "h", "n", "star", "vrate", "alt"]
    write_seq(counties, OUT / "counties.geojsonl", "counties", 4, 14, cp)
    write_seq(munis, OUT / "munis.geojsonl", "munis", 6, 14, mp)
    write_seq(areas, OUT / "areas.geojsonl", "areas", 9, 14, ap)
    write_seq(vil.assign(id=np.arange(1, len(vil) + 1)), OUT / "villages.geojsonl", "villages", 9, 14, ["id", "vname"])
    write_seq(label_points(counties), OUT / "county_labels.geojsonl", "county_labels", 4, 10, ["cname"])
    ml = label_points(munis)
    ml["r"] = ml["km2"].rank(ascending=False).astype(int)
    write_seq(ml, OUT / "muni_labels.geojsonl", "muni_labels", 7, 12, ["uname", "utype", "r"])
    sl = label_points(sd)
    write_seq(sl, OUT / "school_labels.geojsonl", "school_labels", 11, 14, ["sdname"])
    al = label_points(areas[areas.h.notna() & (areas.km2 > 0.3)])
    al["r"] = al["km2"].rank(ascending=False).astype(int)
    write_seq(al, OUT / "area_labels.geojsonl", "area_labels", 10, 14, ["h", "n", "r"])

    # Color scale domain and search index.
    def q(s):
        return [round(float(x), 2) for x in np.percentile(s.dropna(), [2, 50, 98])]

    meta = {
        "year": CFG["year"],
        "domain": {"h": q(areas.h), "n": q(areas.n)},
        "counts": {"areas": int(len(areas)), "munis": int(len(munis)), "counties": int(len(counties)),
                   "rated_share": round(float(rated_share), 4)},
        "default_value": CFG.get("default_value", 350000),
    }
    (SITE_DATA / "meta.json").write_text(json.dumps(meta))

    def bbox(g):
        b = g.to_crs(4326).geometry.bounds
        return [[round(x, 4) for x in row] for row in b[["minx", "miny", "maxx", "maxy"]].values]

    search = []
    for (name, kind, county), b in zip(zip(counties.cname + " County", ["county"] * len(counties), [""] * len(counties)), bbox(counties)):
        search.append({"n": name, "k": kind, "c": county, "b": b})
    for (name, ut, county), b in zip(zip(munis.uname, munis.utype, munis.cname), bbox(munis)):
        search.append({"n": name, "k": "city" if ut == "C" else "township", "c": f"{county} County", "b": b})
    vil_c = gpd.sjoin(label_points(vil), counties[["cname", "geometry"]], how="left", predicate="within")
    vil_c = vil_c[~vil_c.index.duplicated()].reindex(vil.index)
    for name, county, b in zip(vil.vname, vil_c.cname.fillna(""), bbox(vil)):
        search.append({"n": f"Village of {name}", "k": "village", "c": f"{county} County" if county else "", "b": b})
    for name, b in zip(sd.sdname, bbox(sd)):
        search.append({"n": name, "k": "school", "c": "", "b": b})
    (SITE_DATA / "search.json").write_text(json.dumps(search, separators=(",", ":")))

    report = LOAD_NOTES + report
    (QA / "summary.md").write_text("## Data match report\n\n" + "\n".join(f"- {l}" for l in report) + "\n")
    print("\n".join(report))
    if rated_share < MIN_RATED_SHARE:
        sys.exit(f"Only {rated_share:.0%} of the state's area got a rate; stopping so a broken map is not published.")


if __name__ == "__main__":
    main()
