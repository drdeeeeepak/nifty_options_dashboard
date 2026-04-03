# pages/11_VIX_IV.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go

from data.live_fetcher import get_nifty_daily, get_india_vix, get_vix_history
from analytics.vix_iv_regime import VixIVRegimeEngine
from analytics.options_chain import OptionsChainEngine
from data.live_fetcher import get_nifty_spot, get_dual_expiry_chains

st.set_page_config(page_title="P11 · VIX / IV Regime", layout="wide")
st_autorefresh(interval=60_000, key="p11_refresh")

st.title("Page 11 — VIX / IV Volatility Regime Engine")
st.caption("India VIX · IVP 1yr + 5yr · VRP = ATM IV − HV20 · IV Skew · Term Structure")

spot      = get_nifty_spot()
nifty_df  = get_nifty_daily()
vix_live  = get_india_vix()
vix_hist  = get_vix_history()
chains    = get_dual_expiry_chains(spot)

oc_eng  = OptionsChainEngine()
oc_sig  = oc_eng.signals(chains["far"], spot, chains["far_dte"])
atm_iv  = oc_sig.get("atm_iv", 11.4)

eng = VixIVRegimeEngine()
sig = eng.signals(nifty_df, vix_hist, vix_live, atm_iv)

# ── METRICS ──────────────────────────────────────────────────────────────────
c1,c2,c3,c4,c5,c6,c7 = st.columns(7)
c1.metric("India VIX",      f"{vix_live:.2f}")
c2.metric("VIX Zone",       sig["vix_zone"])
c3.metric("IVP (1yr)",      f"{sig['ivp_1yr']:.0f}th pctile")
c4.metric("IVP (5yr)",      f"{sig['ivp_5yr']:.0f}th pctile")
c5.metric("ATM IV",         f"{sig['atm_iv']:.1f}%")
c6.metric("HV20",           f"{sig['hv20']:.1f}%")
c7.metric("VRP",            f"{sig['vrp']:+.1f}%")

kills = sig["kill_switches"]
if kills.get("HARD_KILL"):
    st.error("🔴 HARD KILL: VIX in Crisis/Extreme zone. No short premium. Exit all credit spreads.")
if kills.get("K4_vrp_negative"):
    st.warning("⚠️ VRP negative (ATM IV < HV20). Edge gone. Reduce all credit positions 50%.")
if kills.get("K2_regime_shift"):
    st.warning("⚠️ VIX crossed above 20. Regime shift. Re-price IC wings wider.")

st.divider()

# ── VIX GAUGE ────────────────────────────────────────────────────────────────
ZONES = [
    (0,  11, "#ede9fe", "Complacent Zone 1"),
    (11, 17, "#fef3c7", "Low-Normal Zone 2"),
    (17, 20, "#dcfce7", "Sweet Spot Zone 3"),
    (20, 28, "#dbeafe", "Elevated Zone 4"),
    (28, 40, "#fee2e2", "Crisis Zone 5"),
    (40, 60, "#fecaca", "Extreme Zone 6"),
]

fig_vix = go.Figure()
for lo, hi, color, label in ZONES:
    fig_vix.add_shape(type="rect", x0=lo, x1=hi, y0=0, y1=1,
        fillcolor=color, line_width=0, layer="below")
    fig_vix.add_annotation(x=(lo+hi)/2, y=0.5, text=f"<b>{label}</b>",
        showarrow=False, font=dict(size=9, color="#334155"))

fig_vix.add_shape(type="line", x0=vix_live, x1=vix_live, y0=-0.2, y1=1.2,
    line=dict(color="#0f1724", width=3))
fig_vix.add_annotation(x=vix_live, y=-0.35,
    text=f"<b>VIX {vix_live:.2f}</b>", showarrow=False, font=dict(size=13))

