"""Cấu hình chung. Sửa danh sách coin theo dõi ở đây."""
import os

# symbol hiển thị -> (id trên CoinGecko, cặp giao dịch trên sàn qua ccxt)
COINS = {
    "BTC": ("bitcoin", "BTC/USDT"),
    "ETH": ("ethereum", "ETH/USDT"),
    "SOL": ("solana", "SOL/USDT"),
    "BNB": ("binancecoin", "BNB/USDT"),
    "XRP": ("ripple", "XRP/USDT"),
    "DOGE": ("dogecoin", "DOGE/USDT"),
    "ADA": ("cardano", "ADA/USDT"),
    "LINK": ("chainlink", "LINK/USDT"),
}

DB_PATH = os.getenv("TRACKER_DB", "crypto.db")
EXCHANGE = os.getenv("TRACKER_EXCHANGE", "binance")   # bất kỳ sàn nào ccxt hỗ trợ: binance, okx, kraken...
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")  # không bắt buộc (gói Demo miễn phí)
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))    # CoinGecko miễn phí giới hạn ~30 lượt/phút

# Cảnh báo Telegram (không bắt buộc)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DEFAULT_SOURCE = os.getenv("TRACKER_SOURCE", "coingecko")  # coingecko | binance | demo
