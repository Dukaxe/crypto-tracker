"""Thu thập giá liên tục, lưu SQLite và kiểm tra cảnh báo.

python collector.py --source coingecko            # mỗi 60 giây
python collector.py --source binance --every 15
python collector.py --source demo --every 2 --iterations 5   # chạy thử không cần mạng
"""
import argparse
import json
import time

import pandas as pd

from tracker import config
from tracker.alerts import AlertEngine, Rule, telegram_notifier
from tracker.indicators import rsi
from tracker.sources import get_source
from tracker.storage import Store


def load_rules(path="rules.json"):
    with open(path) as f:
        return [Rule(**r) for r in json.load(f)]


def collect_once(source, store, engine, symbols, rsi_cache):
    ticks = source.tickers(symbols)
    added = store.save_ticks(ticks, source.name)
    since = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=24)
    histories = {s: store.ticks(s, since=since) for s in symbols}
    fired = engine.run(histories, rsi_values=rsi_cache)
    line = "  ".join(f"{r.symbol} {r.price:,.2f} ({r.change_24h:+.1f}%)" if r.price >= 1
                     else f"{r.symbol} {r.price:.4f} ({r.change_24h:+.1f}%)" for r in ticks.itertuples())
    print(f"[{pd.Timestamp.now():%H:%M:%S}] +{added} dòng | {line}")
    return fired


def refresh_rsi(source, symbols):
    """RSI(14) trên nến ngày; chỉ cập nhật mỗi giờ để không vượt giới hạn API."""
    out = {}
    for s in symbols:
        try:
            out[s] = float(rsi(source.ohlcv(s, "1d", 60)["close"]).iloc[-1])
        except Exception as e:
            print(f"Không lấy được nến {s}: {e}")
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="coingecko", choices=["coingecko", "binance", "demo"])
    p.add_argument("--every", type=int, default=config.POLL_SECONDS, help="giây giữa 2 lần lấy giá")
    p.add_argument("--iterations", type=int, default=0, help="0 = chạy mãi")
    p.add_argument("--db", default=config.DB_PATH)
    a = p.parse_args()

    source, store = get_source(a.source), Store(a.db)
    symbols = list(config.COINS)
    engine = AlertEngine(load_rules(), store, notifiers=[lambda m: print("  CẢNH BÁO:", m), telegram_notifier])
    rsi_cache, rsi_time, i = {}, 0.0, 0
    print(f"Thu thập {len(symbols)} coin từ {a.source}, mỗi {a.every}s, lưu vào {a.db}. Ctrl+C để dừng.")
    while True:
        try:
            if time.time() - rsi_time > 3600:
                rsi_cache, rsi_time = refresh_rsi(source, symbols), time.time()
            collect_once(source, store, engine, symbols, rsi_cache)
        except KeyboardInterrupt:
            break
        except Exception as e:  # mất mạng, bị giới hạn lượt gọi... -> thử lại lần sau
            print("Lỗi:", e)
        i += 1
        if a.iterations and i >= a.iterations:
            break
        try:
            time.sleep(a.every)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
