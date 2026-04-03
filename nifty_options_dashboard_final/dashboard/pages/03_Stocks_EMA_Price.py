# pages/03_Stocks_EMA_Price.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from data.live_fetcher import get_nifty_spot, get_top10_daily
from analytics.ema import EMAEngine
from config import MTF_EMA_PERIODS, TOP_10_NIFTY, BREADTH_MULTIPLIERS

st.set_page_config(page_title="P03 · Stocks EMA vs Price", layout="wide")
st_autorefresh(interval=60_000, key="p03_refresh")

st.title("Page 03 — Top 10 Stocks: Price vs MTF Proxy EMAs")
st.caption("Each stock vs 7 proxy EMAs · Breadth signal for Nifty Index credit options")

spot     = get_nifty_spot()
stock_dfs= get_top10_daily()
eng      = EMAEngine()
breadth  = eng.breadth_signals(stock_dfs)

# ── BREADTH METRICS ──────────────────────────────────────────────────────────
c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Above EMA60 (2hr)", f"{breadth['above_ema60']}/10")
c2.metric("Above EMA200",      f"{breadth['above_ema200']}/10")
c3.metric("Breadth Regime",    breadth["breadth_regime"])
c4.metric("Size Multiplier",   f"{breadth['size_multiplier']:.2f}×")
c5.metric("Home Score",        f"{breadth['home_score']}/4")

if breadth["rotation_signal"]:
    st.warning("🔄 **Sector Rotation Detected** — Banks bullish, IT bearish → Iron Condor preferred over pure PE spread")

st.divider()

# ── MINI CHARTS GRID (2 rows × 5 cols) ───────────────────────────────────────
st.subheader("Stock-by-Stock EMA Position")

EMA_COLORS = {
    3: "#ef4444", 8: "#f97316", 16: "#eab308",
    30: "#22c55e", 60: "#06b6d4", 120: "#3b82f6", 200: "#7c3aed",
}

per_stock = breadth["per_stock"]

cols = st.columns(5)
for i, symbol in enumerate(TOP_10_NIFTY):
    col = cols[i % 5]
    if i == 5:
        cols = st.columns(5)   # second row

    stock_sig = per_stock.get(symbol, {})
    df_raw    = stock_dfs.get(symbol, pd.DataFrame())

    above60  = stock_sig.get("above_ema60",  False)
    above200 = stock_sig.get("above_ema200", False)
    regime   = stock_sig.get("regime", "—")
    ribbon   = stock_sig.get("ribbon_pct", 0)

    border_color = "#16a34a" if above60 else "#dc2626"

    with col:
        st.markdown(
            f"<div style='border-left:4px solid {border_color};"
            f"padding:6px 10px;background:#f8f9fb;border-radius:0 6px 6px 0;"
            f"margin-bottom:4px;'>"
            f"<b>{symbol}</b><br>"
            f"<span style='font-size:11px;color:#5a6b8a;'>"
            f"{'✅ EMA60' if above60 else '❌ EMA60'} · "
            f"{'✅ EMA200' if above200 else '❌ EMA200'}<br>"
            f"Ribbon: {ribbon:.1f}% · {regime}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Mini sparkline
        if not df_raw.empty:
            df_stock = eng.compute(df_raw.copy()).tail(30)
            fig_mini = go.Figure()
            fig_mini.add_trace(go.Scatter(
                x=df_stock.index, y=df_stock["close"],
                mode="lines", line=dict(color=border_color, width=1.5),
                showlegend=False,
            ))
            for p, color in [(60, "#06b6d4"), (200, "#7c3aed")]:
                col_name = f"ema_{p}"
                if col_name in df_stock.columns:
                    fig_mini.add_trace(go.Scatter(
                        x=df_stock.index, y=df_stock[col_name],
                        mode="lines",
                        line=dict(color=color, width=0.8, dash="dot"),
                        showlegend=False,
                    ))
            fig_mini.update_layout(
                height=80, margin=dict(l=0,r=0,t=0,b=0),
                paper_bgcolor="white", plot_bgcolor="#f8f9fb",
                xaxis=dict(visible=False), yaxis=dict(visible=False),
            )
            st.plotly_chart(fig_mini, use_container_width=True, key=f"mini_{symbol}")

st.divider()

# ── BREADTH SUMMARY TABLE ────────────────────────────────────────────────────
st.subheader("EMA Status Summary")
rows = []
for sym in TOP_10_NIFTY:
    s = per_stock.get(sym, {})
    ev = s.get("ema_values", {})
    rows.append({
        "Stock":      sym,
        "Above EMA60":  "✅" if s.get("above_ema60")  else "❌",
        "Above EMA30":  "✅" if s.get("above_ema60")  else "—",
        "Above EMA200": "✅" if s.get("above_ema200") else "❌",
        "Regime":       s.get("regime", "—"),
        "Ribbon %":     f"{s.get('ribbon_pct', 0):.1f}%",
    })
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── RULES ────────────────────────────────────────────────────────────────────
with st.expander("Breadth Rules for Nifty Credit Options"):
    st.markdown("""
| Above EMA60 | Regime | Size Multiplier | Strategy |
|-------------|--------|----------------|----------|
| 8–10 / 10   | Strong Bull | 1.00× | PE spread full |
| 6–7 / 10    | Moderate Bull | 0.85× | PE spread or IC-PE heavy |
| 4–5 / 10    | Neutral | 0.65× | Iron Condor only |
| 0–3 / 10    | Bear breadth | 0.40× | CE spread or no trade |

**Banking test**: HDFC + ICICI + Kotak + Axis all above EMA60 → PE floor secured regardless of IT weakness.

**Heavy drag kill**: 2+ stocks with weight >8% below weekly RSI 40 → exit PE positions.
    """)
