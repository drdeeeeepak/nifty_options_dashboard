# pages/12_Market_Profile.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import date

from data.live_fetcher import get_nifty_spot, get_nifty_daily
from analytics.market_profile import MarketProfileEngine

st.set_page_config(page_title="P12 · Market Profile", layout="wide")
st_autorefresh(interval=60_000, key="p12_refresh")

st.title("Page 12 — Market Profile Engine")
st.caption(
    "Wed→Tue expiry cycle · Weekly VA + Daily VA nesting · POC · "
    "Day type · Responsive vs initiative · 5 kill switches"
)

spot = get_nifty_spot()
df   = get_nifty_daily()
eng  = MarketProfileEngine()
sig  = eng.signals(df, spot)

# ── METRICS ──────────────────────────────────────────────────────────────────
c1,c2,c3,c4,c5,c6 = st.columns(6)
c1.metric("Weekly VAH",     f"{sig['weekly_vah']:,.0f}")
c2.metric("Weekly POC",     f"{sig['weekly_poc']:,.0f}")
c3.metric("Weekly VAL",     f"{sig['weekly_val']:,.0f}")
c4.metric("Market State",   sig["market_state"])
c5.metric("Day Type",       sig["day_type"])
c6.metric("Home Score",     f"{sig['home_score']}/20")

kills = sig["kill_switches"]
any_kill = any(kills.values())
if kills.get("MP_K1"):
    st.error("🔴 MP-K1: Price accepted outside Weekly VA 2+ sessions → Exit IC")
if kills.get("MP_K2"):
    st.error("🔴 MP-K2: Trend day confirmed → Exit IC at 1:30pm")
if kills.get("MP_K3"):
    st.warning("⚠️ MP-K3: Gap beyond VA unfilled → Reduce IC 50%")
if kills.get("MP_K4"):
    st.warning("⚠️ MP-K4: Weekly POC crossed → Monitor PE leg")

st.divider()

# ── PROFILE VISUAL ────────────────────────────────────────────────────────────
st.subheader("Weekly Value Area + Daily Nesting")

w_vah = sig["weekly_vah"]
w_val = sig["weekly_val"]
w_poc = sig["weekly_poc"]
d_vah = sig["daily_vah"]
d_val = sig["daily_val"]
d_poc = sig["daily_poc"]

fig_va = go.Figure()

# Weekly VA fill
fig_va.add_hrect(
    y0=w_val, y1=w_vah,
    fillcolor="rgba(37,99,235,0.07)",
    line_width=0, annotation_text="Weekly VA",
    annotation_position="top right",
)

# Daily VA fill
fig_va.add_hrect(
    y0=d_val, y1=d_vah,
    fillcolor="rgba(22,163,74,0.15)",
    line_width=0, annotation_text="Daily VA",
    annotation_position="top left",
)

# Weekly VAH / VAL / POC lines
for level, color, lbl, dash in [
    (w_vah, "#dc2626", f"W-VAH {w_vah:,.0f} (CE anchor)", "solid"),
    (w_poc, "#d97706", f"W-POC {w_poc:,.0f} (expiry pull)", "dot"),
    (w_val, "#16a34a", f"W-VAL {w_val:,.0f} (PE anchor)", "solid"),
    (d_vah, "#2563eb", f"D-VAH {d_vah:,.0f}", "dash"),
    (d_val, "#2563eb", f"D-VAL {d_val:,.0f}", "dash"),
    (spot,  "#0f1724", f"Spot {spot:,.0f}", "solid"),
]:
    fig_va.add_hline(
        y=level, line_color=color, line_dash=dash, line_width=2,
        annotation_text=lbl, annotation_position="right",
    )

# Price context bars (last 5 sessions)
df_recent = df.tail(7)
fig_va.add_trace(go.Bar(
    x=df_recent.index.strftime("%a %d"),
    y=df_recent["high"] - df_recent["low"],
    base=df_recent["low"],
    marker_color="rgba(37,99,235,0.3)",
    marker_line_color="rgba(37,99,235,0.6)",
    marker_line_width=1,
    name="Daily Range",
))

fig_va.update_layout(
    height=380, paper_bgcolor="white", plot_bgcolor="#f8f9fb",
    margin=dict(t=20, b=20),
    yaxis=dict(title="Price Level"),
)
st.plotly_chart(fig_va, use_container_width=True)

st.divider()

# ── NESTING STATE + STRATEGY ──────────────────────────────────────────────────
st.subheader("Nesting State → IC Strike Selection")

nesting = sig["nesting_state"]
ce_anchor = sig["ce_strike_anchor"]
pe_anchor = sig["pe_strike_anchor"]

NESTING_INFO = {
    "BALANCED": {
        "color": "#dcfce7", "border": "#16a34a",
        "desc": "Daily VA completely inside Weekly VA — maximum IC confidence.",
        "strategy": "Iron Condor at Weekly VAH (CE) and Weekly VAL (PE).",
        "home_pts": "20/20",
    },
    "BULL_VALUE_SHIFT": {
        "color": "#dbeafe", "border": "#2563eb",
        "desc": "Daily VA above Weekly VAH — bullish value shift in progress.",
        "strategy": "Bull Put Spread. Old Weekly VAH is now PE floor. CE very far OTM.",
        "home_pts": "18/20",
    },
    "BEAR_VALUE_SHIFT": {
        "color": "#fee2e2", "border": "#dc2626",
        "desc": "Daily VA below Weekly VAL — bearish value shift in progress.",
        "strategy": "Bear Call Spread. Old Weekly VAL is now CE ceiling. PE very far OTM.",
        "home_pts": "18/20",
    },
    "PARTIAL_OVERLAP": {
        "color": "#fef3c7", "border": "#d97706",
        "desc": "Daily VA partially overlaps weekly — transitional / uncertain.",
        "strategy": "Small IC. Reduce size 50%. Watch next session for direction.",
        "home_pts": "10/20",
    },
}

