# pages/02_Nifty_EMA_Ribbon.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
import pandas as pd

from data.live_fetcher import get_nifty_spot, get_nifty_daily
from analytics.ema import EMAEngine
from config import MTF_EMA_PERIODS

st.set_page_config(page_title="P02 · Nifty EMA Ribbon", layout="wide")
st_autorefresh(interval=60_000, key="p02_refresh")

st.title("Page 02 — Nifty EMA Ribbon (EMAs vs EMAs)")
st.caption("Inter-EMA relationships · Compression / Expansion · Crossovers · Ribbon ordering for credit options")

spot = get_nifty_spot()
df   = get_nifty_daily()
eng  = EMAEngine()
sig  = eng.signals(df)

# ── METRICS ──────────────────────────────────────────────────────────────────
c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Ribbon State",     sig["ribbon_state"])
c2.metric("Ribbon Spread %",  f"{sig['ribbon_pct']:.2f}%")
c3.metric("Bull ordered pairs", f"{sig['bull_ordered_pairs']}/6")
c4.metric("Home Score",       f"{sig['home_score']}/6")
kills = sig.get("kill_switches", {})
c5.metric("Compression Kill", "🔴 YES" if kills.get("ribbon_compressed") else "✅ No")

st.divider()

# ── RIBBON CHART ─────────────────────────────────────────────────────────────
EMA_COLORS = {
    3: "#ef4444", 8: "#f97316", 16: "#eab308",
    30: "#22c55e", 60: "#06b6d4", 120: "#3b82f6", 200: "#7c3aed",
}

df_plot = eng.compute(df.copy()).tail(120)
fig = go.Figure()

# Price line
fig.add_trace(go.Scatter(
    x=df_plot.index, y=df_plot["close"],
    mode="lines", name="Nifty Close",
    line=dict(color="#0f1724", width=2),
))

for p, color in EMA_COLORS.items():
    col = f"ema_{p}"
    if col in df_plot.columns:
        fig.add_trace(go.Scatter(
            x=df_plot.index, y=df_plot[col],
            mode="lines", name=f"EMA{p} ({MTF_EMA_PERIODS[p]})",
            line=dict(color=color, width=1.2),
            fill="tonexty" if p == 200 else None,
            fillcolor=f"rgba(180,180,240,0.04)" if p == 200 else None,
        ))

fig.update_layout(
    height=460, paper_bgcolor="white", plot_bgcolor="#f8f9fb",
    legend=dict(orientation="h", y=-0.18),
    margin=dict(t=20, b=20),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── CROSSOVER PAIRS TABLE ────────────────────────────────────────────────────
st.subheader("EMA Crossover Pair Status")
pairs = [
    (30, 60,  "1hr × 2hr",   "HIGHEST — weekly options"),
    (60, 120, "2hr × 4hr",   "VERY HIGH — structural"),
    (120, 200,"4hr × Daily", "HIGHEST — macro regime"),
    (16, 30,  "30min × 1hr", "HIGH — near-medium"),
    (8, 16,   "15min × 30min","MEDIUM — intraday"),
    (3, 8,    "5min × 15min", "LOWER — noise filter"),
]

ema_vals = sig["ema_values"]
rows = []
for shorter, longer, proxy_label, significance in pairs:
    vs = ema_vals.get(f"ema_{shorter}", 0)
    vl = ema_vals.get(f"ema_{longer}",  0)
    order  = "🟢 Bull (shorter > longer)" if vs > vl else "🔴 Bear (shorter < longer)"
    diff   = vs - vl
    rows.append({
        "Pair":         f"EMA{shorter} × EMA{longer}",
        "Proxies":      proxy_label,
        "Significance": significance,
        "Order":        order,
        "Diff (pts)":   round(diff, 0),
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.divider()

# ── RECENT CROSSOVERS ────────────────────────────────────────────────────────
st.subheader("Recent Crossover Events (last 5 sessions)")
crossovers = sig.get("crossovers", [])
if crossovers:
    for cx in crossovers:
        icon = "🟢" if cx["type"] == "GOLDEN" else "🔴"
        st.markdown(
            f"{icon} **{cx['type']}** — EMA{cx['shorter']} × EMA{cx['longer']} "
            f"({cx['proxy_shorter']} × {cx['proxy_longer']}) · {cx['days_ago']} session(s) ago"
        )
else:
    st.info("No crossovers detected in last 5 sessions.")

# ── SLOPES TABLE ─────────────────────────────────────────────────────────────
with st.expander("EMA Slopes (1-day change)"):
    slopes = sig.get("slopes", {})
    slope_rows = [
        {"Period": p, "Proxy TF": MTF_EMA_PERIODS[p],
         "1d Slope": slopes.get(p, 0),
         "Direction": "↑" if slopes.get(p, 0) > 0 else "↓"}
        for p in [3, 8, 16, 30, 60, 120, 200]
    ]
    st.dataframe(pd.DataFrame(slope_rows), use_container_width=True, hide_index=True)

# ── RULES ────────────────────────────────────────────────────────────────────
with st.expander("Ribbon Rules for Credit Options"):
    st.markdown("""
**Bull fan (EMA3 > EMA8 > ... > EMA200):** Maximum PE conviction. No CE selling.

**Bear fan (EMA200 > ... > EMA3):** Maximum CE conviction. No PE selling.

**Compression <1%:** No new positions. Wait for direction to emerge.

**Key crossover — EMA30 × EMA60:** Highest significance for weekly options.
- Golden (1hr above 2hr): upgrade PE size to full.
- Death (1hr below 2hr): HARD WARNING — reduce PE 50%.

**EMA60 × EMA120 death cross:** Structural bear signal. Exit PE positions.
    """)
