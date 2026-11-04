"use strict";

const $ = (id) => document.getElementById(id);
const UNKNOWN = "Onbekend";
const OTHER = "Overig";
const numberFormat = new Intl.NumberFormat("nl-NL");
const euro = (v) => (v == null ? "–" : `€ ${numberFormat.format(Math.round(v))}`);
const km = (v) => (v == null ? "–" : `${numberFormat.format(Math.round(v))} km`);
const SITE_NAMES = {
  marktplaats: "Marktplaats", viabovag: "viaBOVAG", autotrack: "AutoTrack",
  gaspedaal: "Gaspedaal", autoscout24: "AutoScout24",
};

/** Geschraapte tekst is onbetrouwbaar: alles gaat door esc(), links door safeUrl(). */
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}
function safeUrl(url) {
  try {
    const parsed = new URL(url);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "#";
  } catch {
    return "#";
  }
}

const field = (key) => (car) => car[key];
function band(key, step, format) {
  return { band: key, step, get: (c) => (c[key] == null ? null : Math.floor(c[key] / step) * step), format };
}
const DIMENSIONS = {
  generation: { label: "Generatie", get: field("generation"), facet: true, ordered: true },
  year: { label: "Bouwjaar", get: field("year"), ordered: true, rangeKey: "year" },
  priceBand: { label: "Prijsklasse", ordered: true, ...band("price_eur", 5000, (v) => `${euro(v)} – ${numberFormat.format(v + 4999)}`) },
  kmBand: { label: "Km-klasse", ordered: true, ...band("mileage_km", 25000, (v) => `${numberFormat.format(v)} – ${numberFormat.format(v + 24999)}`) },
  powerBand: { label: "Vermogen (pk)", ordered: true, ...band("power_hp", 25, (v) => `${v} – ${v + 24} pk`) },
  fuel: { label: "Brandstof", get: field("fuel"), facet: true },
  transmission: { label: "Transmissie", get: field("transmission"), facet: true },
  features: { label: "Opties", multi: true, facet: true, requireAll: true, get: (c) => c.features || [] },
  drivetrain: { label: "Aandrijving", get: field("drivetrain"), facet: true },
  variant: { label: "Motorvariant", get: field("variant"), facet: true },
  trim: { label: "Uitvoering", get: field("trim"), facet: true },
  color: { label: "Kleur", get: field("color"), facet: true },
  energy_label: { label: "Energielabel", get: field("energy_label"), facet: true, ordered: true },
  seller_type: { label: "Verkoper", get: field("seller_type"), facet: true },
  province: { label: "Provincie", get: field("province"), facet: true },
  site: { label: "Site", multi: true, get: (c) => c.sources.map((s) => s.site), format: (v) => SITE_NAMES[v] || v, facet: true },
};
const RANGES = [
  { key: "price_eur", label: "Prijs (€)", step: 500 },
  { key: "mileage_km", label: "Kilometerstand", step: 5000 },
  { key: "year", label: "Bouwjaar", step: 1 },
  { key: "power_hp", label: "Vermogen (pk)", step: 10 },
];
const median = (values) => {
  const sorted = values.filter((v) => v != null).sort((a, b) => a - b);
  if (!sorted.length) return null;
  const mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
};
const mean = (values) => {
  const known = values.filter((v) => v != null);
  return known.length ? known.reduce((a, b) => a + b, 0) / known.length : null;
};
const minimum = (values) => {
  const known = values.filter((v) => v != null);
  return known.length ? Math.min(...known) : null;
};
const METRICS = {
  count: { label: "Aantal auto's", calc: (cars) => cars.length, format: (v) => numberFormat.format(v) },
  medianPrice: { label: "Mediaan prijs", calc: (cars) => median(cars.map((c) => c.price_eur)), format: euro },
  meanPrice: { label: "Gemiddelde prijs", calc: (cars) => mean(cars.map((c) => c.price_eur)), format: euro },
  minPrice: { label: "Laagste prijs", calc: (cars) => minimum(cars.map((c) => c.price_eur)), format: euro },
  medianKm: { label: "Mediaan km-stand", calc: (cars) => median(cars.map((c) => c.mileage_km)), format: km },
  medianYear: { label: "Mediaan bouwjaar", calc: (cars) => median(cars.map((c) => c.year)), format: (v) => (v == null ? "–" : String(Math.round(v))) },
};
const SCATTER_X = {
  mileage_km: { label: "Kilometerstand", title: "kilometerstand", format: (v) => numberFormat.format(v) },
  year: { label: "Bouwjaar", title: "bouwjaar", format: (v) => String(v) },
  power_hp: { label: "Vermogen (pk)", title: "vermogen", format: (v) => `${v}` },
};
const SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
const TABLE_COLUMNS = [
  { key: null, label: "" },
  { key: "title", label: "Auto" },
  { key: "price_eur", label: "Prijs", num: true },
  { key: "mileage_km", label: "Km-stand", num: true },
  { key: "year", label: "Jaar", num: true },
  { key: "fuel", label: "Brandstof" },
  { key: "transmission", label: "Transmissie" },
  { key: "power_hp", label: "Pk", num: true },
  { key: "city", label: "Locatie" },
  { key: null, label: "Advertentie" },
];
const PAGE_SIZE = 50;