info = NESTING_INFO.get(nesting, {
    "color": "#f8f9fb", "border": "#e2e6ef",
    "desc": "Unknown state.", "strategy": "No trade.", "home_pts": "0/20",
})

st.markdown(
    f"<div style='background:{info['color']};border:1.5px solid {info['border']};"
    f"border-radius:8px;padding:14px 18px;margin-bottom:12px;'>"
    f"<h4 style='margin:0 0 6px;color:#0f1724;'>State: {nesting}</h4>"
    f"<p style='margin:0 0 4px;font-size:12px;color:#5a6b8a;font-family:monospace;'>{info['desc']}</p>"
    f"<p style='margin:0;font-size:12px;font-weight:600;'>{info['strategy']}</p>"
    f"<span style='font-size:11px;color:#5a6b8a;'>Home score: {info['home_pts']}</span>"
    f"</div>",
    unsafe_allow_html=True,
)

c1, c2 = st.columns(2)
c1.metric("CE Anchor Strike", f"{ce_anchor:,.0f}" if ce_anchor else "—",
          help="Weekly VAH rounded to nearest 50 (ceil)")
c2.metric("PE Anchor Strike", f"{pe_anchor:,.0f}" if pe_anchor else "—",
          help="Weekly VAL rounded to nearest 50 (floor)")

st.divider()

# ── EXPIRY CYCLE TIMELINE ─────────────────────────────────────────────────────
st.subheader("Wed → Tue Expiry Cycle")

today_dow = date.today().weekday()   # 0=Mon, 1=Tue, 2=Wed...
DAY_NAMES = ["Monday","Tuesday","Wednesday","Thursday","Friday","Monday","Tuesday"]
DAY_RULES = {
    2: ("Wed · Day 1 · 7 DTE",  "Observe only. VA not formed. Never enter on Wednesday."),
    3: ("Thu · Day 2 · 5 DTE ← PRIME", "PRIME IC entry. VA firming. OI concentrating at walls. Enter before 11am."),
    4: ("Fri · Day 3 · 4 DTE",  "Follow Thursday bias. If VA extended — follow. If nested — confirm IC."),
    0: ("Mon · Day 4 · 2 DTE",  "Weekend gap check. Re-run all systems. Adjust wings if gap outside VA."),
    1: ("Tue · EXPIRY",         "No new positions. Max pain pull toward POC. Manage existing for risk only."),
}

cols_cycle = st.columns(5)
day_order  = [2, 3, 4, 0, 1]   # Wed Thu Fri Mon Tue

for i, dow in enumerate(day_order):
    label, rule = DAY_RULES[dow]
    is_today = (today_dow == dow)
    border   = "2px solid #2563eb" if is_today else "1px solid #e2e6ef"
    bg       = "#eff6ff"           if is_today else "#f8f9fb"

    cols_cycle[i].markdown(
        f"<div style='background:{bg};border:{border};border-radius:7px;"
        f"padding:9px 10px;text-align:center;'>"
        f"<b style='font-size:11px;{'color:#2563eb;' if is_today else ''}'>{label}</b>"
        f"<br><span style='font-size:9px;color:#5a6b8a;font-family:monospace;'>{rule}</span>"
        f"{'<br><b style=\"color:#2563eb;font-size:9px;\">◀ TODAY</b>' if is_today else ''}"
        f"</div>",
        unsafe_allow_html=True,
    )

st.divider()

# ── RESPONSIVE vs INITIATIVE ──────────────────────────────────────────────────
st.subheader("Responsive vs Initiative Activity")

responsive = sig.get("responsive", True)

if responsive:
    st.success(
        "✅ **Responsive Activity Detected** — "
        "Price tested VA extreme and closed back inside. "
        "OTF traders defending the range. IC confirmed — full size."
    )
else:
    st.error(
        "🔴 **Initiative Activity** — "
        "Price accepted outside VA for 2+ sessions. "
        "OTF traders NOT defending the range. Exit IC immediately."
    )

st.caption(
    "**Two-TPO rule**: Wait 60 minutes (2 × 30min periods) after a VA breach "
    "before acting. First breach ≠ initiative. Confirmed acceptance = initiative."
)

st.divider()

# ── KILL SWITCHES ─────────────────────────────────────────────────────────────
st.subheader("Kill Switches")
for k, v in kills.items():
    icon = "🔴 ACTIVE" if v else "✅ Clear"
    st.markdown(f"{icon} — **{k}**")

with st.expander("Kill Switch Details"):
    st.markdown("""
| KS | Type | Trigger | Action |
|----|------|---------|--------|
| MP-K1 | **HARD** | Price closed outside Weekly VA for 2 consecutive sessions | Exit full IC at next open |
| MP-K2 | **HARD** | Trend day confirmed by 1:30pm (narrow IB + extended range) | Exit full IC at 1:30pm |
| MP-K3 | **HARD** | Monday gap beyond VA not filled in first 2 TPOs | Exit IC at 10:15am |
| MP-K4 | **SOFT** | Weekly POC crossed against position on daily close | Reduce leg 50% |
| MP-K5 | **SOFT** | Double distribution LVN within 50pts of short strike | Reduce IC 50% |
    """)
