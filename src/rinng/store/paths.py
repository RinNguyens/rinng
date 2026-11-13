"""Bố cục thư mục data/ (docs/08-kien-truc.md mục 5.1).

Mọi tiến trình lấy đường dẫn từ đây để không ai tự đặt tên thư mục.
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
        """Thư mục dữ liệu thô của một ngày. `symbol` là tên gốc trên sàn."""
        return self.raw / exchange / dataset / symbol / f"date={day.isoformat()}"

    def curated_partition(
        self, dataset: str, exchange: str, instrument_id: str, timeframe: str, year: int
    ) -> Path:
        return (
            self.curated
            / dataset
            / f"exchange={exchange}"
            / f"symbol={instrument_id}"
            / f"timeframe={timeframe}"
            / f"year={year}"
        )

    def derived(self, zone: str, module: str, version: int, instrument_id: str, tf: str) -> Path:
        """Thư mục đầu ra phân tích. `zone` là 'features' hoặc 'events'."""
        if zone not in ("features", "events"):
            raise ValueError(f"zone không hợp lệ: {zone!r}")
        return (
            self.root
            / zone
            / module
            / f"v{version}"
            / f"symbol={instrument_id}"
            / f"timeframe={tf}"
        )