const state = {
  cars: [],
  q: "",
  ranges: {},
  facets: {},
  sort: { key: "price_eur", dir: 1 },
  page: 0,
  pivot: { row: "generation", col: "fuel", metric: "count" },
  scatter: { x: "mileage_km", color: "generation" },
  colorMap: new Map(),
};

function dimValues(car, dim) {
  const raw = dim.get(car);
  if (dim.multi) return raw.length ? raw : [UNKNOWN];
  return [raw == null || raw === "" ? UNKNOWN : raw];
}
function dimLabel(dim, value) {
  return value !== UNKNOWN && value !== OTHER && dim.format ? dim.format(value) : String(value);
}

function matchesText(car, query) {
  if (!query) return true;
  const haystack = [car.title, car.city, car.province, car.seller_name, car.license_plate, car.variant, car.trim,
    car.color, ...(car.options || []), ...(car.features || [])].join(" ").toLowerCase();
  return query.split(/\s+/).every((word) => haystack.includes(word));
}

/** skipFacet laat één filtergroep weg, zodat facet-tellingen tonen wat die keuze zou opleveren. */
function filtered(skipFacet = null) {
  const query = state.q.trim().toLowerCase();
  return state.cars.filter((car) => {
    if (!matchesText(car, query)) return false;
    for (const [key, range] of Object.entries(state.ranges)) {
      const value = car[key];
      if (range.min != null && (value == null || value < range.min)) return false;
      if (range.max != null && (value == null || value > range.max)) return false;
    }
    for (const [name, selected] of Object.entries(state.facets)) {
      if (name === skipFacet || !selected.size) continue;
      const dim = DIMENSIONS[name];
      const values = dimValues(car, dim).map(String);
      const hit = dim.requireAll ? [...selected].every((v) => values.includes(v)) : values.some((v) => selected.has(v));
      if (!hit) return false;
    }
    return true;
  });
}

/* ---------- filters ---------- */

function buildRangeFilters() {
  $("rangeFilters").innerHTML = RANGES.map((r) => `
    <div class="field">
      <span>${esc(r.label)}</span>
      <div class="range-row">
        <input type="number" inputmode="numeric" step="${r.step}" min="0" data-range="${r.key}" data-bound="min" aria-label="${esc(r.label)} vanaf" placeholder="van">
        –
        <input type="number" inputmode="numeric" step="${r.step}" min="0" data-range="${r.key}" data-bound="max" aria-label="${esc(r.label)} tot en met" placeholder="t/m">
      </div>
    </div>`).join("");
}

function setRange(key, bound, value) {
  const range = state.ranges[key] || (state.ranges[key] = { min: null, max: null });
  range[bound] = value;
  if (range.min == null && range.max == null) delete state.ranges[key];
}

function syncRangeInputs() {
  document.querySelectorAll("[data-range]").forEach((input) => {
    const value = state.ranges[input.dataset.range]?.[input.dataset.bound];
    const next = value == null ? "" : String(value);
    if (input.value !== next) input.value = next;
    const stats = rangeStats[input.dataset.range];
    if (stats) input.placeholder = String(input.dataset.bound === "min" ? stats.min : stats.max);
  });
}

let rangeStats = {};
function computeRangeStats() {
  rangeStats = {};
  for (const { key } of RANGES) {
    const values = state.cars.map((c) => c[key]).filter((v) => v != null);
    if (values.length) rangeStats[key] = { min: Math.min(...values), max: Math.max(...values) };
  }
}

