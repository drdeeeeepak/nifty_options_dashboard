# pages/08_Stocks_RSI_Daily.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd

from data.live_fetcher import get_top10_daily
from analytics.rsi_engine import RSIEngine
from config import TOP_10_NIFTY

st.set_page_config(page_title="P08 · Stocks Daily RSI", layout="wide")
st_autorefresh(interval=60_000, key="p08_refresh")

st.title("Page 08 — Top 10 Stocks: Daily RSI Divergence")
st.caption("Daily RSI per stock · D vs W divergence detection · Intraday breadth timing")

stock_dfs = get_top10_daily()
eng       = RSIEngine()
stock_sig = eng.stock_signals(stock_dfs)
per       = stock_sig["per_stock"]

# ── METRICS ──────────────────────────────────────────────────────────────────
above_54 = sum(1 for s in per.values() if s.get("d_rsi", 0) > 54)
below_46 = sum(1 for s in per.values() if s.get("d_rsi", 0) < 46)
exhaust  = sum(1 for s in per.values() if s.get("d_rsi", 0) > 68)
diverg   = sum(
    1 for s in per.values()
    if abs(s.get("d_rsi", 50) - s.get("w_rsi", 50)) > 8
)

c1,c2,c3,c4 = st.columns(4)
c1.metric("Stocks daily RSI >54",  f"{above_54}/10")
c2.metric("Stocks daily RSI <46",  f"{below_46}/10")
c3.metric("Exhaustion (>68)",      f"{exhaust}/10")
c4.metric("D vs W divergence (>8pt)", f"{diverg}/10")

st.divider()

# ── STOCK GRID ────────────────────────────────────────────────────────────────
st.subheader("Daily RSI by Stock")
cols = st.columns(5)
for idx, sym in enumerate(TOP_10_NIFTY):
    col = cols[idx % 5]
    if idx == 5:
        cols = st.columns(5)

    s     = per.get(sym, {})
    d_rsi = s.get("d_rsi", 50)
    w_rsi = s.get("w_rsi", 50)
    d_zone= s.get("d_zone", "—")
    d_sl  = s.get("d_slope", 0)
    align = s.get("alignment", "—")
    diff  = d_rsi - w_rsi

    color = (
        "#d97706" if d_rsi > 68 else
        "#16a34a" if d_rsi > 54 else
        "#dc2626" if d_rsi < 46 else
        "#2563eb"
    )

    with col:
        st.markdown(
            f"<div style='border-left:4px solid {color};"
            f"padding:8px 10px;background:#f8f9fb;border-radius:0 6px 6px 0;"
            f"margin-bottom:8px;'>"
            f"<b>{sym}</b><br>"
            f"<span style='font-size:20px;font-weight:700;color:{color};'>{d_rsi:.1f}</span> "
            f"<span style='font-size:10px;color:#5a6b8a;'>(W:{w_rsi:.1f})</span><br>"
            f"<span style='font-size:10px;color:#5a6b8a;'>"
            f"{d_zone[:12]}<br>D-W: {diff:+.1f} · Slope: {d_sl:+.1f}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

st.divider()

# ── DIVERGENCE TABLE ──────────────────────────────────────────────────────────
st.subheader("Daily vs Weekly RSI Divergence")
rows = []
for sym in TOP_10_NIFTY:
    s     = per.get(sym, {})
    d_rsi = s.get("d_rsi", 50)
    w_rsi = s.get("w_rsi", 50)
    diff  = d_rsi - w_rsi

    if diff > 8:
        divergence = "📈 D leading W higher → weekly upgrading soon"
    elif diff < -8:
        divergence = "📉 D falling below W → weekly downgrading risk"
    else:
        divergence = "—"

    # Banking exhaustion check
    if sym in ["HDFCBANK","ICICIBANK","KOTAKBANK","AXISBANK"] and d_rsi > 68:
        ce_signal = "⚠️ Bank exhaustion → Nifty CE entry"
    else:
        ce_signal = "—"

    rows.append({
        "Stock":      sym,
        "Daily RSI":  round(d_rsi, 1),
        "Weekly RSI": round(w_rsi, 1),
        "D − W":      f"{diff:+.1f}",
        "Divergence": divergence,
        "CE Signal":  ce_signal,
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with st.expander("Daily RSI Stock Rules"):
    st.markdown("""
**SD1 — 6+ stocks daily RSI >54:** Broad intraday bull. PE entry confirmed from breadth.

**SD2 — 2+ banking stocks daily RSI >68:** Banking exhaustion → Nifty CE entry signal.

**SD3 — D leads W higher by >8pts for 2+ sessions:** Weekly regime about to upgrade.

**SD4 — D leads W lower by >8pts:** Weekly regime about to downgrade. Pre-empt.

**SD5 — INFY + LT both daily RSI <40, slopes negative:** Tighten IC CE wing by 1 strike.
    """)
