# Home.py
# Streamlit entry point — Page 00: Command Center
# Run: streamlit run Home.py

import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Nifty Options Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Auto-refresh every 60 seconds ─────────────────────────────────────────────
st_autorefresh(interval=60_000, key="home_refresh")

# ── Imports ───────────────────────────────────────────────────────────────────
from data.live_fetcher import (
    get_nifty_spot, get_nifty_daily, get_top10_daily,
    get_india_vix, get_vix_history, get_dual_expiry_chains,
    get_near_far_expiries, get_dte,
)
from analytics.ema            import EMAEngine
from analytics.rsi_engine     import RSIEngine
from analytics.bollinger      import BollingerOptionsEngine
from analytics.options_chain  import OptionsChainEngine
from analytics.oi_scoring     import OIScoringEngine
from analytics.vix_iv_regime  import VixIVRegimeEngine
from analytics.market_profile import MarketProfileEngine
from analytics.home_engine    import HomeEngine
import ui.components as ui

# ── Load all data ─────────────────────────────────────────────────────────────
with st.spinner("Loading market data..."):
    spot         = get_nifty_spot()
    nifty_df     = get_nifty_daily()
    stock_dfs    = get_top10_daily()
    vix_live     = get_india_vix()
    vix_hist     = get_vix_history()
    chains       = get_dual_expiry_chains(spot)
    near_exp, far_exp = get_near_far_expiries()

# ── Compute all signals ───────────────────────────────────────────────────────
ema_eng = EMAEngine()
rsi_eng = RSIEngine()
bb_eng  = BollingerOptionsEngine()
oc_eng  = OptionsChainEngine()
oi_eng  = OIScoringEngine()
vix_eng = VixIVRegimeEngine()
mp_eng  = MarketProfileEngine()
home_eng= HomeEngine()

ema_sig     = ema_eng.signals(nifty_df)
breadth_sig = ema_eng.breadth_signals(stock_dfs)
rsi_sig     = rsi_eng.signals(nifty_df)
bb_sig      = bb_eng.signals(nifty_df)
oc_sig_near = oc_eng.signals(chains["near"], spot, chains["near_dte"])
oc_sig_far  = oc_eng.signals(chains["far"],  spot, chains["far_dte"])
oi_sig      = oi_eng.signals(
    chains["near"], chains["far"],
    chains["near_dte"], chains["far_dte"],
    near_exp, far_exp
)
atm_iv      = oc_sig_far.get("atm_iv", 11.4)
vix_sig     = vix_eng.signals(nifty_df, vix_hist, vix_live, atm_iv)
mp_sig      = mp_eng.signals(nifty_df, spot)

all_signals = {
    "ema":            ema_sig,
    "breadth":        breadth_sig,
    "rsi":            rsi_sig,
    "bollinger":      bb_sig,
    "options_chain":  oc_sig_far,   # FAR expiry for position management
    "vix_iv":         vix_sig,
    "market_profile": mp_sig,
}

home = home_eng.compute_score(all_signals)

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown("## 📊 Nifty Options Dashboard — Command Center")
col1, col2, col3, col4, col5, col6, col7, col8 = st.columns(8)
col1.metric("Nifty Spot",    f"{spot:,.0f}")
col2.metric("Score",         f"{home['total_score']}/100")
col3.metric("Verdict",       home["verdict"])
col4.metric("Effective Size",f"{home['effective_size']*100:.0f}%")
col5.metric("Kill Switches", "🔴 ACTIVE" if home["any_kill"] else "✅ Clear")
col6.metric("India VIX",     f"{vix_live:.2f}")
col7.metric("Near DTE",      chains["near_dte"])
col8.metric("Far DTE",       chains["far_dte"])

st.divider()

# ── MASTER VERDICT BANNER ────────────────────────────────────────────────────
verdict_color = {
    "KILL_VETO":    "🔴",
    "NO_TRADE":     "🔴",
    "WAIT":         "🟡",
    "TRADE_MINIMAL":"🟡",
    "TRADE_REDUCED":"🟢",
    "TRADE_FULL":   "🟢",
}.get(home["verdict"], "⚪")

st.markdown(f"""
<div style="background:#f0fdf4;border:2px solid #86efac;border-radius:10px;padding:16px 20px;margin-bottom:16px;">
  <h3 style="margin:0 0 8px;">{verdict_color} {home['strategy']} — {home['verdict']}</h3>
  <p style="margin:0;color:#5a6b8a;font-family:monospace;font-size:12px;">
    Score {home['total_score']}/100 · Base size {home['base_size']*100:.0f}% · 
    Breadth {home['breadth_count']}/10 → {home['breadth_mult']}× · 
    Effective {home['effective_size']*100:.0f}% · 
    {"⚠ KILL ACTIVE" if home['any_kill'] else "No kill switches"}
  </p>
</div>
""", unsafe_allow_html=True)

