/* Michigan property tax map: controls, selection, search and shareable links. */
(async function () {
  const $ = (id) => document.getElementById(id);
  const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  const mills = (m) => (m == null ? "—" : `${Number(m).toFixed(2)} mills`);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const BASE = new URL(".", location.href).href;
  const darkQ = matchMedia("(prefers-color-scheme: dark)");
  const coarse = matchMedia("(pointer: coarse)").matches;

  // ------------------------------------------------------------------ state
  const meta = await fetch("data/meta.json").then((r) => r.json());
  const H = new URLSearchParams(location.hash.slice(1));
  const S = {
    value: clampValue(Number(H.get("v")) || meta.default_value || 350000),
    type: H.get("t") === "n" ? "n" : "h",
    pinned: null, // {layer, id, p}
    shown: null,
  };
  const startView = (H.get("m") || "").split(",").map(Number);
  const startSel = (H.get("s") || "").split(":");

  function clampValue(v) { return Math.max(0, Math.min(100000000, Math.round(v))); }
  const sev = () => S.value / 2;
  const tax = (m) => (m == null ? null : (sev() * m) / 1000);

  $("yr").textContent = $("yr2").textContent = meta.year;

  // ------------------------------------------------------------------ map
  const protocol = new pmtiles.Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);

  const theme = () => (darkQ.matches ? "dark" : "light");
  const styleOpts = () => ({ theme: theme(), type: S.type, value: S.value, meta, base: BASE, hl: S.shown && { layer: S.shown.layer, id: S.shown.id } });

  const narrow = innerWidth < 700;
  const map = new maplibregl.Map({
    container: "map",
    style: buildStyle(styleOpts()),
    center: startView.length === 3 && startView.every(isFinite) ? [startView[0], startView[1]] : [-85.4, 44.75],
    zoom: startView.length === 3 && startView.every(isFinite) ? startView[2] : narrow ? 5 : 5.9,
    minZoom: 4.5,
    maxZoom: 17,
    maxBounds: [[-97, 38.5], [-76, 51]],
    dragRotate: false,
    pitchWithRotate: false,
    touchPitch: false,
    attributionControl: { compact: true },
  });
  map.touchZoomRotate.disableRotation();
  map.keyboard.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.GeolocateControl({ fitBoundsOptions: { maxZoom: 13 } }), "top-right");

  // Route shields are drawn here rather than loaded from a sprite file.
  map.on("styleimagemissing", (e) => {
    if (/^tag-/.test(e.id) && !map.hasImage(e.id)) {
      // Rounded tag behind the tax amounts, so they read on any fill color.
      const dark = e.id === "tag-dark", w = 40, h = 32, c = document.createElement("canvas");
      c.width = w; c.height = h;
      const g = c.getContext("2d");
      g.fillStyle = dark ? "rgba(27,35,38,0.92)" : "rgba(255,255,255,0.94)";
      g.strokeStyle = dark ? "rgba(230,238,238,0.35)" : "rgba(28,43,46,0.35)";
      g.lineWidth = 2;
      g.beginPath(); if (g.roundRect) g.roundRect(2, 2, w - 4, h - 4, 9); else g.rect(2, 2, w - 4, h - 4); g.fill(); g.stroke();
      map.addImage(e.id, g.getImageData(0, 0, w, h), { pixelRatio: 2, stretchX: [[12, 28]], stretchY: [[11, 21]], content: [6, 5, 34, 27] });
      return;
    }
    if (!/^sh-/.test(e.id) || map.hasImage(e.id)) return;
    const r = 2, w = 48, h = 40, c = document.createElement("canvas");
    c.width = w; c.height = h;
    const g = c.getContext("2d");
    const style = { "sh-i": ["#1d4f91", "#ffffff", 10], "sh-us": ["#ffffff", "#1c2b2e", 10], "sh-m": ["#ffffff", "#1c2b2e", 3] }[e.id] || ["#ffffff", "#1c2b2e", 6];
    g.fillStyle = style[0]; g.strokeStyle = style[1]; g.lineWidth = 3;
    g.beginPath(); if (g.roundRect) g.roundRect(3, 3, w - 6, h - 6, style[2]); else g.rect(3, 3, w - 6, h - 6); g.fill(); g.stroke();
    map.addImage(e.id, g.getImageData(0, 0, w, h), { pixelRatio: r, stretchX: [[14, 34]], stretchY: [[12, 28]], content: [8, 6, 40, 34] });
  });

  const TIERS = [
    { layer: "counties", max: 8.3, label: "Showing counties (area-weighted average). Zoom in for cities and townships." },
    { layer: "munis", max: 10.3, label: "Showing cities and townships (area-weighted average). Zoom in for each school district and village." },
    { layer: "areas", max: 99, label: "Showing each tax area: city or township × school district × village." },
  ];
  const tier = () => TIERS.find((t) => map.getZoom() < t.max);

  function pick(point) {
    const t = tier();
    const pad = coarse ? 6 : 0;
    const box = [[point.x - pad, point.y - pad], [point.x + pad, point.y + pad]];
    const f = map.queryRenderedFeatures(box, { layers: [`fill-${t.layer}`] })[0];
    return f ? { layer: t.layer, id: f.properties.id, p: f.properties } : null;
  }

  function setHighlight() {
    for (const l of ["counties", "munis", "areas"]) {
      if (map.getLayer(`hl-${l}`)) map.setFilter(`hl-${l}`, STYLE_HELPERS.hlFilter(S.shown, l));
    }
  }

  function show(sel) {
    S.shown = sel;
    setHighlight();
    renderDetail();
    renderSummary();
  }

  map.on("mousemove", (e) => {
    const f = pick(e.point);
    map.getCanvas().style.cursor = f ? "pointer" : "";
    if (!S.pinned && !coarse) {
      if (!f && !S.shown) return;
      if (f && S.shown && f.layer === S.shown.layer && f.id === S.shown.id) return;
      show(f);
    }
  });
  map.getCanvas().addEventListener("mouseleave", () => { if (!S.pinned) show(null); });
  map.on("click", (e) => {
    const f = pick(e.point);
    const same = f && S.pinned && f.layer === S.pinned.layer && f.id === S.pinned.id;
    S.pinned = same ? null : f;
    show(S.pinned || (coarse ? null : f));
    saveHash();
  });
  map.on("zoom", () => { $("tier").textContent = tier().label; });

  // ------------------------------------------------------------------ panel
  function renderDetail() {
    const d = $("detail");
    const s = S.shown;
    if (!s) {
      d.innerHTML = `<span class="mut">${coarse ? "Tap" : "Hover over or tap"} an area to see its breakdown.</span>`;
      return;
    }
    const p = s.p, t = S.type, o = t === "h" ? "n" : "h";
    const label = { h: "Homestead", n: "Non-homestead" };
    if (s.layer === "areas") {
      const sub = [p.sdname, p.vname ? `Village of ${p.vname}` : null].filter(Boolean).map(esc).join(" · ");
      d.innerHTML = `
        <h2>${esc(p.uname)}${p.star ? " *" : ""}${p.est ? " (estimate)" : ""}</h2>
        <div class="dsub">${sub}<br>${esc(p.cname)} County</div>
        ${p[t] == null ? `<div class="tax">No rate found</div><div class="per">The state's rate file has no row for this area.</div>` : `
        <div class="tax">${usd.format(tax(p[t]))}</div>
        <div class="per">per year, ${label[t].toLowerCase()} · ${usd.format(tax(p[t]) / 12)} a month</div>`}
        <div class="row"><span>${label[t]} rate</span><b>${mills(p[t])}</b></div>
        <div class="row"><span>${label[o]} rate</span><span>${mills(p[o])}</span></div>
        <div class="row"><span>${label[o]} tax</span><span>${p[o] == null ? "—" : usd.format(tax(p[o]))}</span></div>
        ${altRows(p, t)}
        ${p.est ? `<p class="hint">Estimate: the state's school district map and Treasury's rate list don't line up here (the district was likely merged or renamed), so this uses the rate of the neighboring area.</p>` : ""}
        ${p.vname && !p.vrate ? `<p class="hint">No village rate was found for this school district, so the township rate is shown.</p>` : ""}
        ${p.star ? `<p class="hint">* The state lists a second rate for this district here; the first is shown.</p>` : ""}`;
      return;
    }
    const title = s.layer === "counties" ? `${p.cname} County` : p.uname;
    const sub = s.layer === "counties" ? "County average" : `${esc(p.cname)} County`;
    const lo = p[`${t}min`], hi = p[`${t}max`];
    d.innerHTML = `
      <h2>${esc(title)}</h2>
      <div class="dsub">${sub}</div>
      ${p[t] == null ? `<div class="tax">No rate found</div><div class="per">&nbsp;</div>` : `
      <div class="tax">${usd.format(tax(p[t]))}</div>
      <div class="per">typical per year, ${label[t].toLowerCase()} (area-weighted average)</div>`}
      <div class="row"><span>Range inside</span><b>${lo == null ? "—" : `${usd.format(tax(lo))} – ${usd.format(tax(hi))}`}</b></div>
      <div class="row"><span>Average ${label[t].toLowerCase()} rate</span><span>${mills(p[t])}</span></div>
      <div class="row"><span>Tax areas</span><span>${p.cnt ?? "—"}</span></div>
      <p class="hint">Rates vary by school district and village. Zoom in to see each area.</p>`;
  }

  // Parts of a district with their own debt or college millage ("alt" = "LABEL|pre|nh;...").
  function altRows(p, t) {
    if (!p.alt) return "";
    const rows = String(p.alt).split(";").map((x) => x.split("|")).filter((x) => x.length === 3);
    if (!rows.length) return "";
    return `<p class="hint">Part of this area pays a different rate:</p>` + rows.map(([lbl, h, n]) => {
      const m = Number(t === "h" ? h : n);
      return `<div class="row"><span>${esc(lbl)}</span><span>${usd.format(tax(m))} · ${mills(m)}</span></div>`;
    }).join("");
  }

  function renderSummary() {
    const s = S.shown, t = S.type;
    let txt = `${usd.format(S.value)} · ${t === "h" ? "Homestead" : "Non-homestead"} — tap for controls`;
    if (s && s.p[t] != null) {
      const name = s.layer === "counties" ? `${s.p.cname} County` : s.p.uname;
      txt = `${name}: ${usd.format(tax(s.p[t]))}/yr${s.layer === "areas" ? "" : " typical"}`;
    }
    $("shSum").textContent = txt;
  }

  function renderValue() {
    $("val").textContent = usd.format(S.value);
    $("sev").textContent = usd.format(sev());
    if (document.activeElement !== $("num")) $("num").value = S.value;
    $("slider").value = Math.min(1500000, Math.max(50000, S.value));
    const d = meta.domain[S.type];
    $("lo").textContent = usd.format(tax(d[0]));
    $("mid").textContent = usd.format(tax(d[1]));
    $("hi").textContent = usd.format(tax(d[2]));
    const fields = STYLE_HELPERS.labelFields(S.type, S.value, STYLE_HELPERS.PALETTES[theme()]);
    for (const [id, f] of Object.entries(fields)) if (map.getLayer(id)) map.setLayoutProperty(id, "text-field", f);
    renderDetail();
    renderSummary();
  }

  function setType(t) {
    S.type = t;
    $("bH").classList.toggle("on", t === "h"); $("bH").setAttribute("aria-pressed", t === "h");
    $("bN").classList.toggle("on", t === "n"); $("bN").setAttribute("aria-pressed", t === "n");
    const P = STYLE_HELPERS.PALETTES[theme()];
    for (const l of ["fill-counties", "fill-munis", "fill-areas"]) {
      if (map.getLayer(l)) map.setPaintProperty(l, "fill-color", STYLE_HELPERS.fillColor(meta, t, P));
    }
    renderValue();
    saveHash();
  }

  $("slider").addEventListener("input", (e) => { S.value = clampValue(+e.target.value); renderValue(); saveHashSoon(); });
  $("num").addEventListener("input", (e) => { if (e.target.value !== "") { S.value = clampValue(+e.target.value); renderValue(); saveHashSoon(); } });
  $("num").addEventListener("blur", () => { $("num").value = S.value; });
  $("bH").addEventListener("click", () => setType("h"));
  $("bN").addEventListener("click", () => setType("n"));

  // Mobile bottom sheet.
  const aside = $("aside");
  $("sheetH").addEventListener("click", () => {
    const open = aside.classList.toggle("collapsed") === false;
    $("sheetH").setAttribute("aria-expanded", open);
    if (!open) aside.scrollTop = 0;
  });

  darkQ.addEventListener("change", () => map.setStyle(buildStyle(styleOpts())));

  // ------------------------------------------------------------------ search
  let index = null;
  const KIND = { county: "County", city: "City", township: "Township", village: "Village", school: "School district" };
  const ORDER = { county: 0, city: 1, township: 2, village: 3, school: 4 };
  const q = $("q"), res = $("res");
  let hits = [], cur = -1;

  async function loadIndex() {
    if (!index) index = await fetch("data/search.json").then((r) => r.json());
    return index;
  }
  q.addEventListener("focus", loadIndex);
  q.addEventListener("input", async () => {
    const terms = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return closeList();
    const idx = await loadIndex();
    hits = idx
      .filter((e) => { const s = `${e.n} ${e.c}`.toLowerCase(); return terms.every((t) => s.includes(t)); })
      .sort((a, b) => {
        const ws = (e) => (e.n.toLowerCase().split(/[^a-z0-9]+/).some((w) => w.startsWith(terms[0])) ? 0 : 1);
        const as = ws(a), bs = ws(b);
        return as - bs || ORDER[a.k] - ORDER[b.k] || a.n.localeCompare(b.n);
      })
      .slice(0, 8);
    cur = hits.length ? 0 : -1;
    renderList();
  });
  q.addEventListener("keydown", (e) => {
    if (res.hidden) return;
    if (e.key === "ArrowDown") { cur = Math.min(hits.length - 1, cur + 1); renderList(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { cur = Math.max(0, cur - 1); renderList(); e.preventDefault(); }
    else if (e.key === "Enter" && cur >= 0) { go(hits[cur]); e.preventDefault(); }
    else if (e.key === "Escape") closeList();
  });
  q.addEventListener("blur", () => setTimeout(closeList, 150));
  function renderList() {
    res.innerHTML = hits.length
      ? hits.map((h, i) => `<li role="option" id="r${i}" aria-selected="${i === cur}" data-i="${i}"><span>${esc(h.n)}</span><span class="k">${esc([KIND[h.k], h.c].filter(Boolean).join(" · "))}</span></li>`).join("")
      : `<li class="mut" aria-disabled="true">No matches</li>`;
    res.hidden = false;
    q.setAttribute("aria-expanded", "true");
    if (cur >= 0) q.setAttribute("aria-activedescendant", `r${cur}`);
  }
  function closeList() { res.hidden = true; q.setAttribute("aria-expanded", "false"); q.removeAttribute("aria-activedescendant"); }
  res.addEventListener("mousedown", (e) => { const li = e.target.closest("li[data-i]"); if (li) { e.preventDefault(); go(hits[+li.dataset.i]); } });
  function go(h) {
    closeList();
    q.value = h.n;
    q.blur();
    const maxZoom = { county: 8.2, city: 12.5, township: 11.5, village: 13, school: 10.8 }[h.k];
    map.fitBounds([[h.b[0], h.b[1]], [h.b[2], h.b[3]]], { padding: narrow ? 30 : 60, maxZoom, duration: 900 });
    if (innerWidth <= 900) { aside.classList.add("collapsed"); $("sheetH").setAttribute("aria-expanded", "false"); }
  }

  // ------------------------------------------------------------------ shareable link
  let hashTimer = 0;
  function saveHash() {
    const c = map.getCenter();
    const p = new URLSearchParams();
    p.set("v", S.value);
    if (S.type === "n") p.set("t", "n");
    p.set("m", `${c.lng.toFixed(4)},${c.lat.toFixed(4)},${map.getZoom().toFixed(2)}`);
    if (S.pinned) p.set("s", `${S.pinned.layer}:${S.pinned.id}`);
    history.replaceState(null, "", `#${p}`);
  }
  function saveHashSoon() { clearTimeout(hashTimer); hashTimer = setTimeout(saveHash, 300); }
  map.on("moveend", saveHashSoon);

  // Restore a selection from a shared link once its tiles have loaded.
  if (["counties", "munis", "areas"].includes(startSel[0]) && startSel[1]) {
    const layer = startSel[0], id = Number(startSel[1]);
    map.once("idle", () => {
      const f = map.querySourceFeatures("tax", { sourceLayer: layer, filter: ["==", ["get", "id"], id] })[0];
      if (f) { S.pinned = { layer, id, p: f.properties }; show(S.pinned); }
    });
  }

  $("tier").textContent = tier().label;
  renderValue();
  setType(S.type);
})();
