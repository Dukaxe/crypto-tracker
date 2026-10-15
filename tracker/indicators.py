"""Chỉ báo kỹ thuật viết bằng pandas (không cần cài TA-Lib)."""
import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    """RSI theo cách làm mượt của Wilder (giống TradingView)."""
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0).where(gain.notna())


def macd(s: pd.Series, fast=12, slow=26, signal=9) -> pd.DataFrame:
    line = ema(s, fast) - ema(s, slow)
    sig = ema(line, signal)
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def bollinger(s: pd.Series, n=20, k=2.0) -> pd.DataFrame:
    mid = sma(s, n)
    sd = s.rolling(n).std()
    return pd.DataFrame({"bb_mid": mid, "bb_up": mid + k * sd, "bb_low": mid - k * sd})


def annual_volatility(close: pd.Series, periods_per_year=365) -> float:
    """Crypto giao dịch cả tuần nên 1 năm = 365 phiên ngày."""
    return float(np.log(close).diff().std() * np.sqrt(periods_per_year))


def max_drawdown(close: pd.Series) -> float:
    return float((close / close.cummax() - 1).min())


def add_all(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["sma20"] = sma(out["close"], 20)
    out["sma50"] = sma(out["close"], 50)
    out["rsi14"] = rsi(out["close"])
    out = out.join(macd(out["close"])).join(bollinger(out["close"]))
    return out
