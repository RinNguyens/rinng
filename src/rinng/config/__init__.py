"""Đọc và kiểm tra cấu hình dự án."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

DEFAULT_CONFIG = Path("configs/instruments.yaml")


class Instrument(BaseModel):
    """Một instrument với tên chuẩn của dự án và tên gốc trên từng sàn."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["perp", "spot"]
    binance: str | None = None
    okx: str | None = None
    # Hiển thị: tài sản cơ sở (icon), tài sản định giá, tên đầy đủ. Bỏ trống thì suy từ id.
    base: str | None = None
    quote: str | None = None
    name: str | None = None

    @model_validator(mode="after")
    def _fill_display(self) -> "Instrument":
        parts = self.id.split("-")
        self.base = self.base or parts[0]
        self.quote = self.quote or (parts[1] if len(parts) > 1 else None)
        self.name = self.name or self.base
        return self

    def venue_symbol(self, exchange: str) -> str:
        symbol = getattr(self, exchange, None)
        if symbol is None:
            raise KeyError(f"{self.id} không có tên trên sàn {exchange!r}")
        return symbol


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_dir: Path
    base_timeframe: str
    timeframes: list[str]
    instruments: list[Instrument]

    @model_validator(mode="after")
    def _unique_ids(self) -> "Settings":
        ids = [i.id for i in self.instruments]
        if len(ids) != len(set(ids)):
            raise ValueError("id của instrument bị trùng")
        return self

    def instrument(self, instrument_id: str) -> Instrument:
        for inst in self.instruments:
            if inst.id == instrument_id:
                return inst
        raise KeyError(f"không có instrument {instrument_id!r} trong cấu hình")


def load_settings(path: Path = DEFAULT_CONFIG) -> Settings:
    with open(path, encoding="utf-8") as f:
        return Settings.model_validate(yaml.safe_load(f))