# ── SCORE BREAKDOWN ──────────────────────────────────────────────────────────
st.subheader("Weighted Score Breakdown")
cols = st.columns(7)
for i, (system, data) in enumerate(home["per_system"].items()):
    score = data["score"]
    max_  = data["max"]
    pct   = score / max_ if max_ > 0 else 0
    cols[i].metric(system.replace("_", " ").title(), f"{score}/{max_}")
    cols[i].progress(pct)

st.divider()

# ── OI SCORING PANEL (P10B) ──────────────────────────────────────────────────
st.subheader("📈 OI Momentum Scoring — Dual Expiry Position Health")
c1, c2 = st.columns(2)

with c1:
    st.markdown(f"**Near Expiry {near_exp} · {chains['near_dte']} DTE · Panic Mult {oi_eng.get_dte_multiplier(chains['near_dte'])}×**")
    near_scored = oi_sig["near_scored"]
    if not near_scored.empty:
        display_cols = ["pe_oi","pe_pct_change","pe_base","pe_wall",
                        "ce_oi","ce_pct_change","ce_base","ce_wall","net_score"]
        display_cols = [c for c in display_cols if c in near_scored.columns]
        st.dataframe(
            near_scored[display_cols].style.background_gradient(
                subset=["net_score"], cmap="RdYlGn", vmin=-6, vmax=6
            ),
            use_container_width=True
        )

with c2:
    st.markdown(f"**Far Expiry {far_exp} · {chains['far_dte']} DTE · Panic Mult {oi_eng.get_dte_multiplier(chains['far_dte'])}× ← YOUR TRADE**")
    far_scored = oi_sig["far_scored"]
    if not far_scored.empty:
        display_cols = ["pe_oi","pe_pct_change","pe_base","pe_wall",
                        "ce_oi","ce_pct_change","ce_base","ce_wall","net_score","position_action"]
        display_cols = [c for c in display_cols if c in far_scored.columns]
        st.dataframe(
            far_scored[display_cols].style.background_gradient(
                subset=["net_score"], cmap="RdYlGn", vmin=-6, vmax=6
            ),
            use_container_width=True
        )

st.divider()

# ── KILL SWITCHES + ALERTS ───────────────────────────────────────────────────
c1, c2 = st.columns(2)

with c1:
    st.subheader("Kill Switch Status")
    for system, sig in all_signals.items():
        kills = sig.get("kill_switches", {})
        for k, v in kills.items():
            icon = "🔴" if v else "✅"
            st.markdown(f"{icon} **{system}.{k}**")

with c2:
    st.subheader("Alert Feed")
    level_color = {1: "🔴", 2: "🟡", 3: "🔵", 4: "🟢"}
    for alert in home["alerts"]:
        icon = level_color.get(alert["level"], "⚪")
        with st.expander(f"{icon} {alert['title']}", expanded=alert["level"] <= 2):
            st.caption(alert["body"])

st.divider()

# ── PAGE STATUS GRID ─────────────────────────────────────────────────────────
st.subheader("All Pages Status")
pcols = st.columns(6)
page_statuses = [
    ("P01 EMA/Price",  ema_sig.get("ema_regime", "—"),       "green"),
    ("P09 Bollinger",  bb_sig.get("regime", "—"),            "amber"),
    ("P10 Options",    oc_sig_far.get("strategy", "—"),      "green"),
    ("P10B OI Score",  "Dual expiry live",                   "green"),
    ("P11 VIX/IV",     vix_sig.get("vix_zone", "—"),         "amber"),
    ("P12 Mkt Profile",mp_sig.get("nesting_state", "—"),     "green"),
]
for i, (label, value, color) in enumerate(page_statuses):
    pcols[i].metric(label, value)

# ── SCORING REFERENCE ─────────────────────────────────────────────────────────
with st.expander("Scoring System Reference"):
    import pandas as pd
    ref_data = {
        "Page":   ["P10","P12","P05–08","P09","P11","P01–02","P03–04"],
        "System": ["Options Chain","Market Profile","RSI Engine",
                   "Bollinger","VIX/IV","EMA Regime","Breadth"],
        "Max Pts":[25, 20, 20, 15, 10, 6, 4],
        "Current":[
            home["per_system"].get("options_chain",  {}).get("score", 0),
            home["per_system"].get("market_profile", {}).get("score", 0),
            home["per_system"].get("rsi",            {}).get("score", 0),
            home["per_system"].get("bollinger",      {}).get("score", 0),
            home["per_system"].get("vix_iv",         {}).get("score", 0),
            home["per_system"].get("ema",            {}).get("score", 0),
            home["per_system"].get("breadth",        {}).get("score", 0),
        ],
    }
    st.dataframe(pd.DataFrame(ref_data), use_container_width=True, hide_index=True)
