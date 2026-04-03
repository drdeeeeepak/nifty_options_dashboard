# analytics/bollinger.py
# Bollinger Bands Options Engine — Page 09
# 5 regimes, 5 kill switches, strike formulas, mid-flight adjustments.

import pandas as pd
import numpy as np
from analytics.base_strategy import BaseStrategy
from config import (
    BB_PERIOD, BB_STD, BB_SQUEEZE, BB_NORMAL_L, BB_NORMAL_H, BB_EXPAND,
    OI_STRIKE_STEP,
)


class BollingerOptionsEngine(BaseStrategy):

    # ─────────────────────────────────────────────────────────────────────────

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        basis, upper, lower, bw_pct = self.bollinger(
            df["close"], BB_PERIOD, BB_STD
        )
        df["bb_basis"] = basis
        df["bb_upper"] = upper
        df["bb_lower"] = lower
        df["bb_bw"]    = bw_pct
        df["bb_pct_b"] = (df["close"] - lower) / (upper - lower)  # position within bands

        # Walk detection: consecutive closes at/beyond band
        df["walk_up_count"]   = (df["close"] >= df["bb_upper"]).astype(int)
        df["walk_down_count"] = (df["close"] <= df["bb_lower"]).astype(int)
        # Running count — reset when streak breaks
        for col in ("walk_up_count", "walk_down_count"):
            streak = []
            c = 0
            for v in df[col]:
                c = c + 1 if v else 0
                streak.append(c)
            df[col] = streak

        return df

    # ─────────────────────────────────────────────────────────────────────────

    def signals(self, df: pd.DataFrame) -> dict:
        df = self.compute(df.copy())
        r  = df.iloc[-1]

        spot   = r["close"]
        basis  = r["bb_basis"]
        upper  = r["bb_upper"]
        lower  = r["bb_lower"]
        bw_pct = r["bb_bw"]
        pct_b  = r["bb_pct_b"]
        walk_up   = int(r["walk_up_count"])
        walk_down = int(r["walk_down_count"])

        regime        = self._regime(spot, basis, upper, lower, bw_pct,
                                     walk_up, walk_down)
        ce_strike     = self._ce_strike(regime, upper, lower, basis)
        pe_strike     = self._pe_strike(regime, upper, lower, basis)
        kills         = self._kill_switches(df)
        adjustments   = self._mid_flight_adjustments(df)
        home_score    = self._home_score(regime, bw_pct, kills)

        return {
            "basis":          round(basis, 0),
            "upper":          round(upper, 0),
            "lower":          round(lower, 0),
            "bw_pct":         round(bw_pct, 2),
            "pct_b":          round(pct_b, 3),
            "spot":           round(spot, 0),
            "walk_up_count":  walk_up,
            "walk_down_count":walk_down,
            "regime":         regime,
            "ce_strike":      ce_strike,
            "pe_strike":      pe_strike,
            "adjustments":    adjustments,
            "kill_switches":  kills,
            "home_score":     home_score,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Regime classification

    def _regime(self, spot, basis, upper, lower, bw_pct,
                walk_up, walk_down) -> str:
        if bw_pct < BB_SQUEEZE:
            return "SQUEEZE"
        if walk_up >= 3:
            return "WALK_UPPER"
        if walk_down >= 3:
            return "WALK_LOWER"
        # Pierce + close back inside (mean reversion setup)
        # (handled via adjustments — just classify as neutral or MR)
        if abs(spot - basis) < 0.25 * (upper - lower):
            return "NEUTRAL_WALK"      # near basis
        return "NEUTRAL_WALK"

    # ─────────────────────────────────────────────────────────────────────────
    # Strike selection by regime

    def _ce_strike(self, regime: str, upper, lower, basis) -> int:
        half_band = (upper - basis)
        if regime == "SQUEEZE":
            return 0  # no trade
        elif regime == "WALK_UPPER":
            return self.round_strike(upper + 0.5 * half_band, direction="ceil")
        elif regime == "WALK_LOWER":
            return self.round_strike(basis, direction="ceil")
        else:  # NEUTRAL_WALK or MEAN_REVERT
            return self.round_strike(upper, direction="ceil")

    def _pe_strike(self, regime: str, upper, lower, basis) -> int:
        half_band = (basis - lower)
        if regime == "SQUEEZE":
            return 0
        elif regime == "WALK_UPPER":
            return self.round_strike(basis, direction="floor")
        elif regime == "WALK_LOWER":
            return self.round_strike(lower - 0.5 * half_band, direction="floor")
        else:
            return self.round_strike(lower, direction="floor")

    # ─────────────────────────────────────────────────────────────────────────
    # Kill switches

    def _kill_switches(self, df: pd.DataFrame) -> dict:
        if len(df) < 3:
            return {f"K{i}": False for i in range(1, 6)}

        r    = df.iloc[-1]
        prev = df.iloc[-2]

        # K1 — close beyond short strike (requires knowing position — flagged externally)
        # Represented as: close beyond upper or lower band
        K1_ce = r["close"] > r["bb_upper"]
        K1_pe = r["close"] < r["bb_lower"]
        K1 = K1_ce or K1_pe

        # K2 — BW explosion ≥40%
        if len(df) >= 10:
            entry_bw = df["bb_bw"].iloc[-10]  # approximate entry BW
            K2 = r["bb_bw"] > entry_bw * 1.40
        else:
            K2 = False

        # K3 — full candle body beyond band
        K3 = (
            (r["open"] > r["bb_upper"] and r["close"] > r["bb_upper"]) or
            (r["open"] < r["bb_lower"] and r["close"] < r["bb_lower"])
        )

        # K4 — basis cross against position (soft)
        K4_ce_holder = prev["close"] < prev["bb_basis"] and r["close"] > r["bb_basis"]
        K4_pe_holder = prev["close"] > prev["bb_basis"] and r["close"] < r["bb_basis"]
        K4 = K4_ce_holder or K4_pe_holder

        # K5 — walk streak breaks (soft)
        K5 = (
            (prev["walk_up_count"]   >= 3 and r["walk_up_count"]   == 0) or
            (prev["walk_down_count"] >= 3 and r["walk_down_count"] == 0)
        )

        return {
            "K1": bool(K1), "K1_ce": bool(K1_ce), "K1_pe": bool(K1_pe),
            "K2": bool(K2),
            "K3": bool(K3),
            "K4": bool(K4),
            "K5": bool(K5),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Mid-flight adjustments

    def _mid_flight_adjustments(self, df: pd.DataFrame) -> list[dict]:
        """
        Returns list of triggered mid-flight adjustment rules.
        In the dashboard, these show as actionable alerts.
        """
        if len(df) < 10:
            return []

        r    = df.iloc[-1]
        spot = r["close"]
        upper= r["bb_upper"]
        lower= r["bb_lower"]
        basis= r["bb_basis"]
        bw   = r["bb_bw"]
        entry_bw = df["bb_bw"].iloc[-10]

        alerts = []

        # A1 — band expansion warning CE (spot in top quartile + BW expanded 10%)
        if spot > (upper - 0.25 * (upper - lower)) and bw > entry_bw * 1.10:
            alerts.append({
                "leg": "CE", "code": "A1",
                "action": "Roll CE short up",
                "new_strike": self.round_strike(
                    upper + 0.25 * (upper - basis), direction="ceil"
                ),
            })

        # A2 — spot within 50pts of CE (proxy — within 15% of band width from top)
        if spot > (upper - 0.15 * (upper - lower)):
            alerts.append({
                "leg": "CE", "code": "A2",
                "action": "Hedge or roll CE — within 50pts of strike",
            })

        # B1 — band expansion warning PE
        if spot < (lower + 0.25 * (upper - lower)) and bw > entry_bw * 1.10:
            alerts.append({
                "leg": "PE", "code": "B1",
                "action": "Roll PE short down",
                "new_strike": self.round_strike(
                    lower - 0.25 * (basis - lower), direction="floor"
                ),
            })

        # B2 — spot within 50pts of PE
        if spot < (lower + 0.15 * (upper - lower)):
            alerts.append({
                "leg": "PE", "code": "B2",
                "action": "Hedge or roll PE — within 50pts of strike",
            })

        return alerts

    # ─────────────────────────────────────────────────────────────────────────
    # Home page score (max 15)

    def _home_score(self, regime: str, bw_pct: float, kills: dict) -> int:
        score = 0

        # Regime = Neutral or Mean Revert: +7
        if regime in ("NEUTRAL_WALK", "MEAN_REVERT"):
            score += 7

        # BW 4-7% (normal): +4
        if BB_NORMAL_L <= bw_pct <= BB_NORMAL_H:
            score += 4

        # No squeeze: +2
        if bw_pct >= BB_SQUEEZE:
            score += 2

        # No expansion: +2
        if bw_pct <= BB_EXPAND:
            score += 2

        # Hard kills wipe score
        if kills.get("K1") or kills.get("K2") or kills.get("K3"):
            return 0

        return min(score, 15)
