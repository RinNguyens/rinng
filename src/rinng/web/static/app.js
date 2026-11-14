// rinng web (classic): several tabs (workspaces), each a grid of charts; each chart has its own
// "lens" so no single screen is crammed with every parameter.
import { RinngOverlay } from "./overlay.js";

const LWC = window.LightweightCharts;
const STORE_KEY = "rinng.workspaces.v1";

const LAYOUTS = {
  "1": { cols: "1fr", rows: "1fr", n: 1 },
  "2": { cols: "1fr 1fr", rows: "1fr", n: 2 },
  "1+2": { cols: "3fr 2fr", rows: "1fr 1fr", n: 3, big: true },
  "2x2": { cols: "1fr 1fr", rows: "1fr 1fr", n: 4 },
  "3": { cols: "1fr 1fr 1fr", rows: "1fr", n: 3 },
};

const DAYS = [14, 30, 90, 180, 365, 1000, 2000];

const DEFAULT_WORKSPACES = [
  {
    name: "Overview",
    layout: "2x2",
    panels: [
      { lens: "structure", tf: "4h", days: 90 },
      { lens: "profile", tf: "4h", days: 90, period: "week" },
      { lens: "liquidity", tf: "1h", days: 30 },
      { lens: "derivatives", tf: "1h", days: 30 },
    ],
  },
  {
    name: "Volume profile",
    layout: "2",
    panels: [
      { lens: "profile", tf: "1d", days: 365, period: "week" },
      { lens: "profile", tf: "1h", days: 14, period: "day" },
    ],
  },
  {
    name: "Wyckoff / Elliott",
    layout: "1+2",
    panels: [
      { lens: "wyckoff", tf: "1d", days: 1000 },
      { lens: "wyckoff", tf: "4h", days: 180 },
      { lens: "indicators", tf: "4h", days: 180 },
    ],
  },
];

const state = {
  meta: null,
  symbol: "BTC-USDT-PERP",
  exchange: "binance",
  sync: true,
  workspaces: load(),
  active: 0,
  panels: [], // panels on screen
};

function load() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (e) { /* browser storage blocked: use defaults */ }
  return structuredClone(DEFAULT_WORKSPACES);
}

function save() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(state.workspaces)); } catch (e) { /* ignore */ }
}

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "class") e.className = v;
    else e.setAttribute(k, v);
  }
  for (const c of children) e.append(c);
  return e;
}

function select(options, value, onchange) {
  const s = el("select", { onchange: (ev) => onchange(ev.target.value) });
  for (const [v, label] of options) {
    const o = el("option", { value: v }, label);
    if (String(v) === String(value)) o.selected = true;
    s.append(o);
  }
  return s;
}

// ------------------------------------------------------------------ Panel

class Panel {
  constructor(cfg, index, host) {
    this.cfg = cfg;
    this.index = index;
    this.root = el("section", { class: "panel" });
    this.header = el("header");
    this.legend = el("div", { class: "legend" });
    this.body = el("div", { class: "chart" });
    this.status = el("span", { class: "status" });
    this.root.append(this.header, this.legend, this.body);
    host.append(this.root);
    this.renderHeader();
    this.load();
  }

  renderHeader() {
    const c = this.cfg;
    const lenses = Object.entries(state.meta.lenses);
    this.header.replaceChildren(
      select(lenses, c.lens, (v) => { c.lens = v; this.changed(); }),
      select(state.meta.timeframes.map((t) => [t, t]), c.tf, (v) => { c.tf = v; this.changed(); }),
      select(DAYS.map((d) => [d, `${d} days`]), c.days, (v) => { c.days = Number(v); this.changed(); }),
      ...(c.lens === "profile"
        ? [select([["week", "weekly profile"], ["day", "daily profile"]], c.period || "week",
            (v) => { c.period = v; this.changed(); })]
        : []),
      this.status,
    );
  }

  changed() {
    save();
    this.renderHeader();
    this.load();
  }

