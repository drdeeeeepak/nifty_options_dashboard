# pages/07_Stocks_RSI_Weekly.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
import pandas as pd

from data.live_fetcher import get_nifty_daily, get_top10_daily
from analytics.rsi_engine import RSIEngine
from config import TOP_10_NIFTY

st.set_page_config(page_title="P07 · Stocks Weekly RSI", layout="wide")
st_autorefresh(interval=60_000, key="p07_refresh")

st.title("Page 07 — Top 10 Stocks: Weekly RSI Sector Regime")
st.caption("Weekly RSI per stock · Sector alignment · Rotation detection · Index breadth quality")

stock_dfs = get_top10_daily()
eng       = RSIEngine()
stock_sig = eng.stock_signals(stock_dfs)

per   = stock_sig["per_stock"]
rot   = stock_sig["rotation_signal"]
drag  = stock_sig["heavy_drag"]
avg_w = stock_sig["avg_w_rsi"]

# ── METRICS ──────────────────────────────────────────────────────────────────
c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Avg Weekly RSI",    f"{avg_w:.1f}")
c2.metric("In Bull (≥60)",     sum(1 for s in per.values() if s.get("w_rsi", 0) >= 60))
c3.metric("In Bear (<40)",     sum(1 for s in per.values() if s.get("w_rsi", 0) < 40))
c4.metric("Rotation Signal",   "YES 🔄" if rot  else "NO")
c5.metric("Heavy Drag Kill",   "🔴 YES" if drag else "✅ No")

if rot:
    st.warning("🔄 Banks in bull regime + IT in bear regime → Sector rotation active → Iron Condor preferred")
if drag:
    st.error("🔴 Heavy drag: 2+ high-weight stocks below RSI 40 → Exit PE positions")

st.divider()

# ── STOCK RSI GRID ────────────────────────────────────────────────────────────
st.subheader("Weekly RSI by Stock")

cols = st.columns(5)
for idx, sym in enumerate(TOP_10_NIFTY):
    col = cols[idx % 5]
    if idx == 5:
        cols = st.columns(5)

    s      = per.get(sym, {})
    w_rsi  = s.get("w_rsi", 50)
    regime = s.get("w_regime", "—")
    slope  = s.get("w_slope", 0)

    color = (
        "#16a34a" if w_rsi >= 65 else
        "#d97706" if w_rsi >= 45 else
        "#dc2626"
    )
    slope_str = f"{slope:+.1f}/wk"

    with col:
        st.markdown(
            f"<div style='border-top:4px solid {color};"
            f"padding:8px 10px;background:#f8f9fb;border-radius:0 0 6px 6px;"
            f"margin-bottom:8px;'>"
            f"<b style='font-size:13px;'>{sym}</b><br>"
            f"<span style='font-size:22px;font-weight:700;color:{color};'>{w_rsi:.1f}</span><br>"
            f"<span style='font-size:10px;color:#5a6b8a;'>{regime}<br>{slope_str}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        # RSI mini bar
        st.progress(min(w_rsi / 100, 1.0))

st.divider()

# ── SUMMARY TABLE ─────────────────────────────────────────────────────────────
st.subheader("Weekly RSI Summary + Nifty Implication")
rows = []
for sym in TOP_10_NIFTY:
    s      = per.get(sym, {})
    w_rsi  = s.get("w_rsi",  50)
    d_rsi  = s.get("d_rsi",  50)
    regime = s.get("w_regime", "—")
    slope  = s.get("w_slope", 0)

    if regime in ("W_BULL", "W_BULL_EXH"):
        ic_side = "PE side secured"
    elif regime in ("W_BEAR", "W_CAPIT"):
        ic_side = "CE side (drag)"
    else:
        ic_side = "IC neutral"

    rows.append({
        "Stock":        sym,
        "Weekly RSI":   round(w_rsi, 1),
        "Regime":       regime,
        "Slope /wk":    f"{slope:+.1f}",
        "Daily RSI":    round(d_rsi, 1),
        "IC Implication":ic_side,
    })

df_table = pd.DataFrame(rows)

def color_rsi(val):
    try:
        v = float(val)
        if v >= 65:  return "color: #16a34a; font-weight: 600"
        if v < 40:   return "color: #dc2626; font-weight: 600"
        return ""
    except:
        return ""

st.dataframe(
    df_table.style.applymap(color_rsi, subset=["Weekly RSI"]),
    use_container_width=True, hide_index=True
)

# ── RULES ────────────────────────────────────────────────────────────────────
with st.expander("Stocks Weekly RSI Rules"):
    st.markdown("""
**SW1 — 6+ stocks ≥60:** PE spread full size. Strong breadth.

**SW2 — Mixed (4-5 bull, 1-2 bear):** Iron Condor. Avg RSI >55 → PE-heavy; <50 → CE-heavy.

**SW3 — Banking quartet (HDFC/ICICI/Kotak/Axis) all ≥60:** PE floor secured regardless of IT.

**SW4 — 2+ heavyweight stocks (weight >8%) below RSI 40:** Exit all PE. Hard kill.

**Rotation: Banks ≥65 + IT ≤40:** IC only. Banks defend floor, IT caps ceiling. Perfect IC environment.
    """)
