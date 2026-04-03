# data/live_fetcher.py
# All Kite data fetching lives here. Analytics modules never call Kite directly.
# Caching: options=30s, price=60s, daily OHLCV=24hr.

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
import numpy as np
import streamlit as st

from config import (
    NIFTY_INDEX_TOKEN, TOP_10_TOKENS, TTL_OPTIONS, TTL_PRICE, TTL_DAILY,
    OI_STRIKE_STEP, OI_STRIKE_RANGE, EXPIRY_WEEKDAY
)

log = logging.getLogger(__name__)


# ─── Expiry helpers ───────────────────────────────────────────────────────────

def next_tuesday(from_date: Optional[date] = None) -> date:
    """Return the next Tuesday on or after from_date."""
    d = from_date or date.today()
    days_ahead = EXPIRY_WEEKDAY - d.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return d + timedelta(days=days_ahead)


def get_near_far_expiries() -> tuple[date, date]:
    """
    Near expiry = this week's Tuesday.
    Far expiry  = next week's Tuesday (your trade).
    """
    today = date.today()
    near = next_tuesday(today)
    far  = next_tuesday(near + timedelta(days=1))
    return near, far


def get_dte(expiry: date) -> int:
    """Days to expiry from today."""
    return max(0, (expiry - date.today()).days)


# ─── Nifty spot price ─────────────────────────────────────────────────────────

@st.cache_data(ttl=TTL_PRICE, show_spinner=False)
def get_nifty_spot() -> float:
    """Live Nifty 50 spot price."""
    from data.kite_client import get_kite
    kite = get_kite()
    try:
        quote = kite.quote([f"NSE:{NIFTY_INDEX_TOKEN}"])
        return float(quote[str(NIFTY_INDEX_TOKEN)]["last_price"])
    except Exception as e:
        log.error("Spot fetch failed: %s", e)
        return 0.0


# ─── Nifty daily OHLCV ───────────────────────────────────────────────────────

@st.cache_data(ttl=TTL_DAILY, show_spinner=False)
def get_nifty_daily(days: int = 400) -> pd.DataFrame:
    """
    Daily OHLCV for Nifty 50 index.
    Returns DataFrame with columns: date, open, high, low, close, volume.
    """
    from data.kite_client import get_kite
    kite = get_kite()
    try:
        to_date   = date.today()
        from_date = to_date - timedelta(days=days)
        data = kite.historical_data(
            NIFTY_INDEX_TOKEN,
            from_date.strftime("%Y-%m-%d"),
            to_date.strftime("%Y-%m-%d"),
            "day"
        )
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df[["open", "high", "low", "close", "volume"]]
    except Exception as e:
        log.error("Nifty daily fetch failed: %s", e)
        return pd.DataFrame()


# ─── Top 10 stocks daily OHLCV ───────────────────────────────────────────────

@st.cache_data(ttl=TTL_DAILY, show_spinner=False)
def get_top10_daily(days: int = 400) -> dict[str, pd.DataFrame]:
    """
    Daily OHLCV for each top 10 stock.
    Returns {symbol: DataFrame}.
    """
    from data.kite_client import get_kite
    kite = get_kite()
    result = {}
    to_date   = date.today()
    from_date = to_date - timedelta(days=days)
    for symbol, token in TOP_10_TOKENS.items():
        try:
            data = kite.historical_data(
                token,
                from_date.strftime("%Y-%m-%d"),
                to_date.strftime("%Y-%m-%d"),
                "day"
            )
            df = pd.DataFrame(data)
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            result[symbol] = df[["open", "high", "low", "close", "volume"]]
        except Exception as e:
            log.warning("Stock fetch failed %s: %s", symbol, e)
            result[symbol] = pd.DataFrame()
    return result


# ─── Options chain ────────────────────────────────────────────────────────────