  async load() {
    const c = this.cfg;
    this.status.textContent = "loading…";
    const q = new URLSearchParams({
      lens: c.lens, tf: c.tf, days: c.days, period: c.period || "week",
      symbol: state.symbol, exchange: state.exchange,
    });
    let data;
    try {
      const r = await fetch(`/api/chart?${q}`);
      if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
      data = await r.json();
    } catch (e) {
      this.status.textContent = `error: ${e.message}`;
      return;
    }
    this.draw(data);
    this.status.textContent = data.source === "live" ? "data: live REST" : "data: curated";
  }

  draw(data) {
    this.chart && this.chart.remove();
    const chart = LWC.createChart(this.body, {
      autoSize: true,
      layout: { background: { color: "#16181d" }, textColor: "#b0b6c0", fontSize: 11,
        panes: { separatorColor: "#2a2e36" } },
      grid: { vertLines: { color: "#1f232a" }, horzLines: { color: "#1f232a" } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: "#2a2e36", rightOffset: 8 },
      rightPriceScale: { borderColor: "#2a2e36" },
      crosshair: { mode: 0 },
    });
    this.chart = chart;
    const candles = chart.addSeries(LWC.CandlestickSeries, {
      upColor: "#26a69a", downColor: "#ef5350", borderVisible: false,
      wickUpColor: "#26a69a", wickDownColor: "#ef5350",
    });
    candles.setData(data.candles);
    this.candles = candles;
    this.times = data.candles.map((d) => d.time);
    this.closes = data.candles.map((d) => d.close);

    const overlay = new RinngOverlay(this.times);
    candles.attachPrimitive(overlay);
    overlay.set(data);
    if (data.markers && data.markers.length) LWC.createSeriesMarkers(candles, data.markers);

    for (const ln of data.lines || []) {
      const s = chart.addSeries(LWC.LineSeries, {
        color: ln.color, lineWidth: ln.pane === 0 ? 1 : 2, priceLineVisible: false,
        lastValueVisible: ln.pane !== 0, title: ln.name,
      }, ln.pane);
      s.setData(ln.data);
      for (const g of (data.guides || []).filter((g) => g.pane === ln.pane)) {
        for (const v of g.values) s.createPriceLine({ price: v, color: "#555", lineStyle: 2, lineWidth: 1 });
      }
    }
    for (const h of data.histos || []) {
      const fmt = h.precision ? { priceFormat: { type: "price", precision: h.precision, minMove: 10 ** -h.precision } } : {};
      const s = chart.addSeries(LWC.HistogramSeries, { priceLineVisible: false, title: h.name, ...fmt }, h.pane);
      s.setData(h.data);
    }
    const panes = chart.panes();
    if (panes.length > 1) {
      panes[0].setStretchFactor(3);
      for (const p of panes.slice(1)) p.setStretchFactor(1);
    }

    this.legend.replaceChildren(
      ...(data.legend || []).map(([color, text]) =>
        el("span", {}, ...(color ? [el("i", { style: `background:${color}` })] : []), text)),
    );

    chart.timeScale().fitContent();
    chart.subscribeCrosshairMove((param) => syncCrosshair(this, param));
    chart.timeScale().subscribeVisibleTimeRangeChange((range) => syncRange(this, range));
  }

  // The candle containing time t (largest open time <= t).
  barAt(t) {
    const ts = this.times;
    if (!ts || !ts.length || t < ts[0]) return -1;
    let lo = 0, hi = ts.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (ts[mid] <= t) lo = mid; else hi = mid - 1;
    }
    return lo;
  }

  destroy() {
    this.chart && this.chart.remove();
    this.root.remove();
  }
}

// ------------------------------------------------------------------ sync

let syncing = false;

function syncCrosshair(source, param) {
  if (!state.sync || syncing) return;
  syncing = true;
  for (const p of state.panels) {
    if (p === source || !p.chart) continue;
    if (param.time === undefined) {
      p.chart.clearCrosshairPosition();
      continue;
    }
    const i = p.barAt(param.time);
    if (i >= 0) p.chart.setCrosshairPosition(p.closes[i], p.times[i], p.candles);
  }
  syncing = false;
}

