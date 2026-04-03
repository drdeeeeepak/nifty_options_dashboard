# pages/04_Stocks_EMA_Ribbon.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
import pandas as pd

from data.live_fetcher import get_top10_daily
from analytics.ema import EMAEngine
from config import TOP_10_NIFTY, MTF_EMA_PERIODS

st.set_page_config(page_title="P04 · Stocks EMA Ribbon", layout="wide")
st_autorefresh(interval=60_000, key="p04_refresh")

st.title("Page 04 — Top 10 Stocks: EMA Ribbon (EMAs vs EMAs)")
st.caption("Ribbon state per stock · Leader/Laggard detection · Sector rotation signal")

stock_dfs = get_top10_daily()
eng       = EMAEngine()
breadth   = eng.breadth_signals(stock_dfs)
per_stock = breadth["per_stock"]

# ── SUMMARY METRICS ──────────────────────────────────────────────────────────
leaders   = breadth["leaders"]
laggards  = breadth["laggards"]
compressed= breadth["compressed"]
rotation  = breadth["rotation_signal"]

c1,c2,c3,c4 = st.columns(4)
c1.metric("Leaders (bull fan >2%)", len(leaders))
c2.metric("Laggards (inverted)",    len(laggards))
c3.metric("Compressed (<1%)",       len(compressed))
c4.metric("Rotation Signal",        "YES 🔄" if rotation else "NO")

if rotation:
    st.warning("🔄 **Sector rotation**: Banks ribbon fanning up, IT ribbon inverting → IC preferred, not pure PE spread")

st.divider()

# ── RIBBON VISUALIZATION ──────────────────────────────────────────────────────
st.subheader("Ribbon State per Stock")

EMA_COLORS_LIST = ["#ef4444","#f97316","#eab308","#22c55e","#06b6d4","#3b82f6","#7c3aed"]
PERIODS = [3, 8, 16, 30, 60, 120, 200]

cols = st.columns(5)
for idx, sym in enumerate(TOP_10_NIFTY):
    col = cols[idx % 5]
    if idx == 5:
        cols = st.columns(5)

    sig = per_stock.get(sym, {})
    ev  = sig.get("ema_values", {})
    rp  = sig.get("ribbon_pct", 0)
    rs  = sig.get("ribbon_state", "NORMAL")
    regime = sig.get("regime", "—")

    if sym in leaders:
        border = "#16a34a"; role = "Leader"
    elif sym in laggards:
        border = "#dc2626"; role = "Laggard"
    elif sym in compressed:
        border = "#7c3aed"; role = "Coiling"
    else:
        border = "#d97706"; role = "Neutral"

    # Ribbon bar: 7 coloured segments
    vals = [ev.get(f"ema_{p}", 0) for p in PERIODS]
    min_v = min(v for v in vals if v > 0) if any(v > 0 for v in vals) else 1
    max_v = max(vals) if vals else 1

    with col:
        st.markdown(
            f"<div style='border-left:4px solid {border};"
            f"padding:6px 10px;background:#f8f9fb;border-radius:0 6px 6px 0;"
            f"margin-bottom:4px;'>"
            f"<b>{sym}</b> <span style='font-size:10px;color:{border};'>({role})</span><br>"
            f"<span style='font-size:10px;color:#5a6b8a;'>"
            f"Spread: {rp:.1f}% · {rs}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Mini ribbon bar
        df_raw = stock_dfs.get(sym, pd.DataFrame())
        if not df_raw.empty:
            df_s = eng.compute(df_raw.copy()).tail(30)
            fig_r = go.Figure()
            for p, color in zip(PERIODS, EMA_COLORS_LIST):
                c_ = f"ema_{p}"
                if c_ in df_s.columns:
                    fig_r.add_trace(go.Scatter(
                        x=df_s.index, y=df_s[c_],
                        mode="lines", name=f"EMA{p}",
                        line=dict(color=color, width=1),
                        showlegend=False,
                    ))
            fig_r.update_layout(
                height=70, margin=dict(l=0,r=0,t=0,b=0),
                paper_bgcolor="white", plot_bgcolor="#f8f9fb",
                xaxis=dict(visible=False), yaxis=dict(visible=False),
            )
            st.plotly_chart(fig_r, use_container_width=True, key=f"ribbon_{sym}")

st.divider()

# ── LEADER / LAGGARD TABLE ────────────────────────────────────────────────────
st.subheader("Leader / Laggard Classification")
rows = []
for sym in TOP_10_NIFTY:
    sig    = per_stock.get(sym, {})
    rp     = sig.get("ribbon_pct", 0)
    rs     = sig.get("ribbon_state", "—")
    regime = sig.get("regime", "—")

    if sym in leaders:
        role = "🟢 Leader"
        implication = "Strong bull — supporting Nifty floor"
    elif sym in laggards:
        role = "🔴 Laggard"
        implication = "Drag — capping Nifty upside"
    elif sym in compressed:
        role = "🟣 Coiling"
        implication = "Breakout imminent — watch direction"
    else:
        role = "🟡 Neutral"
        implication = "Participating but not leading"

    rows.append({
        "Stock":       sym,
        "Role":        role,
        "Ribbon %":    f"{rp:.1f}%",
        "State":       rs,
        "Regime":      regime,
        "Implication": implication,
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── RULES ────────────────────────────────────────────────────────────────────
with st.expander("Ribbon Rules for Nifty Credit Options"):
    st.markdown("""
**Rule R1 — 6+ stocks in bull fan:** Full IC · PE-heavy · 1.0× size multiplier.

**Rule R2 — Rotation: Banks bull fan + IT inverted ribbon:**
IC only. Asymmetric: CE tighter (IT caps upside) + PE wider (banks defend floor).

**Rule R3 — 2+ stocks compressed (<1% ribbon):**
Defer new positions 1 session. Wait for coil to break direction.

**Rule R4 — 5+ stocks bear fan:**
No PE spreads. CE only. Size multiplier 0.40×.

**Practical read**: Leaders = stocks already running ahead of Nifty. Laggards = drag. 
If 3+ bank stocks are leaders → Nifty floor is institutionally backed → PE conviction high.
    """)
