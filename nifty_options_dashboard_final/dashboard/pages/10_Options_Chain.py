# pages/10_Options_Chain.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
import pandas as pd

from data.live_fetcher import (
    get_nifty_spot, get_dual_expiry_chains, get_near_far_expiries
)
from analytics.options_chain import OptionsChainEngine
from analytics.oi_scoring    import OIScoringEngine

st.set_page_config(page_title="P10 · Options Chain", layout="wide")
st_autorefresh(interval=30_000, key="p10_refresh")

st.title("Page 10 — Options Chain Analysis Engine")
st.caption("Rules 1–20 · PCR · Max Pain · OI Walls · GEX · Migration · Tuesday expiry")

spot   = get_nifty_spot()
chains = get_dual_expiry_chains(spot)
oc_eng = OptionsChainEngine()
oi_eng = OIScoringEngine()

near_exp = chains["near_expiry"]
far_exp  = chains["far_expiry"]
near_dte = chains["near_dte"]
far_dte  = chains["far_dte"]

# ── EXPIRY SELECTOR ───────────────────────────────────────────────────────────
expiry_choice = st.radio(
    "Viewing expiry",
    [f"Near — {near_exp} ({near_dte} DTE) — Intelligence",
     f"Far  — {far_exp}  ({far_dte}  DTE) — YOUR TRADE"],
    horizontal=True,
)
is_near = "Near" in expiry_choice
df_chain = chains["near"] if is_near else chains["far"]
dte      = near_dte if is_near else far_dte
sig      = oc_eng.signals(df_chain, spot, dte)

# ── METRIC ROW ───────────────────────────────────────────────────────────────
c1,c2,c3,c4,c5,c6,c7 = st.columns(7)
c1.metric("Spot",       f"{spot:,.0f}")
c2.metric("PCR",        f"{sig.get('pcr', 0):.2f}")
c3.metric("Max Pain",   f"{sig.get('max_pain', 0):,.0f}")
c4.metric("Call Wall",  f"{sig.get('call_wall', 0):,.0f}")
c5.metric("Put Wall",   f"{sig.get('put_wall', 0):,.0f}")
gex = sig.get("gex", {})
c6.metric("GEX",        f"{gex.get('total_gex', 0):+,.0f}")
c7.metric("Strategy",   sig.get("strategy", "—"))

st.divider()

# ── OI CHAIN TABLE ────────────────────────────────────────────────────────────
st.subheader("OI Chain")
if not df_chain.empty:
    display = df_chain.copy()

    # Highlight important strikes
    def highlight_row(row):
        strike = row.name
        if strike == sig.get("call_wall"):
            return ["background-color: #fee2e2"] * len(row)
        if strike == sig.get("put_wall"):
            return ["background-color: #dcfce7"] * len(row)
        if strike == sig.get("max_pain"):
            return ["background-color: #fef3c7"] * len(row)
        if abs(strike - spot) <= 25:
            return ["background-color: #dbeafe"] * len(row)
        return [""] * len(row)

    cols_show = ["pe_oi", "pe_vol", "pe_ltp", "pe_iv", "pe_pct_change",
                 "ce_oi", "ce_vol", "ce_ltp", "ce_iv", "ce_pct_change"]
    cols_show = [c for c in cols_show if c in display.columns]

    st.dataframe(
        display[cols_show].style.apply(highlight_row, axis=1),
        use_container_width=True, height=400,
    )
    st.caption("🔴 Call Wall · 🟢 Put Wall · 🟡 Max Pain · 🔵 ATM")

st.divider()

# ── GEX DETAILS ───────────────────────────────────────────────────────────────
c1, c2 = st.columns(2)
with c1:
    st.subheader("GEX Summary")
    st.metric("GEX Regime",   gex.get("regime", "—"))
    st.metric("GEX Flip Level", f"{gex.get('flip_level', 0):,.0f}")
    st.metric("GEX Total",    f"{gex.get('total_gex', 0):+,.0f}")

with c2:
    st.subheader("Migration Status")
    mig = sig.get("migration", {})
    st.metric("Migration Detected", "YES 🔴" if mig.get("detected") else "NO ✅")
    st.metric("Direction", mig.get("direction") or "None")

st.divider()

# ── KILL SWITCHES ─────────────────────────────────────────────────────────────
st.subheader("Kill Switches")
kills = sig.get("kill_switches", {})
for k, v in kills.items():
    icon = "🔴 ACTIVE" if v else "✅ Clear"
    st.markdown(f"{icon} — **{k}**")

# ── RULES REFERENCE ───────────────────────────────────────────────────────────
with st.expander("20 Rules Reference"):
    st.markdown("""
| Rule | Signal | Action |
|------|--------|--------|
| R2 | Max Call OI = Call Wall | CE short anchor |
| R3 | Max Put OI = Put Wall | PE short anchor |
| R4 | Call vol weakness <75% put vol | Put dominance signal |
| R7 | Wall dist <1.2% | Range regime → IC |
| R8 | PCR 0.9–1.1 | Balanced → IC |
| R9 | Max pain near spot | Expiry pull direction |
| R13 | GEX positive | Dealer pinning → IC valid |
| R14 | GEX flip level | Break below = expand risk |
| R15 | GEX regime | POSITIVE_PINNING / NEGATIVE_EXPANSION |
| R16 | OI migration detected | Disable weakness rules |
| R19C | IC conditions met | IRON_CONDOR signal |
| R19D | Negative GEX or migration | NO_TRADE |
    """)
