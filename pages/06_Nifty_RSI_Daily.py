# pages/06_Nifty_RSI_Daily.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data.live_fetcher import get_nifty_daily
from analytics.rsi_engine import RSIEngine

st.set_page_config(page_title="P06 · Daily RSI Execution", layout="wide")
st_autorefresh(interval=60_000, key="p06_refresh")

st.title("Page 06 — Nifty Daily RSI — Execution Layer")
st.caption("14-period Daily RSI · 6 execution zones · Slope · Divergence · Phase · Entry timing")

df  = get_nifty_daily()
eng = RSIEngine()
sig = eng.signals(df)

# ── METRICS ──────────────────────────────────────────────────────────────────
c1,c2,c3,c4,c5,c6,c7 = st.columns(7)
c1.metric("Daily RSI",    f"{sig['rsi_daily']:.1f}")
c2.metric("Daily Zone",   sig["d_zone"])
c3.metric("Slope 1d",     f"{sig['d_slope_1d']:+.2f}")
c4.metric("Slope 2d",     f"{sig['d_slope_2d']:+.2f}")
c5.metric("Phase",        sig["momentum_phase"])
c6.metric("Alignment",    sig["alignment"])
c7.metric("Entry Timing", sig["entry_timing"])

st.divider()

# ── ZONE GAUGE ────────────────────────────────────────────────────────────────
d_rsi = sig["rsi_daily"]

DZONES = [
    (0,  32, "#fee2e2", "Capit"),
    (32, 39, "#fecaca", "Bear P"),
    (39, 54, "#dbeafe", "Balance"),
    (54, 61, "#d1fae5", "Bull P"),
    (61, 68, "#bbf7d0", "Bull P+"),
    (68, 100,"#fef3c7", "Exhaust"),
]

fig_g = go.Figure()
for lo, hi, color, label in DZONES:
    fig_g.add_shape(type="rect", x0=lo, x1=hi, y0=0, y1=1,
        fillcolor=color, line_width=0, layer="below")
    fig_g.add_annotation(x=(lo+hi)/2, y=0.5, text=f"<b>{label}</b>",
        showarrow=False, font=dict(size=9, color="#334155"))

fig_g.add_shape(type="line", x0=d_rsi, x1=d_rsi, y0=-0.2, y1=1.2,
    line=dict(color="#0f1724", width=3))
fig_g.add_annotation(x=d_rsi, y=-0.35, text=f"<b>{d_rsi:.1f}</b>",
    showarrow=False, font=dict(size=13))

fig_g.update_layout(
    height=110, margin=dict(t=15, b=40, l=10, r=10),
    paper_bgcolor="white", plot_bgcolor="white",
    xaxis=dict(range=[0, 100], showgrid=False, showticklabels=False),
    yaxis=dict(visible=False),
)
st.plotly_chart(fig_g, use_container_width=True)

st.divider()

# ── PRICE + RSI CHART ─────────────────────────────────────────────────────────
df_comp = eng.compute(df.copy()).tail(90)

fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
    row_heights=[0.55, 0.45], vertical_spacing=0.04)

fig.add_trace(go.Candlestick(
    x=df_comp.index,
    open=df_comp["open"], high=df_comp["high"],
    low=df_comp["low"],   close=df_comp["close"],
    name="Nifty",
    increasing_line_color="#16a34a",
    decreasing_line_color="#dc2626",
), row=1, col=1)

fig.add_trace(go.Scatter(
    x=df_comp.index, y=df_comp["rsi_daily"],
    mode="lines", name="Daily RSI",
    line=dict(color="#7c3aed", width=2),
    fill="tozeroy", fillcolor="rgba(124,58,237,0.07)",
), row=2, col=1)

# Zone reference lines
for level, color, lbl in [
    (68, "#dc2626", "Exhaust 68"),
    (61, "#16a34a", "Bull+ 61"),
    (54, "#2563eb", "Balance 54"),
    (46, "#d97706", "Balance 46"),
    (39, "#dc2626", "Bear P 39"),
    (32, "#7f1d1d", "Capit 32"),
]:
    fig.add_hline(y=level, line_dash="dot", line_color=color,
                  annotation_text=lbl, annotation_position="right",
                  row=2, col=1)

fig.update_layout(
    height=440, xaxis_rangeslider_visible=False,
    paper_bgcolor="white", plot_bgcolor="#f8f9fb",
    legend=dict(orientation="h", y=-0.12),
    margin=dict(t=20, b=20),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── MTF MATRIX ────────────────────────────────────────────────────────────────
st.subheader("Multi-Timeframe Interaction")
w_regime = sig["w_regime"]
d_zone   = sig["d_zone"]

MATRIX = {
    ("W_BULL",       "D_BALANCE"):          ("Bull Put Spread · Full",  "green"),
    ("W_NEUTRAL",    "D_BALANCE"):          ("Iron Condor · Full",      "blue"),
    ("W_BEAR",       "D_BALANCE"):          ("Small CE only",           "red"),
    ("W_BULL",       "D_BULL_PRESSURE"):    ("Bull PCS · Full",         "green"),
    ("W_NEUTRAL",    "D_BULL_PRESSURE"):    ("Asym IC · PE-heavy",      "blue"),
    ("W_BEAR",       "D_BULL_PRESSURE"):    ("TRAP — Small CE",         "amber"),
    ("W_BULL",       "D_BULL_PRESSURE_PLUS"):("Bull PCS · Full",        "green"),
    ("W_NEUTRAL",    "D_BULL_PRESSURE_PLUS"):("Asym IC · PE-heavy",     "blue"),
    ("W_BULL",       "D_EXHAUST"):          ("Dual Exhaust — CE entry", "amber"),
    ("W_BEAR",       "D_BEAR_PRESSURE"):    ("Bear CCS · Full",         "red"),
    ("W_NEUTRAL",    "D_BEAR_PRESSURE"):    ("Small CE · Caution",      "amber"),
    ("W_BULL",       "D_BEAR_PRESSURE"):    ("WAIT — No trade",         "amber"),
}

color_map = {"green":"#dcfce7", "blue":"#dbeafe", "red":"#fee2e2", "amber":"#fef3c7"}

current_key = (w_regime, d_zone)
if current_key in MATRIX:
    label, color = MATRIX[current_key]
    st.markdown(
        f"<div style='background:{color_map.get(color,'#f8f9fb')};"
        f"border-radius:8px;padding:14px 18px;border:1.5px solid #e2e6ef;'>"
        f"<b>Current ({w_regime} × {d_zone}):</b> {label}</div>",
        unsafe_allow_html=True,
    )
else:
    st.info(f"Regime {w_regime} × Zone {d_zone}: Assess individually")

# ── ENTRY RULES ───────────────────────────────────────────────────────────────
with st.expander("Execution Entry Rules"):
    st.markdown("""
**E1 (PRIME PE — early):** Weekly RSI ≥45 + Daily RSI was >54, pulls back to 46–54 balance. Full size.

**E2 (MID PE):** Daily RSI crosses above 54 from below, slope positive, weekly ≥50. 75% size.

**E3 (LATE — CE entry):** Daily RSI crosses above 68. This is the CE spread trigger. 50% size.

**E4 (PRIME CE — early):** Weekly RSI ≤55 + Daily RSI was <46, rallies to 46–54. Full size.

**Kill K2:** Daily RSI skips balance zone (≥54 → <46 in one session) → Hard exit all PE.

**Kill K5:** Daily RSI >68 and slope turns negative for first time → Soft exit 50%.
    """)