const openFacets = new Set(["generation", "fuel", "transmission", "features", "site"]);
function renderFacets() {
  const html = Object.entries(DIMENSIONS).filter(([, d]) => d.facet).map(([name, dim]) => {
    // Bij "moet alles hebben" telt de eigen selectie mee: de teller toont wat er overblijft.
    const base = dim.requireAll ? filtered() : filtered(name);
    const counts = new Map();
    for (const car of base) for (const v of new Set(dimValues(car, dim))) counts.set(String(v), (counts.get(String(v)) || 0) + 1);
    if (dim.requireAll) counts.delete(UNKNOWN);
    const selected = state.facets[name] || new Set();
    for (const v of selected) if (!counts.has(v)) counts.set(v, 0);
    const entries = [...counts.entries()].sort((a, b) => {
      if (dim.ordered) return a[0].localeCompare(b[0], "nl", { numeric: true });
      if (a[0] === UNKNOWN) return 1;
      if (b[0] === UNKNOWN) return -1;
      return b[1] - a[1] || a[0].localeCompare(b[0], "nl");
    });
    if (!entries.length) return "";
    const items = entries.map(([value, count]) => `
      <label class="facet-item ${count ? "" : "empty"}">
        <input type="checkbox" data-facet="${name}" value="${esc(value)}" ${selected.has(value) ? "checked" : ""}>
        <span class="label">${esc(dimLabel(dim, value))}</span>
        <span class="count">${numberFormat.format(count)}</span>
      </label>`).join("");
    const badge = selected.size ? ` <span class="n">(${selected.size})</span>` : "";
    return `<details class="facet" data-name="${name}" ${openFacets.has(name) || selected.size ? "open" : ""}>
      <summary>${esc(dim.label)}${badge}</summary>
      ${dim.requireAll ? `<p class="facet-note">Toont auto's met álle gekozen opties. ${esc(optionCoverageText())}</p>` : ""}
      <div class="facet-list">${items}</div>
    </details>`;
  }).join("");
  const container = $("facetFilters");
  const scrolls = new Map([...container.querySelectorAll(".facet")].map((el) => [el.dataset.name, el.querySelector(".facet-list").scrollTop]));
  container.innerHTML = html;
  container.querySelectorAll(".facet").forEach((el) => {
    el.querySelector(".facet-list").scrollTop = scrolls.get(el.dataset.name) || 0;
    el.addEventListener("toggle", () => {
      if (el.open) openFacets.add(el.dataset.name); else openFacets.delete(el.dataset.name);
    });
  });
}

function optionCoverageText() {
  const withList = state.cars.filter((c) => c.options?.length).length;
  const without = state.cars.length - withList;
  return without ? `Van ${numberFormat.format(without)} auto's is geen optielijst bekend; die worden alleen op de advertentietitel herkend en kunnen dus ten onrechte ontbreken.` : "";
}

function renderChips() {
  const chips = [];
  if (state.q.trim()) chips.push({ text: `Zoek: ${state.q.trim()}`, clear: () => { state.q = ""; $("search").value = ""; } });
  for (const r of RANGES) {
    const range = state.ranges[r.key];
    if (!range) continue;
    const text = `${r.label}: ${range.min ?? "…"} – ${range.max ?? "…"}`;
    chips.push({ text, clear: () => delete state.ranges[r.key] });
  }
  for (const [name, selected] of Object.entries(state.facets)) {
    const dim = DIMENSIONS[name];
    for (const value of selected) {
      chips.push({ text: `${dim.label}: ${dimLabel(dim, value)}`, clear: () => selected.delete(value) });
    }
  }
  const box = $("chips");
  box.innerHTML = "";
  for (const chip of chips) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip";
    button.textContent = chip.text;
    button.title = "Filter verwijderen";
    button.addEventListener("click", () => { chip.clear(); update(); });
    box.append(button);
  }
}

function applyDimensionFilter(dimName, rawValue) {
  const dim = DIMENSIONS[dimName];
  if (rawValue === OTHER) return;
  if (dim.facet) {
    const selected = state.facets[dimName] || (state.facets[dimName] = new Set());
    const value = String(rawValue);
    if (selected.has(value)) selected.delete(value); else selected.add(value);
  } else if (rawValue !== UNKNOWN) {
    const number = Number(rawValue);
    if (dim.band) state.ranges[dim.band] = { min: number, max: number + dim.step - 1 };
    else if (dim.rangeKey) state.ranges[dim.rangeKey] = { min: number, max: number };
  }
}

/* ---------- kerncijfers ---------- */

function renderTiles(cars) {
  const tile = (label, value) => `<div class="tile"><div class="k">${esc(label)}</div><div class="v">${esc(value)}</div></div>`;
  const year = median(cars.map((c) => c.year));
  $("tiles").innerHTML = [
    tile("Auto's in selectie", numberFormat.format(cars.length)),
    tile("Mediaan prijs", euro(median(cars.map((c) => c.price_eur)))),
    tile("Mediaan kilometerstand", km(median(cars.map((c) => c.mileage_km)))),
    tile("Mediaan bouwjaar", year == null ? "–" : String(Math.round(year))),
  ].join("");
}

/* ---------- doorsnijding ---------- */

function groupBy(cars, dim) {
  const groups = new Map();
  for (const car of cars) {
    for (const value of new Set(dimValues(car, dim))) {
      if (!groups.has(value)) groups.set(value, []);
      groups.get(value).push(car);
    }
  }
  return groups;
}

function orderValues(groups, dim) {
  const entries = [...groups.entries()];
  if (dim.ordered) {
    return entries.sort(([a], [b]) => {
      if (a === UNKNOWN) return 1;
      if (b === UNKNOWN) return -1;
      return typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b), "nl", { numeric: true });
    });
  }
  return entries.sort(([a, x], [b, y]) => {
    if (a === UNKNOWN) return 1;
    if (b === UNKNOWN) return -1;
    return y.length - x.length;
  });
}

