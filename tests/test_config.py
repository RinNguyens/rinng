from pathlib import Path

import pytest
from pydantic import ValidationError

from rinng.config import Settings, bundled_config, find_config, load_settings

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


# --------------------------------------------------------------- which config / data dir is used


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("RINNG_CONFIG", raising=False)
    monkeypatch.delenv("RINNG_DATA", raising=False)
    return monkeypatch


def _write_config(path: Path, data_dir: str = "data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"data_dir: {data_dir}\nbase_timeframe: 1m\ntimeframes: [1h]\ninstruments:\n"
        "  - {id: X-USDT-PERP, kind: perp, binance: XUSDT}\n"
    )
    return path


def test_explicit_path_wins_over_env(clean_env, tmp_path):
    clean_env.setenv("RINNG_CONFIG", str(_write_config(tmp_path / "env.yaml")))
    explicit = _write_config(tmp_path / "explicit.yaml", "elsewhere")
    assert find_config(explicit) == (explicit, False)
    assert load_settings(explicit).data_dir == Path("elsewhere")


def test_env_config_then_cwd_config(clean_env, tmp_path):
    clean_env.chdir(tmp_path)
    local = _write_config(tmp_path / "configs" / "instruments.yaml")
    assert find_config() == (Path("configs/instruments.yaml"), False)
    assert local.is_file()
    env = _write_config(tmp_path / "env.yaml")
    clean_env.setenv("RINNG_CONFIG", str(env))
    assert find_config() == (env, False)


def test_bundled_config_outside_repo_uses_home_data_dir(clean_env, tmp_path):
    clean_env.chdir(tmp_path)  # no configs/ here
    file, bundled = find_config()
    assert bundled and file == bundled_config() and file.is_file()
    settings = load_settings()
    assert settings.data_dir == Path("~/.rinng/data").expanduser()
    assert settings.instrument("BTC-USDT-PERP").binance == "BTCUSDT"


def test_rinng_data_overrides_data_dir(clean_env, tmp_path):
    clean_env.setenv("RINNG_DATA", str(tmp_path / "store"))
    assert load_settings(_write_config(tmp_path / "c.yaml")).data_dir == tmp_path / "store"


def test_missing_config_file_is_a_clear_error(clean_env, tmp_path):
    with pytest.raises(FileNotFoundError, match="config file not found"):
        load_settings(tmp_path / "nope.yaml")