@st.cache_data(ttl=TTL_OPTIONS, show_spinner=False)
def get_options_chain(expiry: date, spot: float) -> pd.DataFrame:
    """
    Fetch Nifty options chain for a given expiry date.
    Returns DataFrame with strikes ± OI_STRIKE_RANGE from spot.
    Columns: strike, ce_oi, ce_vol, ce_ltp, ce_iv, ce_oi_change,
                      pe_oi, pe_vol, pe_ltp, pe_iv, pe_oi_change
    """
    from data.kite_client import get_kite
    kite = get_kite()

    # Build ATM ± range strikes
    atm = round(spot / OI_STRIKE_STEP) * OI_STRIKE_STEP
    strikes = range(
        atm - OI_STRIKE_RANGE,
        atm + OI_STRIKE_RANGE + OI_STRIKE_STEP,
        OI_STRIKE_STEP
    )

    expiry_str = expiry.strftime("%d%b%Y").upper()  # e.g. "08APR2025"
    records = []

    for strike in strikes:
        ce_symbol = f"NFO:NIFTY{expiry_str}{strike}CE"
        pe_symbol = f"NFO:NIFTY{expiry_str}{strike}PE"
        try:
            data = kite.quote([ce_symbol, pe_symbol])
            ce   = data.get(ce_symbol, {})
            pe   = data.get(pe_symbol, {})
            records.append({
                "strike":      strike,
                "ce_oi":       ce.get("oi", 0),
                "ce_vol":      ce.get("volume", 0),
                "ce_ltp":      ce.get("last_price", 0),
                "ce_iv":       ce.get("implied_volatility", 0),
                "ce_oi_change":ce.get("oi_day_change", 0),
                "pe_oi":       pe.get("oi", 0),
                "pe_vol":      pe.get("volume", 0),
                "pe_ltp":      pe.get("last_price", 0),
                "pe_iv":       pe.get("implied_volatility", 0),
                "pe_oi_change":pe.get("oi_day_change", 0),
            })
        except Exception as e:
            log.warning("OI fetch failed strike %s: %s", strike, e)

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records).set_index("strike")

    # Compute % OI changes (avoid division by zero)
    prev_ce = df["ce_oi"] - df["ce_oi_change"]
    prev_pe = df["pe_oi"] - df["pe_oi_change"]
    df["ce_pct_change"] = np.where(
        prev_ce > 0, df["ce_oi_change"] / prev_ce * 100, 0.0
    )
    df["pe_pct_change"] = np.where(
        prev_pe > 0, df["pe_oi_change"] / prev_pe * 100, 0.0
    )
    return df


@st.cache_data(ttl=TTL_OPTIONS, show_spinner=False)
def get_dual_expiry_chains(spot: float) -> dict:
    """
    Fetch both near and far expiry chains in one call.
    Returns {"near": df, "far": df, "near_expiry": date, "far_expiry": date,
             "near_dte": int, "far_dte": int}
    """
    near_expiry, far_expiry = get_near_far_expiries()
    return {
        "near":        get_options_chain(near_expiry, spot),
        "far":         get_options_chain(far_expiry,  spot),
        "near_expiry": near_expiry,
        "far_expiry":  far_expiry,
        "near_dte":    get_dte(near_expiry),
        "far_dte":     get_dte(far_expiry),
    }


# ─── India VIX ───────────────────────────────────────────────────────────────

INDIA_VIX_TOKEN = 264969   # NSE:INDIA VIX

@st.cache_data(ttl=TTL_PRICE, show_spinner=False)
def get_india_vix() -> float:
    """India VIX live value."""
    from data.kite_client import get_kite
    kite = get_kite()
    try:
        quote = kite.quote([f"NSE:{INDIA_VIX_TOKEN}"])
        return float(quote[str(INDIA_VIX_TOKEN)]["last_price"])
    except Exception as e:
        log.error("VIX fetch failed: %s", e)
        return 0.0


@st.cache_data(ttl=TTL_DAILY, show_spinner=False)
def get_vix_history(days: int = 365) -> pd.DataFrame:
    """Historical India VIX for IVP calculation."""
    from data.kite_client import get_kite
    kite = get_kite()
    try:
        to_date   = date.today()
        from_date = to_date - timedelta(days=days)
        data = kite.historical_data(
            INDIA_VIX_TOKEN,
            from_date.strftime("%Y-%m-%d"),
            to_date.strftime("%Y-%m-%d"),
            "day"
        )
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date").sort_index()
    except Exception as e:
        log.error("VIX history failed: %s", e)
        return pd.DataFrame()


# ─── Nifty 500 breadth (for Geometric Edge health gate) ──────────────────────

@st.cache_data(ttl=TTL_DAILY, show_spinner=False)
def get_nifty500_breadth() -> int:
    """
    Count of Nifty 500 stocks trading above their 200-day SMA.
    Used as market health gate for Geometric Edge scanner.
    NOTE: This requires fetching all Nifty 500 instruments — expensive.
    Runs once daily via GitHub Actions and saves result to parquet.
    In live dashboard, reads from saved file instead.
    """
    import os, json
    breadth_file = "data/parquet/market_health.json"
    if os.path.exists(breadth_file):
        with open(breadth_file) as f:
            data = json.load(f)
            return data.get("breadth_count", 0)
    return 0   # fallback if not yet computed