function foldTail(entries, dim, limit) {
  if (dim.ordered || entries.length <= limit) return entries;
  const kept = entries.slice(0, limit - 1);
  const seen = new Set();
  const rest = [];
  for (const [, cars] of entries.slice(limit - 1)) {
    for (const car of cars) if (!seen.has(car)) { seen.add(car); rest.push(car); }
  }
  return [...kept, [OTHER, rest]];
}

function renderPivot(cars) {
  const { row, col, metric } = state.pivot;
  const box = $("pivot");
  if (!cars.length) { box.innerHTML = `<p class="empty-state">Geen auto's in deze selectie.</p>`; return; }
  if (!col || col === row) renderBars(cars, row, metric, box);
  else renderHeatTable(cars, row, col, metric, box);
}

function renderBars(cars, rowName, metricName, box) {
  const dim = DIMENSIONS[rowName];
  const metric = METRICS[metricName];
  const rows = foldTail(orderValues(groupBy(cars, dim), dim), dim, 20)
    .map(([value, group]) => ({ value, group, result: metric.calc(group) }));
  const known = rows.map((r) => r.result).filter((v) => v != null);
  const max = known.length ? Math.max(...known) : 1;
  box.innerHTML = `<div class="bars">${rows.map((r, i) => {
    const width = r.result == null || max <= 0 ? 0 : Math.max(0.5, (r.result / max) * 100);
    const label = dimLabel(dim, r.value);
    const title = `${label}: ${metric.format(r.result)} (${numberFormat.format(r.group.length)} auto's)`;
    const isStatic = r.value === OTHER;
    return `<button type="button" class="bar-row ${isStatic ? "static" : ""}" data-i="${i}" title="${esc(title)}">
      <span class="bar-label">${esc(label)}</span>
      <span class="bar-track"><span class="bar-fill" style="display:block;width:${width}%"></span></span>
      <span class="bar-value">${esc(metric.format(r.result))}</span>
    </button>`;
  }).join("")}</div>`;
  box.querySelectorAll(".bar-row").forEach((button) => {
    button.addEventListener("click", () => {
      applyDimensionFilter(rowName, rows[Number(button.dataset.i)].value);
      update();
    });
  });
}

function renderHeatTable(cars, rowName, colName, metricName, box) {
  const rowDim = DIMENSIONS[rowName];
  const colDim = DIMENSIONS[colName];
  const metric = METRICS[metricName];
  const rows = foldTail(orderValues(groupBy(cars, rowDim), rowDim), rowDim, 20);
  const cols = foldTail(orderValues(groupBy(cars, colDim), colDim), colDim, 10);
  const colSets = cols.map(([, group]) => new Set(group));
  const matrix = rows.map(([, group]) => colSets.map((set) => {
    const cell = group.filter((car) => set.has(car));
    return { cars: cell, value: cell.length ? metric.calc(cell) : null };
  }));
  const values = matrix.flat().map((c) => c.value).filter((v) => v != null);
  const low = values.length ? Math.min(...values) : 0;
  const high = values.length ? Math.max(...values) : 1;
  const shade = (value) => {
    const position = high === low ? 0.5 : (value - low) / (high - low);
    const step = Math.min(SEQUENTIAL.length - 1, Math.floor(position * SEQUENTIAL.length));
    return { background: SEQUENTIAL[step], color: step >= 3 ? "#ffffff" : "#0b0b0b" };
  };
  const head = cols.map(([value]) => `<th scope="col">${esc(dimLabel(colDim, value))}</th>`).join("");
  const body = rows.map(([rowValue, group], r) => {
    const cells = matrix[r].map((cell, c) => {
      if (cell.value == null) return `<td><span class="cell-empty">–</span></td>`;
      const style = shade(cell.value);
      const title = `${dimLabel(rowDim, rowValue)} × ${dimLabel(colDim, cols[c][0])}: ${metric.format(cell.value)} (${numberFormat.format(cell.cars.length)} auto's)`;
      return `<td><button type="button" class="cell" data-r="${r}" data-c="${c}" title="${esc(title)}" style="background:${style.background};color:${style.color}">${esc(metric.format(cell.value))}</button></td>`;
    }).join("");
    return `<tr><th scope="row" class="rowh">${esc(dimLabel(rowDim, rowValue))}</th>${cells}<td class="tot">${esc(metric.format(metric.calc(group)))}</td></tr>`;
  }).join("");
  box.innerHTML = `<div class="pivot-wrap"><table class="pivot">
    <thead><tr><th class="rowh" scope="col">${esc(rowDim.label)} \\ ${esc(colDim.label)}</th>${head}<th scope="col">Totaal</th></tr></thead>
    <tbody>${body}</tbody></table></div>`;
  box.querySelectorAll(".cell").forEach((button) => {
    button.addEventListener("click", () => {
      applyDimensionFilter(rowName, rows[Number(button.dataset.r)][0]);
      applyDimensionFilter(colName, cols[Number(button.dataset.c)][0]);
      update();
    });
  });
}

