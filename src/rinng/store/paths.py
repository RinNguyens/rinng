"""Layout of the data/ directory (docs/08-architecture.md section 5.1).

Every process gets its paths from here so nobody names directories by hand.
"""

from datetime import date
from pathlib import Path


class DataPaths:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def curated(self) -> Path:
        return self.root / "curated"

    @property
    def meta(self) -> Path:
        return self.root / "meta"

    @property
    def results(self) -> Path:
        return self.root / "results"

    def raw_partition(self, exchange: str, dataset: str, symbol: str, day: date) -> Path:
        """Raw data directory for one day. `symbol` is the native exchange name."""
        return self.raw / exchange / dataset / symbol / f"date={day.isoformat()}"

    def curated_dataset(self, dataset: str) -> Path:
        return self.curated / dataset

    def curated_partition(
        self,
        dataset: str,
        exchange: str,
        instrument_id: str,
        year: int,
        timeframe: str | None = None,
    ) -> Path:
        """Directory for one year of data. Only bar tables have a `timeframe` level."""
        path = self.curated_dataset(dataset) / f"exchange={exchange}" / f"symbol={instrument_id}"
        if timeframe is not None:
            path = path / f"timeframe={timeframe}"
        return path / f"year={year}"

    def derived(self, zone: str, module: str, version: int, instrument_id: str, tf: str) -> Path:
        """Analysis output directory. `zone` is 'features' or 'events'."""
        if zone not in ("features", "events"):
            raise ValueError(f"invalid zone: {zone!r}")
        return (
            self.root
            / zone
            / module
            / f"v{version}"
            / f"symbol={instrument_id}"
            / f"timeframe={tf}"
        )
