"""Load and validate the project config.

Which config file is used (first match wins):
1. the path passed in (`--config` on the CLI);
2. the `RINNG_CONFIG` environment variable;
3. `configs/instruments.yaml` under the current directory (working inside the repo);
4. the copy bundled with the package (installed with pip/uv/uvx, run from any folder).

Data directory: `RINNG_DATA` if set, else `data_dir` from the config. A relative `data_dir` is
relative to the current directory, except for the bundled config, where it lives under `~/.rinng`
so the result does not depend on where the program was started.
"""

import os
from importlib import resources
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

DEFAULT_CONFIG = Path("configs/instruments.yaml")  # project-local config, relative to cwd
CONFIG_ENV = "RINNG_CONFIG"
DATA_ENV = "RINNG_DATA"
HOME = Path("~/.rinng")
# In the wheel the repo's configs/instruments.yaml is copied here (pyproject force-include);
# in an editable install it is found next to the source tree instead.
_PACKAGED = "instruments.yaml"
_SOURCE_TREE = Path(__file__).resolve().parents[3] / "configs" / "instruments.yaml"


class Instrument(BaseModel):
    """An instrument with the project canonical name and the native name on each exchange."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["perp", "spot"]
    binance: str | None = None
    okx: str | None = None
    # Display: base asset (icon), quote asset, full name. Left empty, derived from id.
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
            raise KeyError(f"{self.id} has no name on exchange {exchange!r}")
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
            raise ValueError("duplicate instrument id")
        return self

    def instrument(self, instrument_id: str) -> Instrument:
        for inst in self.instruments:
            if inst.id == instrument_id:
                return inst
        raise KeyError(f"instrument {instrument_id!r} not in config")


def bundled_config() -> Path:
    """The config shipped with the package (or the repo copy in an editable install)."""
    packaged = Path(str(resources.files(__name__).joinpath(_PACKAGED)))
    return packaged if packaged.is_file() else _SOURCE_TREE


def find_config(path: Path | str | None = None) -> tuple[Path, bool]:
    """(config file, whether it is the bundled default). See the module docstring."""
    if path is not None:
        return Path(path).expanduser(), False
    if env := os.environ.get(CONFIG_ENV):
        return Path(env).expanduser(), False
    if DEFAULT_CONFIG.is_file():
        return DEFAULT_CONFIG, False
    return bundled_config(), True


def load_settings(path: Path | str | None = None) -> Settings:
    file, bundled = find_config(path)
    if not file.is_file():
        raise FileNotFoundError(f"config file not found: {file}")
    with open(file, encoding="utf-8") as f:
        settings = Settings.model_validate(yaml.safe_load(f))
    if env := os.environ.get(DATA_ENV):
        data_dir = Path(env)
    elif bundled and not settings.data_dir.expanduser().is_absolute():
        data_dir = HOME / settings.data_dir
    else:
        data_dir = settings.data_dir
    return settings.model_copy(update={"data_dir": data_dir.expanduser()})