/* ---------- spreidingsplot ---------- */

/** Kleur volgt de categorie, niet de rang in de huidige selectie: filteren kleurt niets om.
 *  Maximaal drie kleuren: alleen die blijven onderling onderscheidbaar bij overlappende punten. */
function buildColorMap() {
  state.colorMap = new Map();
  const dim = DIMENSIONS[state.scatter.color];
  const entries = orderValues(groupBy(state.cars, dim), { ...dim, ordered: false })
    .filter(([value]) => value !== UNKNOWN).slice(0, 3);
  entries.forEach(([value], i) => state.colorMap.set(value, i));
}
function seriesVar(car) {
  const dim = DIMENSIONS[state.scatter.color];
  const slot = state.colorMap.get(dimValues(car, dim)[0]);
  return slot == null ? "var(--series-other)" : `var(--series-${slot + 1})`;
}

function niceTicks(min, max, count = 6, integer = false) {
  if (min === max) { max = min + 1; }
  const rough = (max - min) / count;
  const power = 10 ** Math.floor(Math.log10(rough));
  const fraction = rough / power;
  let step = (fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10) * power;
  if (integer) step = Math.max(1, Math.round(step));
  const start = Math.floor(min / step) * step;
  const ticks = [];
  for (let v = start; v <= max + step * 0.999; v += step) ticks.push(Number(v.toFixed(6)));
  return ticks;
}

