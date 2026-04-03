# pages/05_Nifty_RSI_Weekly.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from data.live_fetcher import get_nifty_daily
from analytics.rsi_engine import RSIEngine

st.set_page_config(page_title="P05 · Weekly RSI Regime", layout="wide")
st_autorefresh(interval=60_000, key="p05_refresh")

st.title("Page 05 — Nifty Weekly RSI — Regime Context Layer")
st.caption("14-period Weekly RSI · Primary regime identification · Sets weekly context for biweekly credit options entry")

df  = get_nifty_daily()
eng = RSIEngine()
sig = eng.signals(df)

# ── METRICS ──────────────────────────────────────────────────────────────────
c1,c2,c3,c4,c5,c6 = st.columns(6)
c1.metric("Weekly RSI",   f"{sig['rsi_weekly']:.1f}")
c2.metric("W-Regime",     sig["w_regime"])
c3.metric("W-Slope",      f"{sig['w_slope_1w']:+.2f}/wk")
c4.metric("Range Shift",  "Bull active" if sig["range_shift"].get("bull_range") else "Forming")
c5.metric("Home Score",   f"{sig['home_score']}/20")
kills = sig["kill_switches"]
any_kill = any(kills.values())
c6.metric("Kill Switches","🔴 ACTIVE" if any_kill else "✅ Clear")

st.divider()

# ── REGIME GAUGE ─────────────────────────────────────────────────────────────
w_rsi = sig["rsi_weekly"]

ZONES = [
    (0,  30,  "#fee2e2", "Capitulation"),
    (30, 40,  "#fca5a5", "Bear"),
    (40, 45,  "#fef3c7", "Bear→Neutral"),
    (45, 60,  "#dbeafe", "Neutral"),
    (60, 65,  "#fef3c7", "Neutral→Bull"),
    (65, 70,  "#dcfce7", "Bull"),
    (70, 100, "#fef3c7", "Exhaustion"),
]

fig_gauge = go.Figure()
for lo, hi, color, label in ZONES:
    fig_gauge.add_shape(type="rect",
        x0=lo, x1=hi, y0=0, y1=1,
        fillcolor=color, line_width=0, layer="below"
    )
    fig_gauge.add_annotation(x=(lo+hi)/2, y=0.5,
        text=f"<b>{label}</b><br>{lo}–{hi}",
        showarrow=False, font=dict(size=9, color="#334155"),
    )

# Pointer
fig_gauge.add_shape(type="line",
    x0=w_rsi, x1=w_rsi, y0=-0.15, y1=1.15,
    line=dict(color="#0f1724", width=3),
)
fig_gauge.add_annotation(x=w_rsi, y=-0.25,
    text=f"<b>{w_rsi:.1f}</b>",
    showarrow=False, font=dict(size=13, color="#0f1724"),
)

fig_gauge.update_layout(
    height=130, margin=dict(t=20, b=40, l=10, r=10),
    paper_bgcolor="white", plot_bgcolor="white",
    xaxis=dict(range=[0, 100], showgrid=False, showticklabels=False),
    yaxis=dict(range=[-0.4, 1.4], showgrid=False, showticklabels=False, visible=False),
)
st.plotly_chart(fig_gauge, use_container_width=True)

st.divider()

# ── WEEKLY RSI CHART ──────────────────────────────────────────────────────────
df_comp = eng.compute(df.copy())

# Resample to weekly
weekly = df_comp["rsi_weekly"].resample("W-TUE").last().dropna().tail(52)
price_weekly = df_comp["close"].resample("W-TUE").last().dropna().tail(52)

fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
    row_heights=[0.6, 0.4], vertical_spacing=0.04)

fig.add_trace(go.Scatter(
    x=price_weekly.index, y=price_weekly.values,
    mode="lines", name="Nifty (weekly close)",
    line=dict(color="#2563eb", width=2),
), row=1, col=1)

fig.add_trace(go.Scatter(
    x=weekly.index, y=weekly.values,
    mode="lines", name="Weekly RSI",
    line=dict(color="#7c3aed", width=2),
    fill="tozeroy", fillcolor="rgba(124,58,237,0.07)",
), row=2, col=1)

# RSI zone lines
for level, color, label in [(70,"#dc2626","Exhaust"), (60,"#d97706","Bull"), (45,"#2563eb","Neutral"), (30,"#dc2626","Bear")]:
    fig.add_hline(y=level, line_dash="dot", line_color=color,
                  annotation_text=label, annotation_position="right",
                  row=2, col=1)

fig.update_layout(
    height=420, paper_bgcolor="white", plot_bgcolor="#f8f9fb",
    legend=dict(orientation="h", y=-0.12),
    margin=dict(t=20, b=20),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── REGIME → STRATEGY TABLE ───────────────────────────────────────────────────
st.subheader("Current Regime → Options Strategy")

REGIME_TABLE = {
    "W_CAPIT":      ("Capitulation",    "No trade",         "0%",    "—"),
    "W_BEAR":       ("Bear",            "Bear Call Spread",  "100%",  "CE only"),
    "W_BEAR_TRANS": ("Bear→Neutral",    "CE-heavy IC",       "50%",   "CE dominant"),
    "W_NEUTRAL":    ("Neutral",         "Iron Condor",       "100%",  "Both balanced"),
    "W_BULL_TRANS": ("Neutral→Bull",    "PE-heavy IC",       "100%",  "PE dominant"),
    "W_BULL":       ("Bull",            "Bull Put Spread",   "100%",  "PE only"),
    "W_BULL_EXH":   ("Bull Exhaustion", "CE entry + PE exit","75%",   "Flip to CE"),
}

current = sig["w_regime"]
for regime_key, (label, strategy, size, notes) in REGIME_TABLE.items():
    is_current = regime_key == current
    bg = "#dbeafe" if is_current else ""
    marker = "◀ CURRENT" if is_current else ""
    cols = st.columns([2,2.5,1,2,1.5])
    cols[0].markdown(f"**{label}**")
    cols[1].markdown(f"`{strategy}`")
    cols[2].markdown(size)
    cols[3].markdown(notes)
    cols[4].markdown(f"**{marker}**")

# ── KILL SWITCHES ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("Kill Switches")
for k, v in kills.items():
    icon = "🔴 ACTIVE" if v else "✅ Clear"
    st.markdown(f"{icon} — **{k}**")

with st.expander("Kill Switch Details"):
    st.markdown("""
- **K1** — Weekly regime flip against position → Exit all PE or CE at next open
- **K2** — Daily zone skip (bypasses balance zone) → Hard exit
- **K3** — Dual exhaustion (weekly >70 + daily >68) → CE entry + PE exit
- **K4** — Range shift failure (held above 45 then drops below 40) → Soft exit 50%
- **K5** — Slope sign change at exhaustion → Soft exit 50%
    """)
