"""Dashboard theo dõi giá crypto.  Chạy:  streamlit run app.py"""
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from tracker import config
from tracker.indicators import add_all, annual_volatility, max_drawdown
from tracker.sources import get_source
from tracker.storage import Store

NAVY, GREEN, RED, GREY = "#1F3A5F", "#16A34A", "#DC2626", "#94A3B8"

st.set_page_config(page_title="Crypto Tracker", page_icon="📈", layout="wide")


@st.cache_resource
def store():
    return Store(config.DB_PATH)


@st.cache_data(ttl=55, show_spinner=False)
def load_tickers(source_name):
    src = get_source(source_name)
    df = src.tickers(list(config.COINS))
    store().save_ticks(df, src.name)   # dashboard cũng ghi lại lịch sử
    return df


@st.cache_data(ttl=300, show_spinner=False)
def load_ohlcv(source_name, symbol, timeframe, limit):
    return add_all(get_source(source_name).ohlcv(symbol, timeframe, limit))


def fmt_price(x):
    if x >= 1000:
        return f"${x:,.0f}"
    return f"${x:,.2f}" if x >= 1 else f"${x:,.4f}"


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Cài đặt")
    sources = ["coingecko", "binance", "demo"]
    source_name = st.selectbox("Nguồn dữ liệu", sources, index=sources.index(config.DEFAULT_SOURCE),
                               help="demo = dữ liệu giả lập để chạy thử khi không có mạng")
    symbol = st.selectbox("Coin", list(config.COINS))
    timeframe = st.radio("Khung nến", ["1h", "4h", "1d"], index=2, horizontal=True)
    limit = st.slider("Số nến", 60, 365, 180, step=15)
    show_bb = st.checkbox("Bollinger Bands", True)
    show_sma = st.checkbox("SMA 20 / 50", True)
    refresh = st.select_slider("Tự làm mới (giây)", [0, 30, 60, 120, 300], value=60,
                               help="0 = tắt. CoinGecko miễn phí giới hạn khoảng 30 lượt gọi/phút")

st.title("Theo dõi giá crypto")


@st.fragment(run_every=refresh or None)
def live():
    try:
        tick = load_tickers(source_name)
        bars = load_ohlcv(source_name, symbol, timeframe, limit)
    except Exception as e:
        st.error(f"Không lấy được dữ liệu từ {source_name}: {e}")
        st.info("Thử nguồn khác ở thanh bên (Binance có thể bị chặn ở một số quốc gia), hoặc chọn 'demo'.")
        return
    st.caption(f"Nguồn: {source_name} · cập nhật {pd.Timestamp.now():%H:%M:%S}"
               + (" · DỮ LIỆU GIẢ LẬP" if source_name == "demo" else ""))

    # Bảng giá các coin
    rows = list(tick.sort_values("volume_24h", ascending=False).itertuples())
    for start in range(0, len(rows), 4):          # 4 coin mỗi hàng cho dễ đọc
        for col, r in zip(st.columns(4), rows[start:start + 4]):
            col.metric(r.symbol, fmt_price(r.price), f"{r.change_24h:+.2f}%", border=True)

    # Biểu đồ nến + chỉ báo
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.6, 0.2, 0.2], vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(x=bars.ts, open=bars.open, high=bars.high, low=bars.low, close=bars.close,
                                 name=symbol, increasing_line_color=GREEN, decreasing_line_color=RED), 1, 1)
    if show_sma:
        fig.add_trace(go.Scatter(x=bars.ts, y=bars.sma20, name="SMA20", line=dict(color=NAVY, width=1.3)), 1, 1)
        fig.add_trace(go.Scatter(x=bars.ts, y=bars.sma50, name="SMA50", line=dict(color="#F59E0B", width=1.3)), 1, 1)
    if show_bb:
        fig.add_trace(go.Scatter(x=bars.ts, y=bars.bb_up, name="BB trên", line=dict(color=GREY, width=1, dash="dot")), 1, 1)
        fig.add_trace(go.Scatter(x=bars.ts, y=bars.bb_low, name="BB dưới", line=dict(color=GREY, width=1, dash="dot"),
                                 fill="tonexty", fillcolor="rgba(148,163,184,0.08)"), 1, 1)
    fig.add_trace(go.Scatter(x=bars.ts, y=bars.rsi14, name="RSI 14", line=dict(color=NAVY, width=1.3)), 2, 1)
    fig.add_hline(y=70, line=dict(color=RED, width=1, dash="dash"), row=2, col=1)
    fig.add_hline(y=30, line=dict(color=GREEN, width=1, dash="dash"), row=2, col=1)
    colors = [GREEN if h >= 0 else RED for h in bars["hist"].fillna(0)]
    fig.add_trace(go.Bar(x=bars.ts, y=bars["hist"], name="MACD hist", marker_color=colors), 3, 1)
    fig.add_trace(go.Scatter(x=bars.ts, y=bars.macd, name="MACD", line=dict(color=NAVY, width=1.2)), 3, 1)
    fig.add_trace(go.Scatter(x=bars.ts, y=bars.signal, name="Signal", line=dict(color="#F59E0B", width=1.2)), 3, 1)
    fig.update_layout(height=680, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=1.04), template="plotly_white")
    fig.update_yaxes(title_text="Giá (USD)", row=1, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)
    fig.update_yaxes(title_text="MACD", row=3, col=1)

    left, right = st.columns([3, 1])
    left.plotly_chart(fig, use_container_width=True)

    last = bars.iloc[-1]
    ppy = {"1h": 24 * 365, "4h": 6 * 365, "1d": 365}[timeframe]
    rsi_now = last.rsi14
    rsi_text = "quá mua" if rsi_now >= 70 else "quá bán" if rsi_now <= 30 else "trung tính"
    trend = "trên" if last.close > last.sma50 else "dưới"
    with right:
        st.subheader(f"{symbol} · {timeframe}")
        st.metric("Giá đóng cửa nến cuối", fmt_price(last.close))
        st.metric(f"Lợi nhuận {len(bars)} nến", f"{(last.close / bars.close.iloc[0] - 1) * 100:+.1f}%")
        st.metric("Biến động năm hoá", f"{annual_volatility(bars.close, ppy) * 100:.0f}%")
        st.metric("Sụt giảm tối đa", f"{max_drawdown(bars.close) * 100:.1f}%")
        st.metric("RSI 14", f"{rsi_now:.0f}", rsi_text, delta_color="off")
        st.write(f"Giá đang **{trend}** SMA50.")


live()

tab1, tab2 = st.tabs(["Lịch sử đã thu thập", "Cảnh báo"])
with tab1:
    hist = store().ticks(symbol)
    if hist.empty:
        st.write("Chưa có dữ liệu. Chạy `python collector.py` để thu thập liên tục.")
    else:
        st.line_chart(hist.set_index("ts")["price"], height=250)
        st.caption(f"{len(hist):,} lần ghi giá {symbol} trong {config.DB_PATH}")
with tab2:
    with open("rules.json") as f:
        st.write("Luật đang dùng (sửa trong `rules.json`):")
        st.dataframe(pd.DataFrame(json.load(f)), hide_index=True)
    alerts = store().alerts()
    st.write("Cảnh báo gần đây (do `collector.py` ghi):")
    st.dataframe(alerts, hide_index=True) if not alerts.empty else st.write("Chưa có cảnh báo.")