let scatterPoints = [];
function renderScatter(cars) {
  const xKey = state.scatter.x;
  const xInfo = SCATTER_X[xKey];
  $("scatterTitle").textContent = `Prijs tegenover ${xInfo.title}`;
  const dim = DIMENSIONS[state.scatter.color];
  const usable = cars.filter((c) => c[xKey] != null && c.price_eur != null);
  const legend = [...state.colorMap.entries()].map(([value, slot]) =>
    `<span><i style="background:var(--series-${slot + 1})"></i>${esc(dimLabel(dim, value))}</span>`);
  legend.push(`<span><i style="background:var(--series-other)"></i>Overige waarden</span>`);
  $("scatterLegend").innerHTML = legend.join("");

  const box = $("scatter");
  scatterPoints = [];
  if (!usable.length) { box.innerHTML = `<p class="empty-state">Geen auto's met deze gegevens.</p>`; return; }

  const width = Math.max(320, box.clientWidth || 800);
  const height = width < 560 ? 300 : 380;
  const margin = { top: 10, right: 30, bottom: 42, left: 62 };
  const xs = usable.map((c) => c[xKey]);
  const ys = usable.map((c) => c.price_eur);
  const xTicks = niceTicks(Math.min(...xs), Math.max(...xs), width < 560 ? 4 : 7, xKey === "year");
  const yTicks = niceTicks(0, Math.max(...ys), 5);
  const xMin = xTicks[0], xMax = xTicks[xTicks.length - 1], yMax = yTicks[yTicks.length - 1];
  const scaleX = (v) => margin.left + ((v - xMin) / (xMax - xMin || 1)) * (width - margin.left - margin.right);
  const scaleY = (v) => height - margin.bottom - (v / (yMax || 1)) * (height - margin.top - margin.bottom);

  const grid = yTicks.map((t) => `
    <line class="${t === 0 ? "baseline" : "gridline"}" x1="${margin.left}" x2="${width - margin.right}" y1="${scaleY(t)}" y2="${scaleY(t)}"></line>
    <text x="${margin.left - 8}" y="${scaleY(t) + 4}" text-anchor="end">${esc(euro(t))}</text>`).join("");
  const xLabels = xTicks.map((t) => `<text x="${scaleX(t)}" y="${height - margin.bottom + 18}" text-anchor="middle">${esc(xInfo.format(t))}</text>`).join("");
  scatterPoints = usable.map((car) => ({ car, x: scaleX(car[xKey]), y: scaleY(car.price_eur) }));
  const dots = scatterPoints.map((p, i) => `<circle data-i="${i}" cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="4" fill="${seriesVar(p.car)}"></circle>`).join("");

  box.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Spreidingsplot van prijs tegenover ${esc(xInfo.title)}; dezelfde gegevens staan in de tabel hieronder">
    ${grid}${xLabels}
    <text x="${(width + margin.left) / 2}" y="${height - 6}" text-anchor="middle">${esc(xInfo.label)}</text>
    ${dots}
  </svg>`;
}

function nearestPoint(event) {
  const svg = $("scatter").querySelector("svg");
  if (!svg || !scatterPoints.length) return null;
  const rect = svg.getBoundingClientRect();
  const scale = svg.viewBox.baseVal.width / rect.width;
  const x = (event.clientX - rect.left) * scale;
  const y = (event.clientY - rect.top) * scale;
  let best = null, bestDistance = 24 * 24;
  scatterPoints.forEach((point, index) => {
    const distance = (point.x - x) ** 2 + (point.y - y) ** 2;
    if (distance < bestDistance) { bestDistance = distance; best = index; }
  });
  return best;
}

function setupScatterHover() {
  const box = $("scatter");
  const tip = $("tooltip");
  let active = null;
  const clear = () => {
    if (active) active.classList.remove("active");
    active = null;
    tip.hidden = true;
    box.style.cursor = "";
  };
  box.addEventListener("pointermove", (event) => {
    const index = nearestPoint(event);
    if (index == null) { clear(); return; }
    const dot = box.querySelector(`circle[data-i="${index}"]`);
    if (dot !== active) {
      if (active) active.classList.remove("active");
      active = dot;
      dot.classList.add("active");
      dot.parentNode.append(dot);
    }
    const { car } = scatterPoints[index];
    tip.innerHTML = `<strong>${esc(euro(car.price_eur))}</strong>
      ${esc(car.title || "BMW X1")}<br>
      ${esc(km(car.mileage_km))} · ${esc(car.year ?? "–")} · ${esc(car.fuel || "–")}${car.power_hp ? ` · ${esc(car.power_hp)} pk` : ""}<br>
      ${esc(car.city || "")}${car.city ? " · " : ""}klik om te openen`;
    tip.hidden = false;
    const x = Math.min(event.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
    const y = Math.min(event.clientY + 14, window.innerHeight - tip.offsetHeight - 8);
    tip.style.left = `${Math.max(8, x)}px`;
    tip.style.top = `${Math.max(8, y)}px`;
    box.style.cursor = "pointer";
  });
  box.addEventListener("pointerleave", clear);
  box.addEventListener("click", (event) => {
    const index = nearestPoint(event);
    if (index == null) return;
    window.open(safeUrl(scatterPoints[index].car.sources[0].url), "_blank", "noopener,noreferrer");
  });
}

/* ---------- tabel ---------- */

function compareCars(a, b) {
  const { key, dir } = state.sort;
  const x = a[key], y = b[key];
  if (x == null && y == null) return 0;
  if (x == null) return 1;
  if (y == null) return -1;
  return (typeof x === "number" ? x - y : String(x).localeCompare(String(y), "nl")) * dir;
}

function renderTable(cars) {
  $("resultsTitle").textContent = `${numberFormat.format(cars.length)} auto's`;
  const sorted = [...cars].sort(compareCars);
  const pages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  state.page = Math.min(state.page, pages - 1);
  const visible = sorted.slice(state.page * PAGE_SIZE, (state.page + 1) * PAGE_SIZE);

  const head = TABLE_COLUMNS.map((column) => {
    const cls = column.num ? ' class="num"' : "";
    if (!column.key) return `<th${cls}>${esc(column.label)}</th>`;
    const active = state.sort.key === column.key;
    const sortState = active ? (state.sort.dir > 0 ? "ascending" : "descending") : "none";
    const arrow = active ? (state.sort.dir > 0 ? " ↑" : " ↓") : "";
    return `<th${cls} aria-sort="${sortState}"><button type="button" data-sort="${column.key}">${esc(column.label)}${arrow}</button></th>`;
  }).join("");

  const rows = visible.map((car) => {
    const meta = [car.variant, car.trim, car.color, car.license_plate].filter(Boolean).join(" · ");
    const features = (car.features || []).join(", ") + (car.features_source === "titel" ? " (uit titel)" : "");
    const image = car.image_url
      ? `<img class="thumb" loading="lazy" referrerpolicy="no-referrer" alt="" src="${esc(safeUrl(car.image_url))}">`
      : `<div class="thumb"></div>`;
    const links = car.sources.map((source) => {
      const price = source.price_eur ? ` ${source.price_is_bid ? "bieden vanaf " : ""}${euro(source.price_eur)}` : "";
      return `<a class="site-link" href="${esc(safeUrl(source.url))}" target="_blank" rel="noopener noreferrer">${esc(SITE_NAMES[source.site] || source.site)}${esc(price)}</a>`;
    }).join("");
    const location = [car.city, car.province].filter(Boolean).join(", ");
    return `<tr>
      <td>${image}</td>
      <td class="title-cell"><div class="car-title">${esc(car.title || "BMW X1")}</div><div class="car-meta">${esc(meta)}</div>${car.features?.length ? `<div class="car-features">${esc(features)}</div>` : ""}</td>
      <td class="num">${esc(euro(car.price_eur))}</td>
      <td class="num">${esc(car.mileage_km == null ? "–" : numberFormat.format(car.mileage_km))}</td>
      <td class="num">${esc(car.year ?? "–")}</td>
      <td>${esc(car.fuel || "–")}</td>
      <td>${esc(car.transmission || "–")}</td>
      <td class="num">${esc(car.power_hp ?? "–")}</td>
      <td>${esc(location || "–")}<div class="car-meta">${esc(car.seller_name || car.seller_type || "")}</div></td>
      <td>${links}</td>
    </tr>`;
  }).join("");
  $("results").innerHTML = `<thead><tr>${head}</tr></thead><tbody>${rows || `<tr><td colspan="${TABLE_COLUMNS.length}" class="empty-state">Geen auto's in deze selectie.</td></tr>`}</tbody>`;
  $("pager").innerHTML = pages > 1 ? `
    <button class="btn" type="button" data-page="-1" ${state.page === 0 ? "disabled" : ""}>Vorige</button>
    <span>Pagina ${state.page + 1} van ${pages}</span>
    <button class="btn" type="button" data-page="1" ${state.page >= pages - 1 ? "disabled" : ""}>Volgende</button>` : "";
}

