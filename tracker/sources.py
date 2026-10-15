"""Nguồn dữ liệu giá. Mọi nguồn trả về cùng một dạng để phần còn lại không cần biết nguồn nào.

- tickers(symbols) -> DataFrame: symbol, price, change_24h (%), volume_24h (USD), ts (UTC)
- ohlcv(symbol, timeframe, limit) -> DataFrame: ts, open, high, low, close, volume
"""
import time

import numpy as np
import pandas as pd
import requests

from . import config

TICKER_COLS = ["symbol", "price", "change_24h", "volume_24h", "ts"]
OHLCV_COLS = ["ts", "open", "high", "low", "close", "volume"]


class CoinGeckoSource:
    """API công khai của CoinGecko, không cần tài khoản."""
    name = "coingecko"
    BASE = "https://api.coingecko.com/api/v3"

    def __init__(self, session=None):
        self.session = session or requests.Session()
        if config.COINGECKO_API_KEY:
            self.session.headers["x-cg-demo-api-key"] = config.COINGECKO_API_KEY

    def _get(self, path, params):
        r = self.session.get(f"{self.BASE}{path}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def tickers(self, symbols):
        ids = {config.COINS[s][0]: s for s in symbols}
        data = self._get("/simple/price", {
            "ids": ",".join(ids), "vs_currencies": "usd", "include_24hr_change": "true",
            "include_24hr_vol": "true", "include_last_updated_at": "true",
        })
        rows = []
        for cg_id, d in data.items():
            rows.append({"symbol": ids[cg_id], "price": d["usd"], "change_24h": d.get("usd_24h_change"),
                         "volume_24h": d.get("usd_24h_vol"),
                         "ts": pd.to_datetime(d.get("last_updated_at", time.time()), unit="s", utc=True)})
        return pd.DataFrame(rows, columns=TICKER_COLS)

    def ohlcv(self, symbol, timeframe="1d", limit=180):
        # CoinGecko /ohlc tự chọn độ phân giải theo số ngày và không có volume,
        # nên dùng market_chart (giá + volume) rồi gom thành nến.
        cg_id = config.COINS[symbol][0]
        days = {"1h": max(2, limit // 24 + 1), "4h": max(3, limit // 6 + 1), "1d": limit}[timeframe]
        data = self._get(f"/coins/{cg_id}/market_chart", {"vs_currency": "usd", "days": min(days, 365)})
        px = pd.DataFrame(data["prices"], columns=["ts", "price"])
        vol = pd.DataFrame(data["total_volumes"], columns=["ts", "volume"])
        px["ts"] = pd.to_datetime(px["ts"], unit="ms", utc=True)
        vol["ts"] = pd.to_datetime(vol["ts"], unit="ms", utc=True)
        rule = {"1h": "1h", "4h": "4h", "1d": "1D"}[timeframe]
        bars = px.set_index("ts")["price"].resample(rule).ohlc()
        # total_volumes là volume 24h trượt, lấy giá trị cuối mỗi nến làm gần đúng
        bars["volume"] = vol.set_index("ts")["volume"].resample(rule).last()
        bars = bars.dropna(subset=["close"]).reset_index()
        return bars[OHLCV_COLS].tail(limit).reset_index(drop=True)


class CCXTSource:
    """Dữ liệu trực tiếp từ sàn (mặc định Binance) qua thư viện ccxt."""
    name = "ccxt"

    def __init__(self, exchange_id=None, exchange=None):
        if exchange is None:
            import ccxt
            exchange = getattr(ccxt, exchange_id or config.EXCHANGE)({"enableRateLimit": True})
        self.ex = exchange

    def tickers(self, symbols):
        pairs = {config.COINS[s][1]: s for s in symbols}
        data = self.ex.fetch_tickers(list(pairs))
        rows = []
        for pair, t in data.items():
            if pair not in pairs:
                continue
            rows.append({"symbol": pairs[pair], "price": t["last"], "change_24h": t.get("percentage"),
                         "volume_24h": t.get("quoteVolume"),
                         "ts": pd.to_datetime(t.get("timestamp") or time.time() * 1000, unit="ms", utc=True)})
        return pd.DataFrame(rows, columns=TICKER_COLS)

    def ohlcv(self, symbol, timeframe="1d", limit=180):
        raw = self.ex.fetch_ohlcv(config.COINS[symbol][1], timeframe=timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=OHLCV_COLS)
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        return df


class DemoSource:
    """Dữ liệu giả lập (bước ngẫu nhiên) để chạy dashboard khi không có mạng hoặc bị chặn API."""
    name = "demo"
    START = {"BTC": 76000, "ETH": 2900, "SOL": 170, "BNB": 640, "XRP": 2.3, "DOGE": 0.22, "ADA": 0.75, "LINK": 16}
    VOL = {"BTC": 0.03, "ETH": 0.04, "SOL": 0.055, "BNB": 0.03, "XRP": 0.05, "DOGE": 0.06, "ADA": 0.05, "LINK": 0.05}

    def __init__(self, seed=None):
        self.rng = np.random.default_rng(seed)

    def ohlcv(self, symbol, timeframe="1d", limit=180):
        step = {"1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4), "1d": pd.Timedelta(days=1)}[timeframe]
        scale = {"1h": 1 / np.sqrt(24), "4h": 1 / np.sqrt(6), "1d": 1.0}[timeframe]
        sigma = self.VOL.get(symbol, 0.05) * scale
        rets = self.rng.normal(0, sigma, limit)
        close = self.START.get(symbol, 10) * np.exp(np.cumsum(rets) - rets.sum())  # kết thúc gần giá START
        open_ = np.r_[close[0], close[:-1]]
        spread = np.abs(self.rng.normal(0, sigma / 2, limit))
        high = np.maximum(open_, close) * (1 + spread)
        low = np.minimum(open_, close) * (1 - spread)
        volume = self.rng.lognormal(18, 0.4, limit)
        end = pd.Timestamp.now(tz="UTC").floor(step)
        ts = pd.date_range(end=end, periods=limit, freq=step)
        return pd.DataFrame({"ts": ts, "open": open_, "high": high, "low": low, "close": close, "volume": volume})

    def tickers(self, symbols):
        rows = []
        for s in symbols:
            change = self.rng.normal(0, self.VOL.get(s, 0.05) * 100)
            price = self.START.get(s, 10) * (1 + self.rng.normal(0, 0.002))
            rows.append({"symbol": s, "price": price, "change_24h": change,
                         "volume_24h": self.rng.lognormal(20, 0.5), "ts": pd.Timestamp.now(tz="UTC")})
        return pd.DataFrame(rows, columns=TICKER_COLS)


def get_source(name):
    if name == "coingecko":
        return CoinGeckoSource()
    if name in ("binance", "ccxt"):
        return CCXTSource()
    if name == "demo":
        return DemoSource()
    raise ValueError(f"Nguồn không hỗ trợ: {name}")
