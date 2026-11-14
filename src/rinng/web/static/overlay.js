// Primitive vẽ lớp phủ của rinng lên series nến (Lightweight Charts 5.x plugin API):
// vùng (zones), mức ngang (levels) và volume profile theo kỳ (profiles).
// Thời gian tùy ý (không trùng mốc nến) được đổi sang chỉ số logical có phần lẻ rồi sang pixel.

function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

function fmtVol(v) {
  const a = Math.abs(v);
  const s = a >= 1e6 ? (a / 1e6).toFixed(1) + "M" : a >= 1e3 ? (a / 1e3).toFixed(1) + "k" : a.toFixed(0);
  return (v >= 0 ? "+" : "−") + s;
}

export class RinngOverlay {
  constructor(times) {
    this.times = times; // giây UTC, tăng dần, mốc mở nến
    this.zones = [];
    this.levels = [];
    this.profiles = [];
    this._view = { zOrder: () => "bottom", renderer: () => ({ draw: () => {}, drawBackground: (t) => this._drawBg(t) }) };
    this._top = { zOrder: () => "top", renderer: () => ({ draw: (t) => this._drawTop(t) }) };
  }

  set(data) {
    this.zones = data.zones || [];
    this.levels = data.levels || [];
    this.profiles = data.profiles || [];
    this._request && this._request();
  }

  attached({ chart, series, requestUpdate }) {
    this._chart = chart;
    this._series = series;
    this._request = requestUpdate;
  }

  detached() {
    this._chart = this._series = this._request = null;
  }

  paneViews() {
    return [this._view, this._top];
  }

  // Thời gian → chỉ số logical (nội suy giữa hai mốc nến; ngoại suy sau nến cuối).
  _logical(t) {
    const ts = this.times;
    if (!ts.length) return null;
    if (t <= ts[0]) return 0;
    const n = ts.length;
    if (t >= ts[n - 1]) {
      const step = n > 1 ? ts[n - 1] - ts[n - 2] : 1;
      return n - 1 + (t - ts[n - 1]) / step;
    }
    let lo = 0, hi = n - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (ts[mid] <= t) lo = mid; else hi = mid;
    }
    return lo + (t - ts[lo]) / (ts[hi] - ts[lo]);
  }

  _x(t, fallback) {
    if (t == null) return fallback;
    const l = this._logical(t);
    const x = l == null ? null : this._chart.timeScale().logicalToCoordinate(l);
    return x == null ? fallback : x;
  }

  _y(p) {
    return this._series.priceToCoordinate(p);
  }

  _drawBg(target) {
    if (!this._chart) return;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const right = mediaSize.width;
      for (const z of this.zones) {
        const x0 = this._x(z.t0, 0), x1 = this._x(z.t1, right);
        const y0 = this._y(z.p1), y1 = this._y(z.p0);
        if (y0 == null || y1 == null || x1 < 0 || x0 > right) continue;
        const a = z.style === "faint" ? 0.035 : z.style === "light" ? 0.13 : 0.2;
        ctx.fillStyle = hexA(z.color, z.t1 ? a * 0.5 : a);
        ctx.fillRect(x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0));
        if (z.style === "dash" || z.style === "solid") {
          ctx.strokeStyle = hexA(z.color, z.t1 ? 0.3 : 0.6);
          ctx.setLineDash(z.style === "dash" ? [4, 3] : []);
          ctx.strokeRect(x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0));
          ctx.setLineDash([]);
        }
        if (z.label && x1 - x0 > 24 && y1 - y0 > 9) {
          ctx.fillStyle = hexA(z.color, 0.8);
          ctx.font = "10px system-ui";
          ctx.fillText(z.label, x0 + 3, y0 + 10);
        }
      }
      for (const p of this.profiles) this._drawProfile(ctx, p, right);
    });
  }

  _drawProfile(ctx, p, right) {
    const x0 = this._x(p.t0, null), x1 = this._x(p.t1, null);
    if (x0 == null || x1 == null || x1 < 0 || x0 > right) return;
    const width = (x1 - x0) * 0.85;
    let mx = 0;
    for (const r of p.rows) mx = Math.max(mx, r[2] + r[3]);
    if (mx <= 0) return;
    const fade = p.closed ? 1 : 0.5;
    let top = Infinity, bottom = -Infinity;
    for (const [lo, hi, buy, sell] of p.rows) {
      const yHi = this._y(hi), yLo = this._y(lo);
      if (yHi == null || yLo == null) continue;
      top = Math.min(top, yHi);
      bottom = Math.max(bottom, yLo);
      const h = Math.max(1, yLo - yHi - 0.5);
      const inVa = hi > p.val && lo < p.vah;
      const isPoc = lo <= p.poc && p.poc <= hi;
      const a = (isPoc ? 0.95 : inVa ? 0.75 : 0.35) * fade;
      const wb = (width * buy) / mx, ws = (width * sell) / mx;
      ctx.fillStyle = `rgba(38,166,154,${a})`;
      ctx.fillRect(x0, yHi, wb, h);
      ctx.fillStyle = `rgba(239,83,80,${a})`;
      ctx.fillRect(x0 + wb, yHi, ws, h);
      if (isPoc) {
        ctx.strokeStyle = `rgba(255,152,0,${fade})`;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(x0, yHi, wb + ws, h);
      }
    }
    const yPoc = this._y(p.poc);
    if (yPoc != null) {
      ctx.strokeStyle = `rgba(255,152,0,${0.9 * fade})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x0, yPoc);
      ctx.lineTo(x1, yPoc);
      ctx.stroke();
    }
    if (Number.isFinite(top)) {
      const colors = { D: "#90a4ae", P: "#26a69a", b: "#ef5350", DD: "#ab47bc" };
      ctx.font = "bold 11px system-ui";
      const text = p.shape + (p.closed ? "" : "…");
      const w = ctx.measureText(text).width + 8;
      ctx.fillStyle = colors[p.shape] || "#90a4ae";
      ctx.globalAlpha = fade;
      ctx.fillRect(x0, top - 18, w, 15);
      ctx.fillStyle = "#111";
      ctx.fillText(text, x0 + 4, top - 7);
      ctx.globalAlpha = 1;
      const delta = p.buy - p.sell;
      ctx.font = "10px system-ui";
      ctx.fillStyle = delta >= 0 ? "#26a69a" : "#ef5350";
      ctx.fillText(fmtVol(delta), x0, bottom + 12);
    }
  }

  _drawTop(target) {
    if (!this._chart) return;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const right = mediaSize.width;
      for (const l of this.levels) {
        const y = this._y(l.price);
        if (y == null) continue;
        const x0 = this._x(l.t0, 0), x1 = this._x(l.t1, right);
        if (x1 < 0 || x0 > right) continue;
        ctx.strokeStyle = hexA(l.color, l.t1 && l.t1 < this.times[this.times.length - 1] ? 0.45 : 0.9);
        ctx.lineWidth = 1;
        ctx.setLineDash(l.dash ? [5, 4] : []);
        ctx.beginPath();
        ctx.moveTo(x0, y);
        ctx.lineTo(x1, y);
        ctx.stroke();
        ctx.setLineDash([]);
        if (l.label) {
          ctx.font = "10px system-ui";
          ctx.fillStyle = hexA(l.color, 0.95);
          ctx.fillText(l.label, Math.min(x1, right - 40) - ctx.measureText(l.label).width - 2, y - 3);
        }
      }
    });
  }
}
