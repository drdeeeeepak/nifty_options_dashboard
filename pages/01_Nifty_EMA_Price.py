# pages/01_Nifty_EMA_Price.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
from data.live_fetcher import get_nifty_spot, get_nifty_daily
from analytics.ema import EMAEngine
from config import MTF_EMA_PERIODS

st.set_page_config(page_title="P01 · Nifty EMA vs Price", layout="wide")
st_autorefresh(interval=60_000, key="p01_refresh")

st.title("Page 01 — Nifty Price vs MTF Proxy EMAs")
st.caption("7 EMAs on Daily chart · Each proxies 200 EMA of that intraday timeframe")

spot    = get_nifty_spot()
df      = get_nifty_daily()
eng     = EMAEngine()
sig     = eng.signals(df)

# ── METRICS ROW ──────────────────────────────────────────────────────────────
c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Nifty Spot",      f"{spot:,.0f}")
c2.metric("Structure",       sig["ema_regime"])
c3.metric("EMAs below spot", f"{sig['alignment_score']}/7")
sup = sig.get("support_ema")
res = sig.get("resistance_ema")
c4.metric("Nearest Support", f"EMA{sup['period']} {sup['value']:,.0f}" if sup else "—")
c5.metric("Nearest Resist",  f"EMA{res['period']} {res['value']:,.0f}" if res else "—")

st.divider()

# ── EMA CHART ────────────────────────────────────────────────────────────────
ema_colors = {
    3:   "#ef4444",
    8:   "#f97316",
    16:  "#eab308",
    30:  "#22c55e",
    60:  "#06b6d4",
    120: "#3b82f6",
    200: "#7c3aed",
}

df_plot = eng.compute(df.copy()).tail(120)
fig = go.Figure()

# Candlesticks
fig.add_trace(go.Candlestick(
    x=df_plot.index,
    open=df_plot["open"], high=df_plot["high"],
    low=df_plot["low"],   close=df_plot["close"],
    name="Nifty",
    increasing_line_color="#16a34a",
    decreasing_line_color="#dc2626",
))

for p, color in ema_colors.items():
    col = f"ema_{p}"
    if col in df_plot.columns:
        fig.add_trace(go.Scatter(
            x=df_plot.index, y=df_plot[col],
            mode="lines", name=f"EMA{p} ({MTF_EMA_PERIODS[p]})",
            line=dict(color=color, width=1.2),
        ))

fig.update_layout(
    height=500, xaxis_rangeslider_visible=False,
    paper_bgcolor="white", plot_bgcolor="#f8f9fb",
    legend=dict(orientation="h", y=-0.15),
    margin=dict(t=20, b=20),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── EMA POSITION LADDER ───────────────────────────────────────────────────────
st.subheader("EMA Position Ladder")
ema_vals = sig["ema_values"]
for p in [3, 8, 16, 30, 60, 120, 200]:
    val = ema_vals.get(f"ema_{p}", 0)
    above = spot < val   # EMA is above spot
    color  = "🔴" if above else "🟢"
    label  = "ABOVE spot (resistance)" if above else "BELOW spot (support)"
    st.markdown(
        f"{color} **EMA{p}** ({MTF_EMA_PERIODS[p]}) = "
        f"`{val:,.0f}` — {label}"
    )

st.divider()

# ── CROSSOVERS ───────────────────────────────────────────────────────────────
st.subheader("Recent EMA Crossovers (last 5 sessions)")
crossovers = sig.get("crossovers", [])
if crossovers:
    for cx in crossovers:
        icon = "🟢" if cx["type"] == "GOLDEN" else "🔴"
        st.markdown(
            f"{icon} **{cx['type']}**: EMA{cx['shorter']} × EMA{cx['longer']} "
            f"({cx['proxy_shorter']} × {cx['proxy_longer']}) — {cx['days_ago']}d ago"
        )
else:
    st.info("No crossovers in last 5 sessions.")

# ── RULES ─────────────────────────────────────────────────────────────────────
with st.expander("Analysis Rules"):
    st.markdown("""
**Rule 1: Count EMAs below spot**
- 5–7 below → Bullish → PE spread. EMA60 (2hr proxy) = PE short floor.
- 3–4 below → Neutral → Iron Condor.
- 0–2 below → Bearish → CE spread. EMA60 = CE ceiling.

**Rule 2: EMA30 + EMA60 cluster = Support floor**
- EMA30 (1hr) and EMA60 (2hr) within 100pts = demand cluster = PE anchor.

**Rule 3: EMA3 + EMA8 above spot = Resistance ceiling**
- 5min and 15min proxies above spot = near-term CE anchor.

**Kill Switch: Price loses EMA60 on daily close → EXIT all PE spreads.**
    """)