function syncRange(source, range) {
  if (!state.sync || syncing || !range) return;
  syncing = true;
  for (const p of state.panels) {
    if (p === source || !p.chart || !p.times.length) continue;
    if (p.cfg.tf !== source.cfg.tf) continue; // only lock time between charts on the same timeframe
    try { p.chart.timeScale().setVisibleRange(range); } catch (e) { /* outside the data */ }
  }
  syncing = false;
}

// ------------------------------------------------------------------ UI

function renderTabs() {
  const bar = document.getElementById("tabs");
  bar.replaceChildren();
  state.workspaces.forEach((ws, i) => {
    const tab = el("button", {
      class: "tab" + (i === state.active ? " active" : ""),
      title: "Double-click to rename",
      onclick: () => { state.active = i; render(); },
      ondblclick: () => {
        const name = prompt("Tab name", ws.name);
        if (name) { ws.name = name; save(); renderTabs(); }
      },
    }, ws.name);
    if (state.workspaces.length > 1) {
      tab.append(el("span", {
        class: "close", title: "Close tab",
        onclick: (e) => {
          e.stopPropagation();
          state.workspaces.splice(i, 1);
          state.active = Math.max(0, Math.min(state.active, state.workspaces.length - 1));
          save();
          render();
        },
      }, "×"));
    }
    bar.append(tab);
  });
  bar.append(el("button", {
    class: "tab add", title: "Add tab",
    onclick: () => {
      state.workspaces.push({ name: `Tab ${state.workspaces.length + 1}`, layout: "2",
        panels: [{ lens: "structure", tf: "4h", days: 90 }, { lens: "profile", tf: "1h", days: 30, period: "week" }] });
      state.active = state.workspaces.length - 1;
      save();
      render();
    },
  }, "+"));
}

function renderControls() {
  const ws = state.workspaces[state.active];
  const box = document.getElementById("controls");
  box.replaceChildren(
    select(state.meta.instruments.map((s) => [s, s]), state.symbol, (v) => { state.symbol = v; render(); }),
    select(state.meta.exchanges.map((s) => [s, s]), state.exchange, (v) => { state.exchange = v; render(); }),
    select(Object.keys(LAYOUTS).map((k) => [k, `layout ${k}`]), ws.layout, (v) => {
      ws.layout = v;
      const lenses = Object.keys(state.meta.lenses);
      while (ws.panels.length < LAYOUTS[v].n) {
        ws.panels.push({ lens: lenses[ws.panels.length % lenses.length], tf: "4h", days: 90, period: "week" });
      }
      save();
      render();
    }),
    el("label", { class: "toggle" },
      Object.assign(el("input", { type: "checkbox", onchange: (e) => { state.sync = e.target.checked; } }),
        { checked: state.sync }),
      " sync crosshair"),
    el("button", { class: "ghost", title: "Restore default tabs", onclick: () => {
      if (!confirm("Restore the default tabs? Your current layout will be lost.")) return;
      state.workspaces = structuredClone(DEFAULT_WORKSPACES);
      state.active = 0;
      save();
      render();
    } }, "defaults"),
  );
}

function render() {
  for (const p of state.panels) p.destroy();
  state.panels = [];
  renderTabs();
  renderControls();
  const ws = state.workspaces[state.active];
  const layout = LAYOUTS[ws.layout] || LAYOUTS["2"];
  const grid = document.getElementById("grid");
  grid.style.gridTemplateColumns = layout.cols;
  grid.style.gridTemplateRows = layout.rows;
  grid.className = "grid" + (layout.big ? " big" : "");
  ws.panels.slice(0, layout.n).forEach((cfg, i) => state.panels.push(new Panel(cfg, i, grid)));
}

async function main() {
  state.meta = await (await fetch("/api/meta")).json();
  render();
}

main();
