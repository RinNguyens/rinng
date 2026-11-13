"""Giao diện chung mà mọi sàn phải cài (docs/08-kien-truc.md mục 6).

Mỗi phương thức trả về từng trang dữ liệu dưới dạng list các dict đã chuẩn hóa
(thời gian UTC tính bằng mili giây, số ở dạng float). Phần còn lại của hệ thống
không được biết mình đang làm việc với sàn nào.
"""

from collections.abc import Iterator
from datetime import datetime
from typing import Any, Protocol

Row = dict[str, Any]


class Exchange(Protocol):
    name: str

    def klines(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> Iterator[list[Row]]: ...

    def funding(self, symbol: str, start: datetime, end: datetime) -> Iterator[list[Row]]: ...

    def open_interest(
        self, symbol: str, period: str, start: datetime, end: datetime
    ) -> Iterator[list[Row]]: ...