/* ---------- opbouw ---------- */

let lastCars = [];
function update() {
  const cars = filtered();
  lastCars = cars;
  state.page = 0;
  renderAll(cars);
}
function renderAll(cars) {
  syncRangeInputs();
  renderFacets();
  renderChips();
  renderTiles(cars);
  renderPivot(cars);
  renderScatter(cars);
  renderTable(cars);
}

function fillSelect(select, options, value) {
  select.innerHTML = options.map(([k, label]) => `<option value="${esc(k)}">${esc(label)}</option>`).join("");
  select.value = value;
}

function setupControls() {
  const dims = Object.entries(DIMENSIONS).map(([k, d]) => [k, d.label]);
  fillSelect($("pivotRow"), dims, state.pivot.row);
  fillSelect($("pivotCol"), [["", "Geen"], ...dims], state.pivot.col);
  fillSelect($("pivotMetric"), Object.entries(METRICS).map(([k, m]) => [k, m.label]), state.pivot.metric);
  fillSelect($("scatterX"), Object.entries(SCATTER_X).map(([k, x]) => [k, x.label]), state.scatter.x);
  const colorDims = Object.entries(DIMENSIONS).filter(([, d]) => d.facet && !d.multi).map(([k, d]) => [k, d.label]);
  fillSelect($("scatterColor"), colorDims, state.scatter.color);

  $("pivotRow").addEventListener("change", (e) => { state.pivot.row = e.target.value; renderPivot(lastCars); });
  $("pivotCol").addEventListener("change", (e) => { state.pivot.col = e.target.value; renderPivot(lastCars); });
  $("pivotMetric").addEventListener("change", (e) => { state.pivot.metric = e.target.value; renderPivot(lastCars); });
  $("scatterX").addEventListener("change", (e) => { state.scatter.x = e.target.value; renderScatter(lastCars); });
  $("scatterColor").addEventListener("change", (e) => { state.scatter.color = e.target.value; buildColorMap(); renderScatter(lastCars); });

  let searchTimer;
  $("search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.q = e.target.value; update(); }, 150);
  });
  $("rangeFilters").addEventListener("change", (e) => {
    const input = e.target.closest("[data-range]");
    if (!input) return;
    setRange(input.dataset.range, input.dataset.bound, input.value === "" ? null : Number(input.value));
    update();
  });
  $("facetFilters").addEventListener("change", (e) => {
    const input = e.target.closest("[data-facet]");
    if (!input) return;
    const selected = state.facets[input.dataset.facet] || (state.facets[input.dataset.facet] = new Set());
    if (input.checked) selected.add(input.value); else selected.delete(input.value);
    update();
  });
  $("resetBtn").addEventListener("click", () => {
    state.q = "";
    state.ranges = {};
    state.facets = {};
    $("search").value = "";
    update();
  });
  $("results").addEventListener("click", (e) => {
    const button = e.target.closest("[data-sort]");
    if (!button) return;
    const key = button.dataset.sort;
    state.sort = state.sort.key === key ? { key, dir: -state.sort.dir } : { key, dir: 1 };
    renderTable(lastCars);
  });
  $("pager").addEventListener("click", (e) => {
    const button = e.target.closest("[data-page]");
    if (!button) return;
    state.page += Number(button.dataset.page);
    renderTable(lastCars);
    $("resultsTitle").scrollIntoView({ block: "start" });
  });
  $("toggleFilters").addEventListener("click", () => {
    const open = $("filters").classList.toggle("open");
    $("toggleFilters").setAttribute("aria-expanded", String(open));
  });
  $("fileInput").addEventListener("change", async (e) => {
    const [file] = e.target.files;
    if (!file) return;
    try {
      load(JSON.parse(await file.text()), `Bestand: ${file.name}`);
    } catch (error) {
      showError(`Dit bestand kon niet worden gelezen: ${error.message}`);
    }
    e.target.value = "";
  });
  $("exportBtn").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(lastCars, null, 1)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "bmw-x1-selectie.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  });
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => renderScatter(lastCars), 150);
  });
}

