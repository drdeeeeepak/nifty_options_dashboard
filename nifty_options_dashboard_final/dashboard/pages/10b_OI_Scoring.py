# pages/10b_OI_Scoring.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd

from data.live_fetcher import get_nifty_spot, get_dual_expiry_chains
from analytics.oi_scoring import OIScoringEngine

st.set_page_config(page_title="P10B · OI Scoring", layout="wide")
st_autorefresh(interval=30_000, key="p10b_refresh")

st.title("Page 10B — OI Momentum Scoring Engine")
st.caption(
    "Dual expiry · Near = intelligence · Far = your trade · "
    "% OI change scores · DTE panic amplifier · Wall Strength 1–10"
)

spot   = get_nifty_spot()
chains = get_dual_expiry_chains(spot)
eng    = OIScoringEngine()

near_dte = chains["near_dte"]
far_dte  = chains["far_dte"]
near_exp = chains["near_expiry"]
far_exp  = chains["far_expiry"]

# ── DTE ZONE SUMMARY ─────────────────────────────────────────────────────────
c1, c2 = st.columns(2)
with c1:
    near_mult = eng.get_dte_multiplier(near_dte)
    zone_n    = eng.dte_zone(near_dte)
    st.info(
        f"**Near Expiry {near_exp} · {near_dte} DTE**\n\n"
        f"Zone: {zone_n} · Panic Multiplier: **{near_mult}×** · "
        f"Wall Modifier: {eng.get_wall_modifier(near_dte):+d}\n\n"
        f"*Intelligence layer — read walls and strikes here*"
    )
with c2:
    far_mult = eng.get_dte_multiplier(far_dte)
    zone_f   = eng.dte_zone(far_dte)
    st.success(
        f"**Far Expiry {far_exp} · {far_dte} DTE**\n\n"
        f"Zone: {zone_f} · Panic Multiplier: **{far_mult}×** · "
        f"Wall Modifier: {eng.get_wall_modifier(far_dte):+d}\n\n"
        f"*Your trade — IC position legs monitored here*"
    )

st.divider()

# ── COMPUTE SCORED CHAINS ─────────────────────────────────────────────────────
sig = eng.signals(
    chains["near"], chains["far"],
    near_dte, far_dte,
    near_exp, far_exp
)
near_scored = sig["near_scored"]
far_scored  = sig["far_scored"]

# ── DISPLAY COLUMNS ───────────────────────────────────────────────────────────
display_cols = [
    "pe_oi", "pe_pct_change", "pe_base", "pe_adj", "pe_wall",
    "ce_oi", "ce_pct_change", "ce_base", "ce_adj", "ce_wall",
    "net_score",
]

def style_net(val):
    try:
        v = float(val)
        if   v >=  4: return "background-color:#14532d;color:white;font-weight:700"
        elif v >=  2: return "background-color:#16a34a;color:white"
        elif v >=  1: return "background-color:#dcfce7;color:#14532d"
        elif v == 0:  return "background-color:#f1f5f9;color:#5a6b8a"
        elif v >= -1: return "background-color:#fee2e2;color:#7f1d1d"
        elif v >= -3: return "background-color:#dc2626;color:white"
        else:         return "background-color:#7f1d1d;color:white;font-weight:700"
    except:
        return ""

# ── NEAR EXPIRY TABLE ────────────────────────────────────────────────────────
st.subheader(f"Near Expiry — {near_exp} ({near_dte} DTE)")
if not near_scored.empty:
    show = [c for c in display_cols if c in near_scored.columns]
    st.dataframe(
        near_scored[show].style.applymap(style_net, subset=["net_score"]),
        use_container_width=True, height=350,
    )
else:
    st.warning("Near expiry chain not loaded.")

st.divider()

# ── FAR EXPIRY TABLE (YOUR POSITION) ─────────────────────────────────────────
st.subheader(f"Far Expiry — {far_exp} ({far_dte} DTE) ← YOUR IC POSITION")
if not far_scored.empty:
    show_far = display_cols + ["position_action"]
    show_far = [c for c in show_far if c in far_scored.columns]

    # Highlight CE and PE short strikes if set in session state
    ce_short = st.session_state.get("ce_short_strike", 0)
    pe_short = st.session_state.get("pe_short_strike", 0)

    def highlight_position(row):
        s = row.name
        if s == ce_short: return ["background-color:#fee2e2"] * len(row)
        if s == pe_short: return ["background-color:#dcfce7"] * len(row)
        return [""] * len(row)

    styled = far_scored[show_far].style
    styled = styled.applymap(style_net, subset=["net_score"])
    if ce_short or pe_short:
        styled = styled.apply(highlight_position, axis=1)

    st.dataframe(styled, use_container_width=True, height=350)
else:
    st.warning("Far expiry chain not loaded.")

# ── POSITION ENTRY ────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Your IC Position")
    ce_s = st.number_input("CE Short Strike", value=0, step=50)
    pe_s = st.number_input("PE Short Strike", value=0, step=50)
    if st.button("Set strikes"):
        st.session_state["ce_short_strike"] = ce_s
        st.session_state["pe_short_strike"] = pe_s

    # Convergence check
    if ce_s and pe_s and not near_scored.empty and not far_scored.empty:
        conv = eng.convergence_check(near_scored, far_scored, int(ce_s), int(pe_s))
        st.subheader("Convergence")
        st.metric("PE Near Wall",  f"{conv['pe_near_wall']}/10")
        st.metric("PE Far Wall",   f"{conv['pe_far_wall']}/10")
        st.metric("CE Near Wall",  f"{conv['ce_near_wall']}/10")
        st.metric("CE Far Wall",   f"{conv['ce_far_wall']}/10")
        st.metric("PE Dual Fortress", "✅" if conv["pe_dual_fortress"] else "⚠️")
        st.metric("CE Dual Fortress", "✅" if conv["ce_dual_fortress"] else "⚠️")

# ── SCORING REFERENCE ─────────────────────────────────────────────────────────
with st.expander("Scoring Rules Reference"):
    st.markdown("""
**PE Base Score** (support dynamics):
- > +50% → +3 (massive put writing)
- +25–50% → +2 · +10–25% → +1 · ±10% → 0 (noise)
- −10 to −20% → −1 × DTE mult · −20 to −35% → −2 × DTE mult · < −35% → −3 × DTE mult

**CE Base Score** (resistance dynamics):
- > +50% → −3 · +25–50% → −2 · +10–25% → −1 · ±10% → 0
- −10 to −20% → +1 × DTE mult · −20 to −35% → +2 × DTE mult · < −35% → +3 × DTE mult

**DTE Multiplier** (applies to unwinding signals only):
- DTE > 5 → 1.0× · DTE 3–5 → 1.5× · DTE 0–2 → 2.0×

**Wall Strength**:
- OI ratio <1.5 → base 3 · 1.5–2.5 → base 5 · >2.5 → base 8
- DTE >5 → +2 · DTE 3–5 → 0 · DTE 0–2 → −2
- Intraday >+15% → +2 · Intraday <0% → −3 · Capped 1–10
    """)
