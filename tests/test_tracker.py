from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tracker.alerts import AlertEngine, Rule, check_rule
from tracker.indicators import add_all, max_drawdown, rsi
from tracker.sources import CCXTSource, CoinGeckoSource, DemoSource
from tracker.storage import Store


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class FakeSession:
    headers = {}

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        for key, data in self.routes.items():
            if url.endswith(key):
                return FakeResponse(data)
        raise AssertionError(url)


def test_coingecko_tickers_parsing():
    s = FakeSession({"/simple/price": {
        "bitcoin": {"usd": 76000.5, "usd_24h_vol": 3.1e10, "usd_24h_change": -1.25, "last_updated_at": 1791900000},
        "ethereum": {"usd": 2900.0, "usd_24h_vol": 1.5e10, "usd_24h_change": 2.5, "last_updated_at": 1791900000}}})
    df = CoinGeckoSource(session=s).tickers(["BTC", "ETH"])
    assert list(df.symbol) == ["BTC", "ETH"]
    assert df.loc[0, "price"] == 76000.5 and df.loc[1, "change_24h"] == 2.5
    assert s.calls[0][1]["ids"] == "bitcoin,ethereum"


def test_coingecko_ohlcv_resamples_to_daily_bars():
    start = pd.Timestamp("2026-01-01", tz="UTC")
    ts = [int((start + pd.Timedelta(hours=h)).timestamp() * 1000) for h in range(72)]
    prices = [[t, 100 + i] for i, t in enumerate(ts)]
    vols = [[t, 1e6] for t in ts]
    s = FakeSession({"/coins/bitcoin/market_chart": {"prices": prices, "total_volumes": vols}})
    bars = CoinGeckoSource(session=s).ohlcv("BTC", "1d", 3)
    assert len(bars) == 3
    assert bars.loc[0, "open"] == 100 and bars.loc[0, "close"] == 123 and bars.loc[0, "high"] == 123


def test_ccxt_source_with_fake_exchange():
    class FakeExchange:
        def fetch_tickers(self, pairs):
            return {"BTC/USDT": {"last": 75000, "percentage": 1.5, "quoteVolume": 2e9, "timestamp": 1791900000000}}

        def fetch_ohlcv(self, pair, timeframe, limit):
            return [[1791900000000 + i * 3600000, 1, 2, 0.5, 1.5, 10] for i in range(limit)]

    src = CCXTSource(exchange=FakeExchange())
    assert src.tickers(["BTC"]).loc[0, "price"] == 75000
    assert len(src.ohlcv("BTC", "1h", 5)) == 5


def test_rsi_matches_known_cases():
    up = pd.Series(np.arange(1, 40, dtype=float))
    assert rsi(up).iloc[-1] == 100
    down = pd.Series(np.arange(40, 1, -1, dtype=float))
    assert rsi(down).iloc[-1] == pytest.approx(0)
    zigzag = pd.Series([10, 11] * 20, dtype=float)
    assert 40 < rsi(zigzag).iloc[-1] < 60


def test_indicators_on_demo_data():
    bars = add_all(DemoSource(seed=1).ohlcv("BTC", "1d", 120))
    assert {"sma20", "rsi14", "macd", "bb_up"} <= set(bars.columns)
    assert (bars.high >= bars[["open", "close"]].max(axis=1)).all()
    assert bars.rsi14.dropna().between(0, 100).all()
    assert max_drawdown(pd.Series([100, 120, 60, 90])) == pytest.approx(-0.5)


def test_store_roundtrip_and_dedup(tmp_path):
    st = Store(tmp_path / "t.db")
    df = DemoSource(seed=2).tickers(["BTC", "ETH"])
    assert st.save_ticks(df, "demo") == 2
    assert st.save_ticks(df, "demo") == 0     # cùng thời điểm -> không ghi trùng
    assert len(st.ticks("BTC")) == 1


def test_alert_rules_and_cooldown(tmp_path):
    t0 = pd.Timestamp("2026-10-13 10:00", tz="UTC")
    hist = pd.DataFrame({"ts": [t0, t0 + pd.Timedelta(minutes=30), t0 + pd.Timedelta(minutes=61)],
                         "price": [100.0, 101.0, 103.5]})
    assert "+3.50%" in check_rule(Rule("BTC", "move_pct", 3, window_min=60), hist)
    assert check_rule(Rule("BTC", "above", 103), hist)
    assert check_rule(Rule("BTC", "below", 90), hist) is None
    assert "quá bán" in check_rule(Rule("BTC", "rsi_low", 30), hist, rsi_value=25)

    got = []
    eng = AlertEngine([Rule("BTC", "above", 103, cooldown_min=60)], Store(tmp_path / "a.db"), [got.append])
    eng.run({"BTC": hist}, now=t0)
    eng.run({"BTC": hist}, now=t0 + pd.Timedelta(minutes=10))   # trong thời gian chờ
    eng.run({"BTC": hist}, now=t0 + pd.Timedelta(minutes=70))
    assert len(got) == 2


def test_dashboard_runs_in_demo_mode(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.chdir(Path(__file__).parent.parent)  # app.py đọc rules.json theo đường dẫn tương đối
    monkeypatch.setattr("tracker.config.DB_PATH", str(tmp_path / "ui.db"))
    at = AppTest.from_file("../app.py", default_timeout=60)
    at.run()                                   # lần đầu: CoinGecko (có thể lỗi mạng, app phải báo lỗi chứ không crash)
    assert not at.exception
    at.sidebar.selectbox[0].set_value("demo")
    at.run()
    assert not at.exception
    assert len(at.metric) >= 8