function showError(message) {
  const box = $("loadError");
  box.hidden = false;
  box.innerHTML = message;
}

function load(cars, info) {
  if (!Array.isArray(cars)) throw new Error("verwacht een JSON-array met auto's");
  state.cars = cars.map((car) => ({ ...car, sources: Array.isArray(car.sources) ? car.sources : [] }));
  $("loadError").hidden = true;
  $("dataInfo").textContent = info;
  computeRangeStats();
  buildColorMap();
  update();
}

function renderReport(report) {
  if (!report?.sites?.length) return;
  const rows = report.sites.map((site) => `<tr>
    <td>${esc(SITE_NAMES[site.site] || site.site)}</td>
    <td>${esc(site.status)}</td>
    <td class="num">${numberFormat.format(site.collected ?? 0)}</td>
    <td class="num">${site.expected == null ? "–" : numberFormat.format(site.expected)}</td>
    <td class="num">${numberFormat.format(site.skipped ?? 0)}</td>
    <td>${esc(new Date(site.scraped_at).toLocaleString("nl-NL"))}</td>
  </tr>`).join("");
  $("sourcesBody").innerHTML = `<table>
    <thead><tr><th>Site</th><th>Status</th><th class="num">Opgehaald</th><th class="num">Volgens site</th><th class="num">Nieuw, overgeslagen</th><th>Moment</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
  $("sourcesPanel").hidden = false;
  const stamp = new Date(report.generated_at).toLocaleString("nl-NL");
  $("dataInfo").textContent = `${numberFormat.format(report.cars)} unieke auto's uit ${numberFormat.format(report.ads)} advertenties · bijgewerkt ${stamp}`;
}

async function init() {
  buildRangeFilters();
  setupControls();
  setupScatterHover();
  try {
    const response = await fetch("../data/listings.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    load(await response.json(), "");
    const report = await fetch("../data/report.json", { cache: "no-store" });
    if (report.ok) renderReport(await report.json());
  } catch {
    $("dataInfo").textContent = "Nog geen gegevens geladen";
    showError(`<strong>Geen gegevens gevonden.</strong> Draai eerst <code>python3 -m scraper</code>, start daarna vanuit de projectmap <code>python3 -m http.server 8000</code> en open <code>http://localhost:8000/web/</code>. Je kunt ook hierboven een JSON-bestand openen.`);
  }
}

init();
