"""Weekly volume profile chart with D / P / b / DD shape labels (Plotly, HTML export).

Same definitions as pine/rinng_overlay.pine: weeks start Monday 00:00 UTC, the profile spreads
bar volume evenly across bins, 70% value area, labels from `volume_profile.classify_shape`.
Only closed weeks get a profile; the current week is drawn faded and marked "(open)".
"""

from datetime import UTC, datetime, timedelta

import plotly.graph_objects as go
import polars as pl

from rinng.analysis.volume_profile import classify_shape, profile_from_ohlcv, value_area

SHAPE_COLORS = {"D": "#90a4ae", "P": "#26a69a", "b": "#ef5350", "DD": "#ab47bc"}


def weekly_profiles(base: pl.DataFrame, n_bins: int = 100, rows: int = 30) -> list[dict]:
    """One dict per week: start, end, closed, shape, poc, val, vah, high, hist."""
    start = base["open_time"].min()
    week0 = (start - timedelta(days=start.weekday())).replace(hour=0, minute=0, second=0)
    last_close = base["open_time"].max() + (base["open_time"][1] - base["open_time"][0])
    out = []
    w = week0
    while w <= base["open_time"].max():
        end = w + timedelta(days=7)
        part = base.filter((pl.col("open_time") >= w) & (pl.col("open_time") < end))
        if part.height > 1:
            prof = profile_from_ohlcv(part, n_bins=n_bins)
            va = value_area(prof)
            per = max(1, -(-n_bins // rows))
            hist = (
                prof.with_row_index("i")
                .group_by((pl.col("i") // per).alias("r"))
                .agg(pl.col("price_low").min(), pl.col("price_high").max(), pl.col("volume").sum())
                .sort("r")
            )
            out.append(
                {
                    "start": w,
                    "end": end,
                    "closed": w >= start and end <= last_close,
                    "shape": classify_shape(prof),
                    "poc": va.poc,
                    "val": va.val,
                    "vah": va.vah,
                    "high": float(part["high"].max()),
                    "hist": hist,
                }
            )
        w = end
    return out


def figure(display: pl.DataFrame, profiles: list[dict], title: str) -> go.Figure:
    fig = go.Figure(
        go.Candlestick(
            x=display["open_time"].to_list(),
            open=display["open"].to_list(),
            high=display["high"].to_list(),
            low=display["low"].to_list(),
            close=display["close"].to_list(),
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
            name="price",
        )
    )
    for p in profiles:
        alpha = 1.0 if p["closed"] else 0.4
        span = (p["end"] - p["start"]) * 0.7
        mx = p["hist"]["volume"].max()
        for r in p["hist"].iter_rows(named=True):
            in_va = r["price_high"] > p["val"] and r["price_low"] < p["vah"]
            has_poc = r["price_low"] <= p["poc"] <= r["price_high"]
            color = "#ff9800" if has_poc else "#78909c"
            opacity = (0.75 if has_poc else 0.45 if in_va else 0.2) * alpha
            fig.add_shape(
                type="rect",
                x0=p["start"],
                x1=p["start"] + span * (r["volume"] / mx),
                y0=r["price_low"],
                y1=r["price_high"],
                fillcolor=color,
                opacity=opacity,
                line_width=0,
                layer="below",
            )
        fig.add_shape(
            type="line",
            x0=p["start"],
            x1=p["end"],
            y0=p["poc"],
            y1=p["poc"],
            line={"color": "#ff9800", "width": 2 if p["closed"] else 1},
        )
        label = p["shape"] + ("" if p["closed"] else " (open)")
        fig.add_annotation(
            x=p["start"] + (p["end"] - p["start"]) / 2,
            y=p["high"],
            text=f"<b>{label}</b>",
            showarrow=False,
            yshift=14,
            font={"color": "white", "size": 13},
            bgcolor=SHAPE_COLORS[p["shape"]],
            opacity=alpha,
        )
    fig.update_layout(
        title=title,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        height=720,
        margin={"l": 50, "r": 20, "t": 50, "b": 30},
        showlegend=False,
    )
    return fig


def fetch_live(venue_symbol: str, base_tf: str, display_tf: str, weeks: int):
    """Fetch closed bars directly from Binance REST (no curated data needed)."""
    from rinng.exchanges.binance import Binance
    from rinng.store.schemas import OHLCV, rows_to_frame

    api = Binance()
    now = datetime.now(UTC)
    start = now - timedelta(days=now.weekday() + 7 * weeks)
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)

    def load(tf: str) -> pl.DataFrame:
        rows = [r for page in api.klines(venue_symbol, tf, start, now) for r in page]
        frame = rows_to_frame(OHLCV, rows, exchange="binance", symbol=venue_symbol, timeframe=tf)
        return frame.filter(pl.col("is_closed")).sort("open_time")

    return load(base_tf), load(display_tf)
