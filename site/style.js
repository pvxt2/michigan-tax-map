/* Map style: Protomaps basemap (OpenStreetMap) + Michigan tax layers.
 *
 * Draw order, bottom to top:
 *   water background > land > tax colors > water > boundary lines > roads > highlight > labels
 *
 * Tax colors by zoom (crossfaded):
 *   counties  z4–8.6 | cities & townships z8–10.6 | tax areas (city/township × school district × village) z10+
 *
 * Roads: one layer pair (casing + line) per class. Each class appears at its own zoom,
 * fades in over ~0.8 zoom, and widens exponentially as you zoom in.
 */
(function () {
  const PALETTES = {
    light: {
      water: "#c6dbe4", land: "#eef0ec", lo: "#e3f1ec", mid: "#efc65f", hi: "#9e3340", nodata: "#cfd3d1",
      ink: "#1c2b2e", mut: "#5b6c6f", halo: "rgba(255,255,255,0.92)", edge: "#ffffff",
      road: { highway: "#555d62", major: "#6c7479", minor: "#8c9397", rail: "#8c9397" }, casing: "#ffffff",
      river: "#a9c8d6", fillOpacity: 0.8,
    },
    dark: {
      water: "#0f2430", land: "#1b2326", lo: "#1f3d3b", mid: "#b8913a", hi: "#c4525f", nodata: "#2c3538",
      ink: "#e6eeee", mut: "#9aabae", halo: "rgba(18,23,25,0.9)", edge: "#121719",
      road: { highway: "#c3ccd0", major: "#a7b2b6", minor: "#86939a", rail: "#6f7d83" }, casing: "#121719",
      river: "#1d3e4f", fillOpacity: 0.78,
    },
  };

  const exp = (stops) => ["interpolate", ["exponential", 1.6], ["zoom"], ...stops.flat()];
  const fade = (z, full) => ["interpolate", ["linear"], ["zoom"], z, 0, z + 0.8, full];
  const notLink = ["!=", ["get", "is_link"], true];
  const kd = (...v) => ["in", ["get", "kind_detail"], ["literal", v]];

  // Road hierarchy. z = zoom the class appears at; w = [zoom, px] width stops; cz = casing from.
  const ROADS = [
    { id: "service", f: ["all", ["==", ["get", "kind"], "minor_road"], kd("service", "alley")], z: 14.5, tone: "minor", op: 0.7,
      w: [[14.5, 0.4], [16, 1.6], [18, 4]] },
    { id: "minor", f: ["all", ["==", ["get", "kind"], "minor_road"], ["!", kd("service", "alley", "driveway", "parking_aisle")]], z: 12, tone: "minor", op: 0.85,
      w: [[12, 0.4], [14, 1.4], [16, 4], [18, 10]] },
    { id: "link", f: ["all", ["==", ["get", "is_link"], true], ["in", ["get", "kind"], ["literal", ["highway", "major_road"]]]], z: 11, tone: "major", op: 0.9,
      w: [[11, 0.5], [14, 1.8], [16, 4], [18, 9]] },
    { id: "tertiary", f: ["all", kd("tertiary"), notLink], z: 10, tone: "minor", op: 0.9,
      w: [[10, 0.5], [12, 1.1], [14, 2.6], [16, 6], [18, 14]], cz: 13 },
    { id: "secondary", f: ["all", kd("secondary"), notLink], z: 9, tone: "major", op: 0.9,
      w: [[9, 0.6], [12, 1.5], [14, 3.4], [16, 8], [18, 18]], cz: 12 },
    { id: "primary", f: ["all", kd("primary"), notLink], z: 8, tone: "major", op: 0.95,
      w: [[8, 0.7], [10, 1.2], [12, 2.2], [14, 4.4], [16, 10], [18, 22]], cz: 11 },
    { id: "trunk", f: ["all", kd("trunk"), notLink], z: 6.5, tone: "highway", op: 0.95,
      w: [[6.5, 0.8], [8, 1.2], [10, 2], [12, 3.2], [14, 5.6], [16, 12], [18, 26]], cz: 10 },
    { id: "motorway", f: ["all", kd("motorway"), notLink], z: 5, tone: "highway", op: 1,
      w: [[5, 0.8], [7, 1.3], [10, 2.4], [12, 3.8], [14, 6.6], [16, 14], [18, 30]], cz: 10 },
  ];

  function fillColor(meta, type, P) {
    const r = meta.domain[type];
    const d = [r[0], Math.max(r[1], r[0] + 0.01), Math.max(r[2], r[1] + 0.02)];
    return ["case", ["has", type],
      ["interpolate", ["linear"], ["get", type], d[0], P.lo, d[1], P.mid, d[2], P.hi],
      P.nodata];
  }

  function taxLabel(type, value) {
    const sevPerMill = value / 2 / 1000;
    // Rounded to the dollar before formatting, so no cents appear on any browser.
    return ["concat", "$", ["number-format", ["round", ["*", ["get", type], sevPerMill]], { "max-fraction-digits": 0 }]];
  }

  // Name with the typical tax underneath (counties, cities, townships), and the tax-area amounts.
  function nameWithTax(name, type, value, P) {
    return ["case", ["has", type],
      ["format", name, { "text-color": P.mut }, "\n", {}, taxLabel(type, value), { "font-scale": 1.12, "text-color": P.ink }],
      ["format", name, {}]];
  }

  function labelFields(type, value, P) {
    return {
      "label-counties": nameWithTax(["upcase", ["get", "cname"]], type, value, P),
      "label-munis": ["get", "uname"],
      "label-areas": taxLabel(type, value),
    };
  }

  function hlFilter(hl, layer) {
    return ["==", ["get", "id"], hl && hl.layer === layer ? hl.id : -1];
  }

  window.buildStyle = function (o) {
    const P = PALETTES[o.theme] || PALETTES.light;
    const base = o.base;
    const layers = [];
    const add = (l) => layers.push(l);

    add({ id: "background", type: "background", paint: { "background-color": P.water } });
    // Two basemap files: "overview" (z0-9, Michigan and neighbours) and "basemap" (z10+, a band
    // around Michigan). Beyond the detailed band, the overview is shown overzoomed.
    const POLY = ["in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]]];
    add({ id: "earth-overview", type: "fill", source: "overview", "source-layer": "earth", paint: { "fill-color": P.land } });
    add({ id: "water-overview-under", type: "fill", source: "overview", "source-layer": "water", minzoom: 10, filter: POLY, paint: { "fill-color": P.water } });
    add({ id: "earth", type: "fill", source: "basemap", "source-layer": "earth", minzoom: 10, paint: { "fill-color": P.land } });

    // Tax colors, crossfaded by zoom tier.
    const fo = P.fillOpacity;
    add({ id: "fill-counties", type: "fill", source: "tax", "source-layer": "counties", maxzoom: 8.6,
      paint: { "fill-color": fillColor(o.meta, o.type, P), "fill-opacity": ["interpolate", ["linear"], ["zoom"], 8, fo, 8.6, 0] } });
    add({ id: "fill-munis", type: "fill", source: "tax", "source-layer": "munis", minzoom: 8, maxzoom: 10.6,
      paint: { "fill-color": fillColor(o.meta, o.type, P), "fill-opacity": ["interpolate", ["linear"], ["zoom"], 8, 0, 8.6, fo, 10, fo, 10.6, 0] } });
    add({ id: "fill-areas", type: "fill", source: "tax", "source-layer": "areas", minzoom: 10,
      paint: { "fill-color": fillColor(o.meta, o.type, P), "fill-opacity": ["interpolate", ["linear"], ["zoom"], 10, 0, 10.6, fo] } });

    // Water above the tax colors, so Great Lakes and inland lakes read clearly.
    add({ id: "water-overview", type: "fill", source: "overview", "source-layer": "water", maxzoom: 10, filter: POLY, paint: { "fill-color": P.water } });
    add({ id: "water", type: "fill", source: "basemap", "source-layer": "water", minzoom: 10, filter: POLY, paint: { "fill-color": P.water } });
    add({ id: "rivers", type: "line", source: "basemap", "source-layer": "water", minzoom: 10,
      filter: ["all", ["in", ["geometry-type"], ["literal", ["LineString", "MultiLineString"]]], ["in", ["get", "kind_detail"], ["literal", ["river", "canal"]]]],
      paint: { "line-color": P.river, "line-width": exp([[10, 0.6], [14, 2], [16, 4]]) } });

    // Boundaries.
    add({ id: "edge-areas", type: "line", source: "tax", "source-layer": "areas", minzoom: 10,
      paint: { "line-color": P.edge, "line-width": exp([[10, 0.4], [14, 1.2]]), "line-opacity": fade(10, 0.9) } });
    add({ id: "edge-villages", type: "line", source: "tax", "source-layer": "villages", minzoom: 10,
      paint: { "line-color": P.ink, "line-width": exp([[10, 0.8], [14, 1.6]]), "line-dasharray": [3, 2], "line-opacity": fade(10, 0.75) } });
    add({ id: "edge-munis", type: "line", source: "tax", "source-layer": "munis", minzoom: 7,
      paint: { "line-color": P.ink, "line-width": exp([[7, 0.3], [9, 0.7], [11, 1.3], [14, 2]]), "line-opacity": fade(7, 0.6) } });
    add({ id: "edge-counties", type: "line", source: "tax", "source-layer": "counties",
      paint: { "line-color": P.ink, "line-width": exp([[4, 0.5], [7, 1], [10, 1.8], [14, 3]]), "line-opacity": 0.75 } });

    // Rail, faint.
    add({ id: "rail", type: "line", source: "basemap", "source-layer": "roads", minzoom: 11,
      filter: ["all", ["==", ["get", "kind"], "rail"], ["!", kd("subway", "tram", "light_rail")]],
      paint: { "line-color": P.road.rail, "line-width": exp([[11, 0.5], [16, 1.5]]), "line-dasharray": [3, 3], "line-opacity": fade(11, 0.6) } });

    // Roads: casings for all classes first, then lines, lowest class first.
    for (const r of ROADS) {
      if (!r.cz) continue;
      add({ id: `road-${r.id}-casing`, type: "line", source: "basemap", "source-layer": "roads", minzoom: r.cz,
        filter: r.f, layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": P.casing, "line-width": exp(r.w.map(([z, w]) => [z, w + Math.min(2.5, 1 + w * 0.25)])), "line-opacity": fade(r.cz, 0.9) } });
    }
    for (const r of ROADS) {
      const line = { type: "line", "source-layer": "roads", filter: r.f, layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": P.road[r.tone], "line-width": exp(r.w), "line-opacity": fade(r.z, r.op) } };
      if (r.z < 10) add(Object.assign({ id: `road-${r.id}-overview`, source: "overview", minzoom: r.z, maxzoom: 10 }, line));
      add(Object.assign({ id: `road-${r.id}`, source: "basemap", minzoom: Math.max(r.z, 10) }, line));
    }

    // Selection highlight.
    for (const [layer, w] of [["counties", 3], ["munis", 2.6], ["areas", 2.6]]) {
      add({ id: `hl-${layer}`, type: "line", source: "tax", "source-layer": layer, filter: hlFilter(o.hl, layer),
        paint: { "line-color": P.ink, "line-width": w } });
    }

    // Labels.
    const font = (w) => [w === "m" ? "Noto Sans Medium" : w === "i" ? "Noto Sans Italic" : "Noto Sans Regular"];
    const text = (extra) => Object.assign({ "text-color": P.ink, "text-halo-color": P.halo, "text-halo-width": 1.4 }, extra || {});

    add({ id: "label-roads-minor", type: "symbol", source: "basemap", "source-layer": "roads", minzoom: 14,
      filter: ["all", ["==", ["get", "kind"], "minor_road"], ["has", "name"]],
      layout: { "symbol-placement": "line", "text-field": ["get", "name"], "text-font": font(), "text-size": 10.5, "symbol-sort-key": 30 },
      paint: text({ "text-color": P.mut }) });
    add({ id: "label-roads-tertiary", type: "symbol", source: "basemap", "source-layer": "roads", minzoom: 13,
      filter: ["all", kd("tertiary"), notLink, ["has", "name"]],
      layout: { "symbol-placement": "line", "text-field": ["get", "name"], "text-font": font(), "text-size": 11, "symbol-sort-key": 20 },
      paint: text() });
    add({ id: "label-roads-major", type: "symbol", source: "basemap", "source-layer": "roads", minzoom: 12,
      filter: ["all", kd("trunk", "primary", "secondary"), notLink, ["has", "name"]],
      layout: { "symbol-placement": "line", "text-field": ["get", "name"], "text-font": font("m"), "text-size": 11.5, "symbol-sort-key": 10 },
      paint: text() });

    for (const [cls, z, src, maxz] of [["motorway", 7, "overview", 10], ["trunk", 8, "overview", 10], ["primary", 9, "overview", 10],
                                        ["motorway", 10, "basemap", 24], ["trunk", 10, "basemap", 24], ["primary", 10, "basemap", 24]]) {
      add({ id: `shield-${cls}-${src}`, type: "symbol", source: src, "source-layer": "roads", minzoom: z, maxzoom: maxz,
        filter: ["all", kd(cls), notLink, ["has", "shield_text"]],
        layout: {
          "symbol-placement": "line", "symbol-spacing": cls === "motorway" ? 380 : 460,
          "text-field": ["get", "shield_text"], "text-font": font("m"), "text-size": 10,
          "text-rotation-alignment": "viewport", "icon-rotation-alignment": "viewport",
          "icon-image": ["match", ["get", "network"], "US:I", "sh-i", "US:US", "sh-us", "sh-m"],
          "icon-text-fit": "both", "icon-text-fit-padding": [2, 4, 2, 4],
          "symbol-sort-key": cls === "motorway" ? 1 : cls === "trunk" ? 2 : 3,
        },
        paint: { "text-color": ["match", ["get", "network"], "US:I", "#ffffff", "#1c2b2e"] } });
    }

    // Labels are placed top-down: later layers win when labels collide, so the tax amounts come last.
    const lf = labelFields(o.type, o.value, P);
    add({ id: "label-schools", type: "symbol", source: "tax", "source-layer": "school_labels", minzoom: 12,
      layout: { "text-field": ["get", "sdname"], "text-font": font("i"), "text-size": 11, "text-max-width": 8, "text-padding": 10 },
      paint: text({ "text-color": P.mut }) });
    add({ id: "label-places-low", type: "symbol", source: "overview", "source-layer": "places", minzoom: 5.5, maxzoom: 8.6,
      filter: ["==", ["get", "kind"], "locality"],
      layout: { "text-field": ["get", "name"], "text-font": font(), "text-size": ["interpolate", ["linear"], ["zoom"], 5.5, 10, 8.6, 12],
        "symbol-sort-key": ["-", 0, ["coalesce", ["get", "population"], 0]], "text-padding": 4 },
      paint: text() });
    add({ id: "label-places-high", type: "symbol", source: "basemap", "source-layer": "places", minzoom: 11,
      filter: ["==", ["get", "kind"], "locality"],
      layout: { "text-field": ["get", "name"], "text-font": font("m"), "text-size": 13, "symbol-sort-key": ["-", 0, ["coalesce", ["get", "population"], 0]] },
      paint: text() });
    add({ id: "label-counties", type: "symbol", source: "tax", "source-layer": "county_labels", minzoom: 4.5, maxzoom: 9,
      layout: { "text-field": lf["label-counties"], "text-font": font("m"), "text-size": ["interpolate", ["linear"], ["zoom"], 5, 9.5, 8.5, 13.5],
        "text-letter-spacing": 0.04, "text-padding": 2, "symbol-sort-key": 0 },
      paint: text({ "text-halo-width": 1.8, "text-opacity": ["interpolate", ["linear"], ["zoom"], 8.2, 1, 9, 0] }) });
    add({ id: "label-munis", type: "symbol", source: "tax", "source-layer": "muni_labels", minzoom: 8.6, maxzoom: 11,
      layout: { "text-field": lf["label-munis"], "text-font": font("m"), "text-size": ["interpolate", ["linear"], ["zoom"], 8.6, 11, 11, 14],
        "text-max-width": 8, "symbol-sort-key": ["get", "r"], "text-padding": 3 },
      paint: text({ "text-halo-width": 1.8 }) });
    add({ id: "label-areas", type: "symbol", source: "tax", "source-layer": "area_labels", minzoom: 10.6,
      layout: { "text-field": lf["label-areas"], "text-font": font("m"), "text-size": ["interpolate", ["linear"], ["zoom"], 10.6, 12.5, 15, 15.5],
        "icon-image": `tag-${o.theme === "dark" ? "dark" : "light"}`, "icon-text-fit": "both", "icon-text-fit-padding": [2, 6, 2, 6],
        "symbol-sort-key": ["get", "r"], "text-padding": 4 },
      paint: { "text-color": P.ink, "text-opacity": fade(10.6, 1), "icon-opacity": fade(10.6, 1) } });

    return {
      version: 8,
      glyphs: base + "fonts/{fontstack}/{range}.pbf",
      sources: {
        overview: { type: "vector", url: "pmtiles://" + base + "data/basemap-overview.pmtiles", maxzoom: 9,
          attribution: '<a href="https://protomaps.com">Protomaps</a> © <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>' },
        basemap: { type: "vector", url: "pmtiles://" + base + "data/basemap.pmtiles", minzoom: 10,
          attribution: '<a href="https://protomaps.com">Protomaps</a> © <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>' },
        tax: { type: "vector", url: "pmtiles://" + base + "data/tax.pmtiles",
          attribution: "Michigan Dept. of Treasury; Michigan Geographic Framework" },
      },
      layers,
    };
  };

  window.STYLE_HELPERS = { fillColor, taxLabel, labelFields, hlFilter, PALETTES };
})();
