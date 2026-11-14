"""Chart nến có lớp phủ (Plotly). Chỉ đọc frame, không tính toán phân tích.

Cách vẽ Events theo hình dạng, không theo tên module, để module mới vẽ được ngay:
- Vùng (price_low < price_high): hình chữ nhật từ event_time tới invalidated_at (hoặc hết chart).
- Mức (price_low == price_high): đường ngang ngắn từ event_time tới invalidated_at / hết chart,
  riêng swing_high/swing_low vẽ thành điểm kèm nhãn HH/HL/LH/LL.
Màu chọn theo từ khóa trong `kind` (bull/high/buy → xanh, bear/low/sell → đỏ, còn lại xám).
"""

import json
from collections.abc import Sequence

import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

BULL = "rgba(38,166,154,{a})"
BEAR = "rgba(239,83,80,{a})"
NEUTRAL = "rgba(120,144,156,{a})"
POC = "rgba(255,152,0,{a})"


def _color(kind: str, alpha: float) -> str:
    k = kind.lower()
    if "poc" in k or "value_area" in k:
        return POC.format(a=alpha)
    if any(w in k for w in ("bull", "_up", "high", "buy", "demand", "long")):
        return BULL.format(a=alpha)
    if any(w in k for w in ("bear", "_down", "low", "sell", "supply", "short")):
        return BEAR.format(a=alpha)
    return NEUTRAL.format(a=alpha)


def candles(
    ohlcv: pl.DataFrame,
    *,
    events: pl.DataFrame | None = None,
    kinds: Sequence[str] | None = None,
    panels: dict[str, pl.DataFrame] | None = None,
    profile: pl.DataFrame | None = None,
    title: str = "",
    max_events: int = 400,
) -> go.Figure:
    """Vẽ nến.

    - `events`: frame theo EVENT_SCHEMA; `kinds` lọc loại cần vẽ.
    - `panels`: {tên panel: frame có cột open_time và các cột giá trị} vẽ bên dưới.
    - `profile`: frame (price_low, price_high, volume) vẽ thành volume profile bên phải.
    """
    panels = panels or {}
    rows = 1 + len(panels)
    cols = 2 if profile is not None else 1
    fig = make_subplots(
        rows=rows,
        cols=cols,
        shared_xaxes=True,
        shared_yaxes=False,
        column_widths=[0.85, 0.15] if cols == 2 else None,
        row_heights=[0.7] + [0.3 / max(1, len(panels))] * len(panels) if panels else None,
        vertical_spacing=0.02,
        horizontal_spacing=0.01,
    )
    fig.add_trace(
        go.Candlestick(
            x=ohlcv["open_time"].to_list(),
            open=ohlcv["open"].to_list(),
            high=ohlcv["high"].to_list(),
            low=ohlcv["low"].to_list(),
            close=ohlcv["close"].to_list(),
            name="giá",
            increasing_line_color=BULL.format(a=1),
            decreasing_line_color=BEAR.format(a=1),
        ),
        row=1,
        col=1,
    )
    if events is not None and not events.is_empty():
        _draw_events(fig, ohlcv, events, kinds, max_events)
    for i, (name, frame) in enumerate(panels.items(), start=2):
        for col in frame.columns:
            if col == "open_time":
                continue
            fig.add_trace(
                go.Scatter(
                    x=frame["open_time"].to_list(),
                    y=frame[col].to_list(),
                    name=col,
                    mode="lines",
                    line={"width": 1},
                ),
                row=i,
                col=1,
            )
        fig.update_yaxes(title_text=name, row=i, col=1)
    if profile is not None and not profile.is_empty():
        mid = ((profile["price_low"] + profile["price_high"]) / 2).to_list()
        poc = profile["volume"].arg_max()
        colors = [POC.format(a=0.9) if j == poc else NEUTRAL.format(a=0.6) for j in range(len(mid))]
        fig.add_trace(
            go.Bar(
                x=profile["volume"].to_list(),
                y=mid,
                orientation="h",
                marker_color=colors,
                name="volume profile",
                width=(profile["price_high"] - profile["price_low"]).to_list(),
            ),
            row=1,
            col=2,
        )
        fig.update_yaxes(matches="y", row=1, col=2, showticklabels=False)
    fig.update_layout(
        title=title,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=520 + 160 * len(panels),
        margin={"l": 40, "r": 20, "t": 40, "b": 20},
        showlegend=False,
    )
    return fig


def _draw_events(fig, ohlcv, events, kinds, max_events) -> None:
    if kinds is not None:
        events = events.filter(pl.col("kind").is_in(list(kinds)))
    events = events.sort("event_time").tail(max_events)
    first, last = ohlcv["open_time"].min(), ohlcv["open_time"].max()
    events = events.filter(
        (pl.col("event_time") <= last)
        & (pl.col("invalidated_at").is_null() | (pl.col("invalidated_at") >= first))
    )
    swing_x, swing_y, swing_text, swing_color = [], [], [], []
    for e in events.iter_rows(named=True):
        kind = e["kind"]
        x0 = max(e["event_time"], first)
        x1 = e["invalidated_at"] or last
        lo, hi = e["price_low"], e["price_high"]
        if lo is None or hi is None:
            continue
        if kind in ("swing_high", "swing_low"):
            label = json.loads(e["attrs"] or "{}").get("label") or ""
            swing_x.append(e["event_time"])
            swing_y.append(hi)
            swing_text.append(label)
            swing_color.append(_color(kind, 1))
        elif hi > lo:
            fig.add_shape(
                type="rect",
                x0=x0,
                x1=x1,
                y0=lo,
                y1=hi,
                line_width=0,
                fillcolor=_color(kind, 0.18),
                row=1,
                col=1,
            )
        else:
            fig.add_shape(
                type="line",
                x0=x0,
                x1=x1,
                y0=lo,
                y1=lo,
                line={"color": _color(kind, 0.8), "width": 1, "dash": "dot"},
                row=1,
                col=1,
            )
    if swing_x:
        fig.add_trace(
            go.Scatter(
                x=swing_x,
                y=swing_y,
                mode="markers+text",
                text=swing_text,
                textposition="top center",
                marker={"size": 5, "color": swing_color},
                textfont={"size": 9},
                name="swing",
            ),
            row=1,
            col=1,
        )


def equity(
    equity_frame: pl.DataFrame, benchmarks: dict[str, pl.DataFrame] | None = None
) -> go.Figure:
    """Đường equity của backtest, kèm các baseline nếu có. Frame cần cột time, equity."""
    fig = go.Figure()
    for name, frame in {"chiến lược": equity_frame, **(benchmarks or {})}.items():
        fig.add_trace(go.Scatter(x=frame["time"].to_list(), y=frame["equity"].to_list(), name=name))
    fig.update_layout(
        template="plotly_dark", height=380, margin={"l": 40, "r": 20, "t": 30, "b": 20}
    )
    return fig
