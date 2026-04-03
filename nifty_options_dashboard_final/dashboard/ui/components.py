# ui/components.py
# Shared Streamlit UI helpers used across all pages.
# Import as: import ui.components as ui

import streamlit as st


def metric_card(label: str, value: str, sub: str = "",
                color: str = "default") -> None:
    """Styled metric with optional sub-text and border color."""
    border = {
        "green": "#16a34a", "red": "#dc2626",
        "amber": "#d97706", "blue": "#2563eb",
    }.get(color, "#e2e6ef")
    bg = {
        "green": "#f0fdf4", "red": "#fef2f2",
        "amber": "#fffbeb", "blue": "#eff6ff",
    }.get(color, "#f8f9fb")

    st.markdown(
        f"<div style='border-top:3px solid {border};background:{bg};"
        f"border-radius:6px;padding:10px 13px;'>"
        f"<div style='font-size:9px;color:#5a6b8a;text-transform:uppercase;"
        f"letter-spacing:.6px;font-family:monospace;margin-bottom:3px;'>{label}</div>"
        f"<div style='font-size:17px;font-weight:700;color:#0f1724;'>{value}</div>"
        f"{'<div style=\"font-size:10px;color:#5a6b8a;font-family:monospace;\">' + sub + '</div>' if sub else ''}"
        f"</div>",
        unsafe_allow_html=True,
    )


def kill_switch_row(name: str, active: bool, detail: str = "") -> None:
    """Single kill switch status row."""
    icon  = "🔴" if active else "✅"
    label = "ACTIVE" if active else "Clear"
    st.markdown(
        f"{icon} **{name}** — {label}"
        + (f" — {detail}" if detail and active else ""),
    )


def alert_box(title: str, body: str, level: str = "info") -> None:
    """Styled alert with consistent colors."""
    colors = {
        "danger": ("#fef2f2", "#dc2626", "#fee2e2"),
        "warning":("#fffbeb", "#d97706", "#fef3c7"),
        "info":   ("#eff6ff", "#2563eb", "#dbeafe"),
        "success":("#f0fdf4", "#16a34a", "#dcfce7"),
    }
    bg, border, txt_bg = colors.get(level, colors["info"])
    st.markdown(
        f"<div style='background:{bg};border:1px solid {border};"
        f"border-left:4px solid {border};border-radius:6px;"
        f"padding:9px 13px;margin-bottom:6px;'>"
        f"<div style='font-size:11px;font-weight:700;color:#0f1724;margin-bottom:3px;'>{title}</div>"
        f"<div style='font-size:10px;color:#5a6b8a;font-family:monospace;line-height:1.5;'>{body}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def expiry_banner(expiry, dte: int, role: str, mult: float) -> None:
    """Dual-expiry banner for P10 / P10B."""
    is_far   = "trade" in role.lower()
    bg       = "#f0fdf4"  if is_far else "#eff6ff"
    border   = "#16a34a"  if is_far else "#2563eb"
    label_c  = "#16a34a"  if is_far else "#2563eb"

    st.markdown(
        f"<div style='background:{bg};border:1.5px solid {border};"
        f"border-radius:7px;padding:10px 15px;display:flex;"
        f"justify-content:space-between;align-items:center;margin-bottom:8px;'>"
        f"<div>"
        f"<div style='font-size:9px;font-family:monospace;font-weight:700;"
        f"color:{label_c};letter-spacing:.8px;text-transform:uppercase;'>{role}</div>"
        f"<div style='font-size:14px;font-weight:700;color:{label_c};"
        f"font-family:monospace;'>{expiry} · {dte} DTE</div>"
        f"</div>"
        f"<div style='text-align:right;'>"
        f"<div style='font-size:9px;color:#5a6b8a;font-family:monospace;'>Panic mult</div>"
        f"<div style='font-size:16px;font-weight:700;color:{label_c};'>{mult:.1f}×</div>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def net_score_chip(score: float) -> str:
    """Return HTML chip for net score with intensity-coded color."""
    s = int(round(score))
    styles = {
        6:  ("background:#14532d;color:#fff;",        f"+{s}"),
        5:  ("background:#14532d;color:#fff;",        f"+{s}"),
        4:  ("background:#166534;color:#fff;",        f"+{s}"),
        3:  ("background:#16a34a;color:#fff;",        f"+{s}"),
        2:  ("background:#4ade80;color:#14532d;",     f"+{s}"),
        1:  ("background:#bbf7d0;color:#14532d;",     f"+{s}"),
        0:  ("background:#f1f5f9;color:#5a6b8a;",      "0"),
        -1: ("background:#fee2e2;color:#7f1d1d;",      f"{s}"),
        -2: ("background:#fca5a5;color:#7f1d1d;",      f"{s}"),
        -3: ("background:#dc2626;color:#fff;",          f"{s}"),
        -4: ("background:#b91c1c;color:#fff;",          f"{s}"),
        -5: ("background:#7f1d1d;color:#fff;",          f"{s}"),
        -6: ("background:#7f1d1d;color:#fff;",          f"{s}"),
    }
    style, text = styles.get(max(-6, min(6, s)), ("background:#f1f5f9;color:#5a6b8a;", str(s)))
    return (
        f"<span style='{style}padding:2px 8px;border-radius:4px;"
        f"font-family:monospace;font-size:11px;font-weight:700;'>{text}</span>"
    )


def wall_dots(score: int, dominant_color: str = "#16a34a") -> str:
    """Return HTML wall strength dot visualization."""
    filled = min(max(score, 0), 10)
    dots   = "".join([
        f"<div style='width:8px;height:8px;border-radius:2px;"
        f"background:{dominant_color if i < filled else '#e2e6ef'};"
        f"display:inline-block;margin-right:1px;'></div>"
        for i in range(5)   # show 5 dots (2 pts each)
    ])
    return (
        f"<div style='display:flex;align-items:center;gap:2px;'>"
        f"{dots}"
        f"<span style='font-size:11px;font-weight:700;font-family:monospace;"
        f"margin-left:4px;color:{dominant_color};'>{score}</span>"
        f"</div>"
    )
