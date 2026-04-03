# analytics/vix_iv_regime.py
# VIX / IV Volatility Regime Engine — Page 11
# India VIX zones, IVP, VRP, IV skew, term structure, kill switches.

import pandas as pd
import numpy as np
from analytics.base_strategy import BaseStrategy
from config import (
    VIX_COMPLACENT, VIX_LOW_NORMAL, VIX_SWEET_SPOT, VIX_ELEVATED, VIX_CRISIS,
    IVP_AVOID, IVP_SMALL, IVP_IDEAL_H, IVP_EXTREME, HV_PERIOD,
)

class VixIVRegimeEngine(BaseStrategy):
    """
    India VIX calibrated engine.
    NOT CBOE scale — India VIX structurally higher.
    """

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add realized vol (HV20) column to daily price DataFrame."""
        df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
        df["hv20"]    = df["log_ret"].rolling(HV_PERIOD).std() * np.sqrt(252) * 100
        return df

    # ─────────────────────────────────────────────────────────────────────────

    def signals(self, price_df: pd.DataFrame, vix_history: pd.DataFrame,
                current_vix: float, atm_iv: float) -> dict:
        """
        Parameters
        ----------
        price_df     : Nifty daily OHLCV (for HV20 calc)
        vix_history  : historical daily VIX closes (for IVP)
        current_vix  : live India VIX value
        atm_iv       : current ATM implied vol from options chain (%)
        """
        price_df  = self.compute(price_df.copy())
        hv20      = float(price_df["hv20"].iloc[-1]) if not price_df.empty else 0.0
        ivp_1yr   = self._ivp(current_vix, vix_history, lookback=252)
        ivp_5yr   = self._ivp(current_vix, vix_history, lookback=1260)
        vrp       = atm_iv - hv20
        vix_zone  = self._vix_zone(current_vix)
        ivp_zone  = self._ivp_zone(ivp_1yr)
        size_mult = self._size_multiplier(vix_zone, ivp_1yr)
        kills     = self._kill_switches(price_df, current_vix, vrp)
        home_score= self._home_score(current_vix, ivp_1yr, vrp, kills)

        return {
            "vix":           round(current_vix, 2),
            "vix_zone":      vix_zone,
            "vix_zone_num":  self._zone_number(vix_zone),
            "hv20":          round(hv20, 2),
            "atm_iv":        round(atm_iv, 2),
            "vrp":           round(vrp, 2),
            "vrp_positive":  vrp > 0,
            "ivp_1yr":       round(ivp_1yr, 0),
            "ivp_5yr":       round(ivp_5yr, 0),
            "ivp_zone":      ivp_zone,
            "size_multiplier": size_mult,
            "contango":      atm_iv > 0 and hv20 > 0,  # simplified term structure proxy
            "kill_switches": kills,
            "home_score":    home_score,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # IVP calculation

    def _ivp(self, current_vix: float, vix_history: pd.DataFrame,
             lookback: int = 252) -> float:
        """
        Implied Volatility Percentile.
        What % of the past N trading days had VIX below current level.
        """
        if vix_history.empty or "close" not in vix_history.columns:
            return 50.0
        hist = vix_history["close"].tail(lookback).dropna()
        if len(hist) == 0:
            return 50.0
        return round(float((hist < current_vix).mean() * 100), 1)

    # ─────────────────────────────────────────────────────────────────────────
    # VIX zone classification

    def _vix_zone(self, vix: float) -> str:
        if   vix < VIX_COMPLACENT:  return "COMPLACENT"
        elif vix < VIX_LOW_NORMAL:  return "LOW_NORMAL"
        elif vix < VIX_SWEET_SPOT:  return "SWEET_SPOT"
        elif vix < VIX_ELEVATED:    return "ELEVATED"
        elif vix < VIX_CRISIS:      return "CRISIS"
        else:                        return "EXTREME"

    def _zone_number(self, zone: str) -> int:
        return {
            "COMPLACENT": 1, "LOW_NORMAL": 2, "SWEET_SPOT": 3,
            "ELEVATED": 4,   "CRISIS": 5,     "EXTREME": 6,
        }.get(zone, 0)

    def _ivp_zone(self, ivp: float) -> str:
        if   ivp < IVP_AVOID:  return "AVOID"
        elif ivp < IVP_SMALL:  return "SMALL_SPREADS"
        elif ivp < IVP_IDEAL_H:return "IDEAL"
        elif ivp < IVP_EXTREME:return "HIGH"
        else:                   return "EXTREME_CALENDAR"

    # ─────────────────────────────────────────────────────────────────────────
    # Position size multiplier

    def _size_multiplier(self, vix_zone: str, ivp: float) -> float:
        if vix_zone in ("CRISIS", "EXTREME"):
            return 0.0
        if vix_zone == "COMPLACENT":
            return 0.0
        if vix_zone == "LOW_NORMAL" and ivp < IVP_AVOID:
            return 0.40
        if vix_zone == "LOW_NORMAL" and ivp < IVP_SMALL:
            return 0.60
        if vix_zone == "SWEET_SPOT" and ivp >= IVP_SMALL:
            return 1.00
        if vix_zone == "ELEVATED" and ivp >= IVP_SMALL:
            return 0.80
        return 0.50   # default cautious

    # ─────────────────────────────────────────────────────────────────────────
    # Kill switches

    def _kill_switches(self, price_df: pd.DataFrame,
                        vix: float, vrp: float) -> dict:
        # K1 — VIX single-day spike ≥30%
        K1 = False
        if "close" not in price_df.columns or len(price_df) < 2:
            pass
        else:
            # Approximate using VIX as-is; real implementation tracks VIX daily
            K1 = False  # computed externally with VIX history

        # K2 — VIX crosses above sweet spot boundary (20)
        K2 = vix > VIX_SWEET_SPOT

        # K3 — VIX rising 3 consecutive days while <17 (slow drift)
        K3 = False   # requires VIX time series — computed in page

        # K4 — VRP negative (ATM IV < HV20)
        K4 = vrp < 0

        # Hard sell kill: zones 5/6
        HARD_KILL = vix >= VIX_CRISIS

        return {
            "K1_vix_spike":   bool(K1),
            "K2_regime_shift":bool(K2),
            "K3_slow_drift":  bool(K3),
            "K4_vrp_negative":bool(K4),
            "HARD_KILL":      bool(HARD_KILL),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Home score (max 10)

    def _home_score(self, vix: float, ivp: float, vrp: float, kills: dict) -> int:
        if kills.get("HARD_KILL"):
            return 0
        score = 0
        # VIX in 12–20 zone: +4
        if 12 <= vix <= VIX_SWEET_SPOT:
            score += 4
        # IVP 25–70: +4
        if IVP_AVOID <= ivp <= IVP_IDEAL_H:
            score += 4
        # VRP positive: +2
        if vrp > 0:
            score += 2
        return min(score, 10)
