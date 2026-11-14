"""History download: Binance dumps first, REST fills what dumps lack; OKX via REST only.

Everything is written to raw/; run `pipeline.curate` afterwards to move it into curated/.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from rinng.config import Instrument, Settings
from rinng.exchanges.binance import Binance
from rinng.exchanges.okx import Okx
from rinng.ingest import dumps
from rinng.ingest.collector.messages import Record
from rinng.ingest.collector.sink import Sink
from rinng.store.paths import DataPaths

log = logging.getLogger(__name__)

BINANCE_DUMPS = ("klines_1m", "funding", "metrics")


@dataclass
class BackfillReport:
    downloaded: int = 0
    missing: list[str] = field(default_factory=list)  # files the exchange lacks (404)
    rest_rows: dict[str, int] = field(default_factory=dict)


def _at(d: date) -> datetime:
    return datetime.combine(d, time(), tzinfo=UTC)


def _rest(sink: Sink, report: BackfillReport, key: str, records) -> None:
    count = 0
    for batch in records:
        sink.add(batch)
        count += len(batch)
    sink.flush()
    report.rest_rows[key] = report.rest_rows.get(key, 0) + count


def backfill_binance(
    paths: DataPaths,
    inst: Instrument,
    start: date,
    end: datetime,
    *,
    datasets: tuple[str, ...] = BINANCE_DUMPS,
    downloader: dumps.Downloader | None = None,
    api: Binance | None = None,
) -> BackfillReport:
    report = BackfillReport()
    downloader = downloader or dumps.Downloader()
    api = api or Binance()
    symbol = inst.binance
    for name in datasets:
        files = dumps.plan(name, symbol, start, end.date() + timedelta(days=1))
        for f in files:
            if downloader.fetch(f, paths) is None:
                report.missing.append(f.filename)
            else:
                report.downloaded += 1
        covered = _at(dumps.covered_until(files, start))
        if covered >= end:
            continue
        sink = Sink(paths, "binance", max_rows=50_000, max_age=1e9)
        if name == "klines_1m":
            pages = api.klines(symbol, "1m", covered, end)
            records = ([Record("ohlcv", inst.id, r, "1m") for r in page] for page in pages)
            _rest(sink, report, "ohlcv_1m", records)
        elif name == "funding":
            pages = api.funding(symbol, covered, end)
            _rest(
                sink, report, "funding", ([Record("funding", inst.id, r) for r in p] for p in pages)
            )
        # metrics/aggTrades/bookDepth: the part without dumps is captured by the collector.
    return report


def backfill_okx(
    paths: DataPaths, inst: Instrument, start: date, end: datetime, *, api: Okx | None = None
) -> BackfillReport:
    report = BackfillReport()
    api = api or Okx()
    symbol = inst.okx
    sink = Sink(paths, "okx", max_rows=50_000, max_age=1e9)
    pages = api.klines(symbol, "1m", _at(start), end)
    records = ([Record("ohlcv", inst.id, r, "1m") for r in page] for page in pages)
    _rest(sink, report, "ohlcv_1m", records)
    # OKX keeps only 3 months of funding via REST.
    f_start = max(_at(start), end - timedelta(days=90))
    pages = api.funding(symbol, f_start, end)
    _rest(sink, report, "funding", ([Record("funding", inst.id, r) for r in p] for p in pages))
    return report


def backfill(
    settings: Settings,
    start: date,
    end: datetime | None = None,
    *,
    exchanges: tuple[str, ...] = ("binance",),
    datasets: tuple[str, ...] = BINANCE_DUMPS,
) -> dict[str, BackfillReport]:
    """Only closed candles: `end` defaults to the start of the current minute."""
    paths = DataPaths(settings.data_dir)
    end = end or datetime.now(UTC).replace(second=0, microsecond=0)
    out = {}
    for inst in settings.instruments:
        if inst.kind != "perp":
            continue
        if "binance" in exchanges and inst.binance:
            log.info("binance %s from %s", inst.id, start)
            out[f"binance:{inst.id}"] = backfill_binance(paths, inst, start, end, datasets=datasets)
        if "okx" in exchanges and inst.okx:
            log.info("okx %s from %s", inst.id, start)
            out[f"okx:{inst.id}"] = backfill_okx(paths, inst, start, end)
    return out