fig_vix.update_layout(
    height=115, margin=dict(t=15, b=40, l=10, r=10),
    paper_bgcolor="white", plot_bgcolor="white",
    xaxis=dict(range=[0, 60], showgrid=False, showticklabels=False),
    yaxis=dict(visible=False),
)
st.plotly_chart(fig_vix, use_container_width=True)

# ── IVP GAUGE ─────────────────────────────────────────────────────────────────
ivp = sig["ivp_1yr"]
fig_ivp = go.Figure()
ivp_zones = [(0,25,"#fee2e2","Avoid"),(25,35,"#fef3c7","Small"),(35,70,"#dcfce7","Ideal"),(70,80,"#fef3c7","High"),(80,100,"#ede9fe","Calendar")]
for lo, hi, color, label in ivp_zones:
    fig_ivp.add_shape(type="rect", x0=lo, x1=hi, y0=0, y1=1,
        fillcolor=color, line_width=0, layer="below")
    fig_ivp.add_annotation(x=(lo+hi)/2, y=0.5, text=f"<b>{label}</b>",
        showarrow=False, font=dict(size=9, color="#334155"))

fig_ivp.add_shape(type="line", x0=ivp, x1=ivp, y0=-0.2, y1=1.2,
    line=dict(color="#7c3aed", width=3))
fig_ivp.add_annotation(x=ivp, y=-0.35, text=f"<b>IVP {ivp:.0f}</b>",
    showarrow=False, font=dict(size=13, color="#7c3aed"))

fig_ivp.update_layout(
    height=115, margin=dict(t=10, b=40, l=10, r=10),
    paper_bgcolor="white", plot_bgcolor="white",
    xaxis=dict(range=[0, 100], showgrid=False, showticklabels=False),
    yaxis=dict(visible=False),
)
st.caption("IVP — 1-year Implied Volatility Percentile")
st.plotly_chart(fig_ivp, use_container_width=True)

st.divider()

# ── VIX HISTORY CHART ─────────────────────────────────────────────────────────
if not vix_hist.empty:
    vix_plot = vix_hist["close"].tail(252)
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Scatter(
        x=vix_plot.index, y=vix_plot.values,
        mode="lines", name="India VIX",
        line=dict(color="#d97706", width=1.5),
        fill="tozeroy", fillcolor="rgba(217,119,6,0.07)",
    ))
    for level, color, lbl in [(17,"#16a34a","Sweet spot"), (20,"#2563eb","Elevated"), (28,"#dc2626","Crisis")]:
        fig_hist.add_hline(y=level, line_dash="dot", line_color=color,
                           annotation_text=lbl, annotation_position="right")

    fig_hist.update_layout(
        height=260, paper_bgcolor="white", plot_bgcolor="#f8f9fb",
        margin=dict(t=20, b=20), title="India VIX — 1 Year",
    )
    st.plotly_chart(fig_hist, use_container_width=True)

# ── SIZING TABLE ──────────────────────────────────────────────────────────────
st.subheader("Position Size by VIX Zone + IVP")
import pandas as pd
sizing_data = [
    ("Complacent <11",  "Any",    "0%",   "Dangerous calm — avoid"),
    ("Low-Normal 11–17","<25",    "40%",  "Thin premiums — small IC only ◀ NOW" if vix_live < 17 else ""),
    ("Low-Normal 11–17","25–35",  "60%",  "Marginal — tradeable with care"),
    ("Sweet Spot 17–20","≥35",    "100%", "Ideal IC regime ← target this"),
    ("Elevated 20–28",  "≥35",    "80%",  "Wider wings required"),
    ("Crisis 28–40",    "Any",    "0%",   "No short premium — exit IC"),
    ("Extreme >40",     "Any",    "0%",   "Long vol only — hard kill"),
]
df_s = pd.DataFrame(sizing_data, columns=["VIX Zone","IVP","Size","Notes"])
st.dataframe(df_s, use_container_width=True, hide_index=True)

st.metric("Current position size multiplier", f"{sig['size_multiplier']:.0%}")
