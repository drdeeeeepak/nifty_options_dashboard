# analytics/market_profile.py
# Market Profile Engine — Page 12
# Wed→Tue expiry cycle, VA, POC, TPO, value shift, day types, kill switches.

import pandas as pd
import numpy as np
from datetime import date, timedelta
from analytics.base_strategy import BaseStrategy


class MarketProfileEngine(BaseStrategy):
    """
    Market Profile using daily OHLCV as TPO proxy.
    Each daily candle = one TPO period.
    70% Value Area rule applied over Wed–Tue weekly cycle.
    """

    TPO_THRESHOLD    = 0.70   # 70% of TPOs define Value Area
    TREND_DAY_IB_PCT = 0.003  # IB < 0.3% of spot = narrow = trend day candidate
    DD_SEPARATION    = 0.005  # 0.5% gap between distributions = double distribution

    # ─────────────────────────────────────────────────────────────────────────

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """No additional columns needed — uses OHLCV directly."""
        return df

    # ─────────────────────────────────────────────────────────────────────────

    def signals(self, df: pd.DataFrame, spot: float) -> dict:
        """
        Compute weekly and daily Value Areas, POC, day type, nesting,
        kill switches and home score.
        """
        if df.empty:
            return self._empty_signals()

        weekly_va = self._weekly_value_area(df)
        daily_va  = self._daily_value_area(df)
        day_type  = self._day_type(df.iloc[-1], spot)
        nesting   = self._nesting_state(weekly_va, daily_va)
        poc_cross = self._poc_cross(df, weekly_va["poc"])
        responsive= self._responsive_activity(df, weekly_va)
        kills     = self._kill_switches(df, spot, weekly_va, nesting, day_type)
        home_score= self._home_score(nesting, kills, responsive)

        return {
            "weekly_vah":      weekly_va["vah"],
            "weekly_val":      weekly_va["val"],
            "weekly_poc":      weekly_va["poc"],
            "daily_vah":       daily_va["vah"],
            "daily_val":       daily_va["val"],
            "daily_poc":       daily_va["poc"],
            "nesting_state":   nesting,
            "day_type":        day_type,
            "responsive":      responsive,
            "poc_cross":       poc_cross,
            "market_state":    self._market_state(nesting),
            "kill_switches":   kills,
            "home_score":      home_score,
            "ce_strike_anchor":self.round_strike(weekly_va["vah"], direction="ceil"),
            "pe_strike_anchor":self.round_strike(weekly_va["val"], direction="floor"),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Value Area calculation

    def _value_area(self, df: pd.DataFrame) -> dict:
        """
        Compute POC and 70% Value Area from a window of daily candles.
        Uses price histogram (high-low range) as TPO proxy.
        """
        if df.empty:
            return {"poc": 0, "vah": 0, "val": 0}

        # Build price histogram
        step     = 50   # Nifty 50pt buckets
        low_all  = df["low"].min()
        high_all = df["high"].max()
        buckets  = np.arange(
            int(low_all // step) * step,
            int(high_all // step) * step + step * 2,
            step
        )

        hist = pd.Series(0.0, index=buckets)
        for _, row in df.iterrows():
            # Each candle contributes TPOs to buckets it spans
            lo = int(row["low"]  // step) * step
            hi = int(row["high"] // step) * step + step
            for b in range(lo, hi, step):
                if b in hist.index:
                    hist[b] += 1

        if hist.sum() == 0:
            mid = int((low_all + high_all) / 2 // step) * step
            return {"poc": mid, "vah": mid + step, "val": mid - step}

        poc = int(hist.idxmax())
        total_tpo = hist.sum()
        target    = total_tpo * self.TPO_THRESHOLD

        # Expand from POC outward to capture 70% of TPOs
        included  = hist[poc]
        above_idx = poc + step
        below_idx = poc - step

        while included < target:
            above_val = hist.get(above_idx, 0)
            below_val = hist.get(below_idx, 0)
            if above_val == 0 and below_val == 0:
                break
            if above_val >= below_val:
                included  += above_val
                above_idx += step
            else:
                included  += below_val
                below_idx -= step

        vah = above_idx - step
        val = below_idx + step
        return {"poc": poc, "vah": max(poc, vah), "val": min(poc, val)}

    def _weekly_value_area(self, df: pd.DataFrame) -> dict:
        """Last 5 trading days (Wed–Tue cycle)."""
        return self._value_area(df.tail(5))

    def _daily_value_area(self, df: pd.DataFrame) -> dict:
        """Last trading day only."""
        return self._value_area(df.tail(1))

    # ─────────────────────────────────────────────────────────────────────────
    # Nesting state

    def _nesting_state(self, weekly_va: dict, daily_va: dict) -> str:
        """
        BALANCED:    daily VA inside weekly VA (IC optimal)
        BULL_SHIFT:  daily VA above weekly VAH
        BEAR_SHIFT:  daily VA below weekly VAL
        DEEP_BALANCE:multi-week overlap (not computed here — approximated)
        """
        if daily_va["val"] > weekly_va["vah"]:
            return "BULL_VALUE_SHIFT"
        if daily_va["vah"] < weekly_va["val"]:
            return "BEAR_VALUE_SHIFT"
        if (daily_va["val"] >= weekly_va["val"] and
                daily_va["vah"] <= weekly_va["vah"]):
            return "BALANCED"
        return "PARTIAL_OVERLAP"

    def _market_state(self, nesting: str) -> str:
        return {
            "BALANCED":          "Balanced",
            "BULL_VALUE_SHIFT":  "Bullish value shift",
            "BEAR_VALUE_SHIFT":  "Bearish value shift",
            "PARTIAL_OVERLAP":   "Partial overlap",
        }.get(nesting, "Unknown")

    # ─────────────────────────────────────────────────────────────────────────
    # Day type

    def _day_type(self, today_row: pd.Series, spot: float) -> str:
        """
        Classify today's candle type.
        Uses IB (initial balance = first hour = approx open-to-close of first candle).
        """
        if today_row.empty:
            return "UNKNOWN"

        day_range = today_row["high"] - today_row["low"]
        ib_pct    = day_range / spot if spot > 0 else 0

        body = abs(today_row["close"] - today_row["open"])
        upper_wick = today_row["high"] - max(today_row["open"], today_row["close"])
        lower_wick = min(today_row["open"], today_row["close"]) - today_row["low"]

        # Trend day: narrow IB relative to day range, strong directional close
        if ib_pct < self.TREND_DAY_IB_PCT and body > 0.6 * day_range:
            return "TREND_DAY"

        # P-shape: close in upper quartile of range
        pct_b = (today_row["close"] - today_row["low"]) / max(day_range, 1)
        if pct_b > 0.75 and upper_wick < 0.15 * day_range:
            return "NORMAL_VAR_UP"
        if pct_b < 0.25 and lower_wick < 0.15 * day_range:
            return "NORMAL_VAR_DOWN"

        return "NORMAL"

    # ─────────────────────────────────────────────────────────────────────────
    # POC cross

    def _poc_cross(self, df: pd.DataFrame, poc: float) -> dict:
        if len(df) < 2:
            return {"crossed": False, "direction": None}
        prev_close = df["close"].iloc[-2]
        curr_close = df["close"].iloc[-1]
        crossed_up   = prev_close < poc <= curr_close
        crossed_down = prev_close > poc >= curr_close
        return {
            "crossed":   crossed_up or crossed_down,
            "direction": "UP" if crossed_up else "DOWN" if crossed_down else None,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Responsive vs initiative (simplified)

    def _responsive_activity(self, df: pd.DataFrame, weekly_va: dict) -> bool:
        """
        Responsive: price tested VAH or VAL and closed back inside VA.
        True = OTF traders defending the range (IC confirmed).
        """
        if df.empty:
            return True
        last = df.iloc[-1]
        tested_top    = last["high"] >= weekly_va["vah"]
        tested_bottom = last["low"]  <= weekly_va["val"]
        closed_inside = weekly_va["val"] <= last["close"] <= weekly_va["vah"]
        return (tested_top or tested_bottom) and closed_inside

    # ─────────────────────────────────────────────────────────────────────────
    # Kill switches

    def _kill_switches(self, df, spot, weekly_va, nesting, day_type) -> dict:
        r = df.iloc[-1] if not df.empty else pd.Series()

        # MP-K1: weekly VA breach + 2 TPO acceptance
        # Proxy: close outside VA for this and previous day
        K1 = False
        if len(df) >= 2:
            prev_close = df["close"].iloc[-2]
            curr_close = df["close"].iloc[-1]
            K1 = (
                (prev_close > weekly_va["vah"] and curr_close > weekly_va["vah"]) or
                (prev_close < weekly_va["val"] and curr_close < weekly_va["val"])
            )

        # MP-K2: trend day confirmed
        K2 = day_type == "TREND_DAY"

        # MP-K3: gap beyond VA (Monday gap check)
        K3 = nesting in ("BULL_VALUE_SHIFT", "BEAR_VALUE_SHIFT")

        # MP-K4: weekly POC cross (soft)
        K4 = self._poc_cross(df, weekly_va["poc"])["crossed"]

        # MP-K5: LVN near strike — approximated as partial overlap
        K5 = nesting == "PARTIAL_OVERLAP"

        return {
            "MP_K1": bool(K1),
            "MP_K2": bool(K2),
            "MP_K3": bool(K3),
            "MP_K4": bool(K4),
            "MP_K5": bool(K5),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Home score (max 20)

    def _home_score(self, nesting: str, kills: dict, responsive: bool) -> int:
        if kills.get("MP_K1") or kills.get("MP_K2"):
            return 0

        score = 0
        if nesting == "BALANCED":      score += 8
        elif nesting == "PARTIAL_OVERLAP": score += 4

        if nesting in ("BALANCED", "PARTIAL_OVERLAP"):
            score += 6   # daily inside weekly VA

        if not any(kills.values()):
            score += 4   # no kill switches

        if responsive:
            score += 2   # responsive activity bonus

        return min(score, 20)

    def _empty_signals(self) -> dict:
        return {
            "weekly_vah": 0, "weekly_val": 0, "weekly_poc": 0,
            "daily_vah": 0,  "daily_val": 0,  "daily_poc": 0,
            "nesting_state": "UNKNOWN", "day_type": "UNKNOWN",
            "responsive": False, "market_state": "Unknown",
            "kill_switches": {}, "home_score": 0,
            "ce_strike_anchor": 0, "pe_strike_anchor": 0,
        }
