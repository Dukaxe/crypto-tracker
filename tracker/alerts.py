"""Luật cảnh báo giá. Mỗi luật trả về thông điệp khi điều kiện xảy ra, kèm thời gian chờ để không báo lặp."""
from dataclasses import dataclass

import pandas as pd
import requests

from . import config


@dataclass
class Rule:
    symbol: str
    kind: str          # "above", "below", "move_pct", "rsi_high", "rsi_low"
    value: float
    window_min: int = 60     # cho move_pct: so với giá cách đây bao nhiêu phút
    cooldown_min: int = 60   # không báo lại trong khoảng này

    @property
    def name(self):
        return f"{self.symbol}:{self.kind}:{self.value}"


def check_rule(rule: Rule, history: pd.DataFrame, rsi_value: float | None = None) -> str | None:
    """history: các tick của 1 coin (cột ts, price), sắp theo thời gian."""
    if history.empty:
        return None
    now = history.iloc[-1]
    price = now["price"]
    if rule.kind == "above" and price >= rule.value:
        return f"{rule.symbol} vượt {rule.value:,.4g} USD (hiện {price:,.4g})"
    if rule.kind == "below" and price <= rule.value:
        return f"{rule.symbol} xuống dưới {rule.value:,.4g} USD (hiện {price:,.4g})"
    if rule.kind == "move_pct":
        past = history[history["ts"] <= now["ts"] - pd.Timedelta(minutes=rule.window_min)]
        if not past.empty:
            change = (price / past.iloc[-1]["price"] - 1) * 100
            if abs(change) >= rule.value:
                return f"{rule.symbol} {change:+.2f}% trong {rule.window_min} phút (giá {price:,.4g})"
    if rule.kind == "rsi_high" and rsi_value is not None and rsi_value >= rule.value:
        return f"{rule.symbol} RSI = {rsi_value:.0f}, vùng quá mua"
    if rule.kind == "rsi_low" and rsi_value is not None and rsi_value <= rule.value:
        return f"{rule.symbol} RSI = {rsi_value:.0f}, vùng quá bán"
    return None


class AlertEngine:
    def __init__(self, rules, store=None, notifiers=None):
        self.rules = rules
        self.store = store
        self.notifiers = notifiers or [print]
        self.last_fired: dict[str, pd.Timestamp] = {}

    def run(self, histories: dict, now=None, rsi_values=None) -> list[str]:
        now = now or pd.Timestamp.now(tz="UTC")
        rsi_values = rsi_values or {}
        fired = []
        for rule in self.rules:
            last = self.last_fired.get(rule.name)
            if last is not None and now - last < pd.Timedelta(minutes=rule.cooldown_min):
                continue
            msg = check_rule(rule, histories.get(rule.symbol, pd.DataFrame()), rsi_values.get(rule.symbol))
            if msg:
                self.last_fired[rule.name] = now
                fired.append(msg)
                if self.store:
                    self.store.save_alert(now, rule.symbol, rule.name, msg)
                for notify in self.notifiers:
                    notify(msg)
        return fired


def telegram_notifier(message: str) -> None:
    """Gửi tin nhắn qua bot Telegram nếu đã đặt TELEGRAM_TOKEN và TELEGRAM_CHAT_ID."""
    if not (config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": config.TELEGRAM_CHAT_ID, "text": message}, timeout=10)
    except requests.RequestException as e:
        print("Không gửi được Telegram:", e)
