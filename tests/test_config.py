from pathlib import Path

import pytest
from pydantic import ValidationError

from rinng.config import Settings, load_settings

REPO = Path(__file__).resolve().parents[1]


def test_default_config_loads():
    settings = load_settings(REPO / "configs" / "instruments.yaml")
    btc = settings.instrument("BTC-USDT-PERP")
    assert btc.venue_symbol("binance") == "BTCUSDT"
    assert btc.venue_symbol("okx") == "BTC-USDT-SWAP"
    assert settings.base_timeframe == "1m"


def _raw(**overrides):
    base = {
        "data_dir": "data",
        "base_timeframe": "1m",
        "timeframes": ["1h"],
        "instruments": [{"id": "X", "kind": "perp", "binance": "XUSDT"}],
    }
    return base | overrides


def test_duplicate_ids_rejected():
    inst = {"id": "X", "kind": "perp"}
    with pytest.raises(ValidationError):
        Settings.model_validate(_raw(instruments=[inst, inst]))


def test_unknown_key_rejected():
    with pytest.raises(ValidationError):
        Settings.model_validate(_raw(typo_key=1))


def test_missing_venue_symbol():
    settings = Settings.model_validate(_raw())
    with pytest.raises(KeyError):
        settings.instrument("X").venue_symbol("okx")


def test_unknown_instrument():
    with pytest.raises(KeyError):
        Settings.model_validate(_raw()).instrument("NOPE")
