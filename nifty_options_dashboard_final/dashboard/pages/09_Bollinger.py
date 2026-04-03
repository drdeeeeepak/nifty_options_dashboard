# pages/09_Bollinger.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data.live_fetcher import get_nifty_spot, get_nifty_daily
from analytics.bollinger import BollingerOptionsEngine

st.set_page_config(page_title="P09 · Bollinger Bands", layout="wide")
st_autorefresh(interval=60_000, key="p09_refresh")

st.title("Page 09 — Bollinger Bands Options Framework")
st.caption("20-period SMA · 2 SD · 5 regimes · Strike selection · Kill switches")

spot = get_nifty_spot()
df   = get_nifty_daily()
eng  = BollingerOptionsEngine()
sig  = eng.signals(df)

# ── METRICS ──────────────────────────────────────────────────────────────────
c1,c2,c3,c4,c5,c6,c7 = st.columns(7)
c1.metric("Upper Band",  f"{sig['upper']:,.0f}")
c2.metric("Basis (SMA)", f"{sig['basis']:,.0f}")
c3.metric("Lower Band",  f"{sig['lower']:,.0f}")
c4.metric("BW%",         f"{sig['bw_pct']:.2f}%")
c5.metric("Regime",      sig["regime"])
c6.metric("CE Strike",   f"{sig['ce_strike']:,.0f}" if sig["ce_strike"] else "—")
c7.metric("PE Strike",   f"{sig['pe_strike']:,.0f}" if sig["pe_strike"] else "—")

kills = sig["kill_switches"]
any_kill = any([kills.get("K1"), kills.get("K2"), kills.get("K3")])
if any_kill:
    st.error(f"🔴 HARD KILL ACTIVE: {[k for k,v in kills.items() if v]}")

# ── ADJUSTMENTS ──────────────────────────────────────────────────────────────
adjustments = sig.get("adjustments", [])
if adjustments:
    for adj in adjustments:
        new_s = adj.get("new_strike", "")
        st.warning(
            f"⚠️ **Mid-flight adjustment {adj['code']} ({adj['leg']}):** "
            f"{adj['action']}" + (f" → New strike: {new_s:,.0f}" if new_s else "")
        )

st.divider()

# ── BOLLINGER CHART ───────────────────────────────────────────────────────────
df_comp = eng.compute(df.copy()).tail(90)
fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
    row_heights=[0.7, 0.3], vertical_spacing=0.04)

# Price + bands
fig.add_trace(go.Candlestick(
    x=df_comp.index, open=df_comp["open"], high=df_comp["high"],
    low=df_comp["low"], close=df_comp["close"], name="Nifty",
    increasing_line_color="#16a34a", decreasing_line_color="#dc2626",
), row=1, col=1)

fig.add_trace(go.Scatter(
    x=df_comp.index, y=df_comp["bb_upper"],
    mode="lines", name="Upper Band",
    line=dict(color="#dc2626", width=1.2, dash="dot"),
), row=1, col=1)

fig.add_trace(go.Scatter(
    x=df_comp.index, y=df_comp["bb_basis"],
    mode="lines", name="Basis (20 SMA)",
    line=dict(color="#2563eb", width=1.5),
), row=1, col=1)

fig.add_trace(go.Scatter(
    x=df_comp.index, y=df_comp["bb_lower"],
    mode="lines", name="Lower Band",
    line=dict(color="#16a34a", width=1.2, dash="dot"),
    fill="tonexty",
    fillcolor="rgba(22,163,74,0.04)",
), row=1, col=1)

# BW% chart
fig.add_trace(go.Scatter(
    x=df_comp.index, y=df_comp["bb_bw"],
    mode="lines", name="Bandwidth %",
    line=dict(color="#7c3aed", width=1.5),
    fill="tozeroy", fillcolor="rgba(124,58,237,0.08)",
), row=2, col=1)

# Threshold lines on BW chart
for level, color, lbl in [(3.5,"#7c3aed","Squeeze"), (7.0,"#dc2626","Expand"), (5.0,"#16a34a","Normal lo"), (8.0,"#dc2626","Hard expand")]:
    fig.add_hline(y=level, line_dash="dot", line_color=color,
                  annotation_text=lbl, row=2, col=1)

fig.update_layout(
    height=460, xaxis_rangeslider_visible=False,
    paper_bgcolor="white", plot_bgcolor="#f8f9fb",
    legend=dict(orientation="h", y=-0.12),
    margin=dict(t=20, b=20),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── REGIME TABLE ─────────────────────────────────────────────────────────────
st.subheader("5 Regimes → Strategy")
REGIMES = [
    ("SQUEEZE",     "<3.5%",  "No trade — wait for direction",        "0%",   "—",               "—"),
    ("WALK_UPPER",  ">5.5%",  "Bull Put Spread · CE far OTM",         "100%", "UB+0.5×half",     "Basis"),
    ("WALK_LOWER",  ">5.5%",  "Bear Call Spread · PE far OTM",        "100%", "Basis",           "LB-0.5×half"),
    ("MEAN_REVERT", "Any",    "Iron Condor · tight at bands",         "100%", "prev_UB",         "prev_LB"),
    ("NEUTRAL_WALK","4–7%",   "Iron Condor · band-anchored",          "100%", "UB rounded up 50","LB rounded dn 50"),
]
import pandas as pd
df_r = pd.DataFrame(REGIMES, columns=["Regime","BW%","Strategy","Size","CE Strike","PE Strike"])
current_r = sig["regime"]
def highlight_regime(row):
    if row["Regime"] == current_r:
        return ["background-color:#dbeafe"] * len(row)
    return [""] * len(row)
st.dataframe(df_r.style.apply(highlight_regime, axis=1), use_container_width=True, hide_index=True)

# ── KILL SWITCHES ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("Kill Switches")
for k, v in kills.items():
    icon = "🔴 ACTIVE" if v else "✅ Clear"
    st.markdown(f"{icon} — **{k}**")

with st.expander("Kill Switch Details"):
    st.markdown("""
- **K1 (HARD)** — Close beyond short strike (upper or lower band)
- **K2 (HARD)** — Bandwidth explosion ≥40% from entry BW%
- **K3 (HARD)** — Full candle body (open AND close) beyond band
- **K4 (SOFT)** — Basis cross against position direction
- **K5 (SOFT)** — Walk streak breaks (3+ walk candles then first close inside)
    """)
