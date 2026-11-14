"""Dashboard Streamlit. Chạy: `uv run rinng dashboard`.

Chỉ đọc dữ liệu: nến curated, events/features đã tính (hoặc tính tại chỗ nếu chưa có),
kết quả backtest trong data/results. File cấu hình lấy từ biến môi trường RINNG_CONFIG.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import streamlit as st

from rinng.config import DEFAULT_CONFIG, load_settings
from rinng.pipeline.run import analyze, load_ohlcv, read_derived
from rinng.store.paths import DataPaths
from rinng.viz.chart import candles, equity

EVENT_MODULES = ["structure", "smc", "liquidity", "volume_profile", "wyckoff", "elliott"]

st.set_page_config(page_title="rinng", layout="wide")
settings = load_settings(Path(os.environ.get("RINNG_CONFIG", DEFAULT_CONFIG)))
paths = DataPaths(settings.data_dir)

page = st.sidebar.radio("Trang", ["Chart", "Backtest"])
symbol = st.sidebar.selectbox("Instrument", [i.id for i in settings.instruments])
exchange = st.sidebar.selectbox("Sàn", ["binance", "okx"])


@st.cache_data(ttl=300)
def _load(exchange: str, symbol: str, timeframe: str, days: int) -> pl.DataFrame:
    start = datetime.now(UTC) - timedelta(days=days)
    return load_ohlcv(paths, exchange, symbol, timeframe, start)


def _events(module: str, timeframe: str, ohlcv: pl.DataFrame) -> pl.DataFrame | None:
    saved = read_derived(paths, "events", module, symbol, timeframe)
    if saved is None:
        saved = analyze(paths, exchange, symbol, timeframe, [module], write=False)[module][1]
    return saved


if page == "Chart":
    tfs = settings.timeframes
    timeframe = st.sidebar.selectbox("Khung", tfs, index=tfs.index("4h") if "4h" in tfs else 0)
    days = st.sidebar.slider("Số ngày", 7, 1500, 180)
    modules = st.sidebar.multiselect("Lớp phủ", EVENT_MODULES, default=["structure", "smc"])
    ohlcv = _load(exchange, symbol, timeframe, days)
    if ohlcv.is_empty():
        st.warning(
            f"Chưa có nến {exchange} {symbol} {timeframe}. Chạy `rinng backfill` rồi "
            "`rinng resample`."
        )
        st.stop()
    frames = [e for m in modules if (e := _events(m, timeframe, ohlcv)) is not None]
    events = pl.concat(frames) if frames else None
    kinds = None
    if events is not None and not events.is_empty():
        all_kinds = sorted(events["kind"].unique().to_list())
        default = [k for k in all_kinds if not k.startswith(("fvg", "liquidity_", "hvn", "lvn"))]
        kinds = st.sidebar.multiselect("Loại sự kiện", all_kinds, default=default)
    panels = {}
    feats = read_derived(paths, "features", "indicators", symbol, timeframe)
    if feats is None:
        feats = analyze(paths, exchange, symbol, timeframe, ["indicators"], write=False)
        feats = feats["indicators"][0]
    feats = feats.filter(pl.col("open_time") >= ohlcv["open_time"][0])
    if "rsi_14" in feats.columns:
        panels["RSI"] = feats.select("open_time", "rsi_14")
    st.plotly_chart(
        candles(
            ohlcv,
            events=events,
            kinds=kinds,
            panels=panels,
            title=f"{exchange} {symbol} {timeframe}",
        ),
        use_container_width=True,
    )
    if events is not None and not events.is_empty():
        with st.expander("Bảng sự kiện"):
            st.dataframe(
                events.filter(pl.col("kind").is_in(kinds or []))
                .sort("event_time", descending=True)
                .head(500)
            )

else:
    runs = sorted(paths.results.glob("*/summary.json")) if paths.results.exists() else []
    if not runs:
        st.info("Chưa có kết quả. Chạy `rinng backtest`.")
        st.stop()
    rows = []
    for s in runs:
        cfg = json.loads((s.parent / "config.json").read_text())
        rows.append(
            {
                "run": s.parent.name,
                **{k: cfg.get(k) for k in ("strategy", "segment", "symbol", "timeframe")},
                **json.loads(s.read_text()),
            }
        )
    table = pl.DataFrame(rows, infer_schema_length=None)
    st.caption(
        f"{len(runs)} lần chạy đã lưu. Càng thử nhiều cấu hình, kết quả tốt nhất càng dễ là do may."
    )
    st.dataframe(table)
    chosen = st.selectbox("Xem equity", table["run"].to_list())
    eq = pl.read_parquet(paths.results / chosen / "equity.parquet")
    st.plotly_chart(equity(eq), use_container_width=True)
    st.dataframe(pl.read_parquet(paths.results / chosen / "trades.parquet"))
