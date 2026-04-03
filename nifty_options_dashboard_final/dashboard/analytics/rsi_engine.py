# analytics/rsi_engine.py
# RSI Momentum & Regime Engine — Pages 05, 06, 07, 08
# Weekly RSI = regime context. Daily RSI = execution timing.

import pandas as pd
import numpy as np
from analytics.base_strategy import BaseStrategy
from config import (
    RSI_PERIOD,
    W_RSI_CAPIT, W_RSI_BEAR_MAX, W_RSI_BEAR_TRANS, W_RSI_NEUTRAL_MID,
    W_RSI_BULL_TRANS, W_RSI_BULL_MIN, W_RSI_EXHAUST,
    D_RSI_CAPIT, D_RSI_BEAR_P, D_RSI_BAL_LOW, D_RSI_BAL_HIGH,
    D_RSI_BULL_P, D_RSI_EXHAUST,
    RSI_KS_W_FLIP_BULL, RSI_KS_W_FLIP_BEAR,
)

class RSIEngine(BaseStrategy):
    """
    14-period RSI.
    Weekly RSI: regime identification (primary context).
    Daily RSI:  execution timing (entry / exit).
    """

    # ─────────────────────────────────────────────────────────────────────────

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add rsi_daily and rsi_weekly columns."""
        # Daily RSI
        df["rsi_daily"] = self.rsi(df["close"], RSI_PERIOD)

        # Weekly RSI: resample close to weekly, compute RSI, forward-fill
        weekly_close = df["close"].resample("W-TUE").last()
        weekly_rsi   = self.rsi(weekly_close, RSI_PERIOD)
        df["rsi_weekly"] = weekly_rsi.reindex(df.index, method="ffill")

        # Slopes
        df["d_slope_1d"] = df["rsi_daily"].diff(1)
        df["d_slope_2d"] = df["rsi_daily"].diff(2)
        df["w_slope_1w"] = df["rsi_weekly"].diff(5)   # 5 trading days ≈ 1 week

        return df

    # ─────────────────────────────────────────────────────────────────────────

    def signals(self, df: pd.DataFrame) -> dict:
        """
        Core output dict consumed by home page and RSI pages.
        """
        df   = self.compute(df.copy())
        r    = df.iloc[-1]
        prev = df.iloc[-2]

        w_rsi     = round(r["rsi_weekly"],  1)
        d_rsi     = round(r["rsi_daily"],   1)
        d_slope1  = round(r["d_slope_1d"],  2)
        d_slope2  = round(r["d_slope_2d"],  2)
        w_slope   = round(r["w_slope_1w"],  2)

        w_regime      = self._weekly_regime(w_rsi)
        d_zone        = self._daily_zone(d_rsi)
        alignment     = self._alignment(w_regime, d_zone)
        phase         = self._classify_phase(d_rsi, d_slope1, d_slope2)
        divergence    = self._detect_divergence(df)
        range_shift   = self._range_shift_status(df)
        kills         = self._kill_switches(df)
        home_score    = self._home_score(w_rsi, d_rsi, d_slope1, alignment, divergence, kills)

        return {
            "rsi_daily":          d_rsi,
            "rsi_weekly":         w_rsi,
            "d_slope_1d":         d_slope1,
            "d_slope_2d":         d_slope2,
            "w_slope_1w":         w_slope,
            "w_regime":           w_regime,
            "d_zone":             d_zone,
            "alignment":          alignment,
            "momentum_phase":     phase,
            "divergence":         divergence,
            "range_shift":        range_shift,
            "momentum_state":     self._momentum_state(w_regime, d_zone),
            "strength":           self._strength(d_rsi, d_slope1, d_slope2),
            "expected_behavior":  self._expected_behavior(w_regime, d_zone, kills),
            "entry_timing":       self._entry_timing(phase, d_rsi),
            "position_size_pct":  self._position_size(phase, alignment),
            "kill_switches":      kills,
            "home_score":         home_score,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Weekly RSI regime

    def _weekly_regime(self, w: float) -> str:
        if   w < W_RSI_CAPIT:       return "W_CAPIT"
        elif w < W_RSI_BEAR_MAX:    return "W_BEAR"
        elif w < W_RSI_BEAR_TRANS:  return "W_BEAR_TRANS"
        elif w < W_RSI_BULL_TRANS:  return "W_NEUTRAL"
        elif w < W_RSI_BULL_MIN:    return "W_BULL_TRANS"
        elif w < W_RSI_EXHAUST:     return "W_BULL"
        else:                       return "W_BULL_EXH"

    # ─────────────────────────────────────────────────────────────────────────
    # Daily RSI zone

    def _daily_zone(self, d: float) -> str:
        if   d < D_RSI_CAPIT:   return "D_CAPIT"
        elif d < D_RSI_BEAR_P:  return "D_BEAR_PRESSURE"
        elif d < D_RSI_BAL_HIGH:return "D_BALANCE"
        elif d < D_RSI_BULL_P:  return "D_BULL_PRESSURE"
        elif d < D_RSI_EXHAUST: return "D_BULL_PRESSURE_PLUS"
        else:                   return "D_EXHAUST"

    # ─────────────────────────────────────────────────────────────────────────
    # MTF alignment

    def _alignment(self, w_regime: str, d_zone: str) -> str:
        bull_w = w_regime in ("W_NEUTRAL", "W_BULL_TRANS", "W_BULL", "W_BULL_EXH")
        bull_d = d_zone in ("D_BALANCE", "D_BULL_PRESSURE", "D_BULL_PRESSURE_PLUS")
        bear_w = w_regime in ("W_CAPIT", "W_BEAR", "W_BEAR_TRANS")
        bear_d = d_zone in ("D_CAPIT", "D_BEAR_PRESSURE")

        if bull_w and bull_d:  return "ALIGNED_BULL"
        if bear_w and bear_d:  return "ALIGNED_BEAR"
        if bull_w and bear_d:  return "COUNTER_TRAP_BEAR"
        if bear_w and bull_d:  return "COUNTER_TRAP_BULL"
        return "MIXED"

    # ─────────────────────────────────────────────────────────────────────────
    # Momentum phase

    def _classify_phase(self, d_rsi: float, slope1: float, slope2: float) -> str:
        if d_rsi < D_RSI_BAL_HIGH and slope1 > 0 and slope1 >= (slope2 or 0) / 2:
            return "EXPANSION"
        elif d_rsi < D_RSI_EXHAUST and slope1 > 0:
            return "CONTINUATION"
        elif d_rsi >= D_RSI_EXHAUST or (slope1 < 0 and d_rsi > 60):
            return "EXHAUSTION"
        else:
            return "REVERSAL"

    # ─────────────────────────────────────────────────────────────────────────
    # Divergence detection

    def _detect_divergence(self, df: pd.DataFrame,
                           lookback: int = 20) -> dict:
        """
        Detect bullish and bearish divergence over last N candles.
        Returns {"bullish": bool, "bearish": bool, "details": str}.
        """
        if len(df) < lookback + 5:
            return {"bullish": False, "bearish": False, "details": "insufficient data"}

        recent = df.tail(lookback)

        # Bearish: price HH but RSI LH
        price_hh = recent["close"].iloc[-1] > recent["close"].max() * 0.98
        rsi_lh   = recent["rsi_daily"].iloc[-1] < recent["rsi_daily"].max() * 0.95
        bearish  = price_hh and rsi_lh and recent["rsi_daily"].iloc[-1] > 55

        # Bullish: price LL but RSI HL
        price_ll = recent["close"].iloc[-1] < recent["close"].min() * 1.02
        rsi_hl   = recent["rsi_daily"].iloc[-1] > recent["rsi_daily"].min() * 1.05
        bullish  = price_ll and rsi_hl and recent["rsi_daily"].iloc[-1] < 45

        detail = ""
        if bearish: detail = "Bearish divergence: price HH, RSI LH"
        elif bullish: detail = "Bullish divergence: price LL, RSI HL"

        return {"bullish": bullish, "bearish": bearish, "details": detail}

    # ─────────────────────────────────────────────────────────────────────────
    # Range shift

    def _range_shift_status(self, df: pd.DataFrame) -> dict:
        """
        Check if bullish range (weekly RSI held ≥45 for 2+ weeks) is active or failed.
        """
        if "rsi_weekly" not in df.columns or len(df) < 15:
            return {"bull_range": False, "range_failure": False}

        w = df["rsi_weekly"]
        held_above_45 = all(w.iloc[-10:] >= 45)   # ~2 weeks of trading days
        failed = (
            any(w.iloc[-15:-10] >= 45) and   # was holding
            w.iloc[-1] < 40                  # now broken
        )
        return {
            "bull_range":     held_above_45,
            "range_failure":  failed,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Kill switches

    def _kill_switches(self, df: pd.DataFrame) -> dict:
        if "rsi_daily" not in df.columns or len(df) < 3:
            return {f"K{i}": False for i in range(1, 6)}

        r    = df.iloc[-1]
        prev = df.iloc[-2]

        # K1 — weekly regime flip
        K1 = (
            (prev["rsi_weekly"] > 60 and r["rsi_weekly"] < RSI_KS_W_FLIP_BULL) or
            (prev["rsi_weekly"] < 40 and r["rsi_weekly"] > RSI_KS_W_FLIP_BEAR)
        )

        # K2 — daily zone skip (bypass balance zone)
        K2 = (
            (prev["rsi_daily"] >= D_RSI_BAL_HIGH and r["rsi_daily"] < D_RSI_BAL_LOW) or
            (prev["rsi_daily"] <= D_RSI_BAL_LOW  and r["rsi_daily"] > D_RSI_BAL_HIGH)
        )

        # K3 — dual exhaustion
        K3 = (
            (r["rsi_weekly"] > W_RSI_EXHAUST and r["rsi_daily"] > D_RSI_EXHAUST) or
            (r["rsi_weekly"] < W_RSI_CAPIT   and r["rsi_daily"] < D_RSI_CAPIT)
        )

        # K4 — range shift failure (soft)
        rs = self._range_shift_status(df)
        K4 = rs["range_failure"]

        # K5 — slope sign change at exhaustion (soft)
        K5 = (
            r["rsi_daily"] > D_RSI_EXHAUST and r["d_slope_1d"] < 0
        )

        return {"K1": bool(K1), "K2": bool(K2), "K3": bool(K3),
                "K4": bool(K4), "K5": bool(K5)}

    # ─────────────────────────────────────────────────────────────────────────
    # Home page score contribution (max 20 pts)

    def _home_score(self, w_rsi, d_rsi, slope1, alignment, divergence, kills) -> int:
        score = 0
        # W+D aligned: +8
        if alignment in ("ALIGNED_BULL", "ALIGNED_BEAR"):
            score += 8
        # Phase 1 or 2 (not exhaustion): +5
        phase = self._classify_phase(d_rsi, slope1, 0)
        if phase in ("EXPANSION", "CONTINUATION"):
            score += 5
        # No divergence: +4
        if not divergence["bullish"] and not divergence["bearish"]:
            score += 4
        # Slope positive (trending): +3
        if slope1 > 0:
            score += 3
        # Deduct for active hard kills
        if kills.get("K1") or kills.get("K2") or kills.get("K3"):
            score = 0  # any hard kill wipes RSI contribution
        return min(score, 20)

    # ─────────────────────────────────────────────────────────────────────────
    # Descriptive outputs

    def _momentum_state(self, w_regime: str, d_zone: str) -> str:
        if w_regime in ("W_BULL", "W_BULL_EXH") and d_zone in ("D_BULL_PRESSURE", "D_BULL_PRESSURE_PLUS"):
            return "Bullish"
        if w_regime in ("W_BEAR", "W_CAPIT") and d_zone in ("D_BEAR_PRESSURE", "D_CAPIT"):
            return "Bearish"
        return "Neutral"

    def _strength(self, d_rsi: float, slope1: float, slope2: float) -> str:
        accel = slope1 > 0 and (slope2 or 0) > 0 and slope1 >= slope2
        if accel and d_rsi > 54:      return "Strong"
        if slope1 > 0 and d_rsi > 46: return "Moderate"
        return "Weak"

    def _expected_behavior(self, w_regime: str, d_zone: str, kills: dict) -> str:
        if any(kills.values()):
            return "Reversal"
        if w_regime in ("W_BULL", "W_BULL_TRANS") and d_zone in ("D_BALANCE",):
            return "Continuation"
        if d_zone == "D_EXHAUST":
            return "Reversal"
        if "COUNTER" in self._alignment(w_regime, d_zone):
            return "Pullback"
        return "Chop"

    def _entry_timing(self, phase: str, d_rsi: float) -> str:
        if phase == "EXPANSION":              return "Early"
        if phase == "CONTINUATION":           return "Mid"
        if phase in ("EXHAUSTION", "REVERSAL"): return "Late"
        return "Unknown"

    def _position_size(self, phase: str, alignment: str) -> float:
        if "COUNTER" in alignment:            return 0.0
        if phase == "EXPANSION":              return 1.00
        if phase == "CONTINUATION":           return 0.75
        if phase == "EXHAUSTION":             return 0.50
        return 0.25

    # ─────────────────────────────────────────────────────────────────────────
    # Stock-level signals (Pages 07, 08)

    def stock_signals(self, stock_dfs: dict[str, pd.DataFrame]) -> dict:
        """
        Compute RSI signals for each of the top 10 stocks.
        Returns per_stock dict + sector rotation signal.
        """
        per_stock = {}
        banks = ["HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK"]
        it    = ["INFY", "TCS"]

        for sym, df in stock_dfs.items():
            if df.empty:
                continue
            try:
                sig = self.signals(df)
                per_stock[sym] = {
                    "w_rsi":    sig["rsi_weekly"],
                    "d_rsi":    sig["rsi_daily"],
                    "w_regime": sig["w_regime"],
                    "d_zone":   sig["d_zone"],
                    "w_slope":  sig["w_slope_1w"],
                    "d_slope":  sig["d_slope_1d"],
                    "alignment":sig["alignment"],
                }
            except Exception:
                pass

        # Sector rotation: banks weekly bull + IT weekly bear
        banks_bull = sum(
            1 for b in banks
            if per_stock.get(b, {}).get("w_regime") in
               ("W_BULL_TRANS", "W_BULL", "W_BULL_EXH")
        )
        it_bear = sum(
            1 for t in it
            if per_stock.get(t, {}).get("w_regime") in
               ("W_BEAR", "W_CAPIT", "W_BEAR_TRANS")
        )
        rotation = banks_bull >= 2 and it_bear >= 1

        # Heavy drag: 2+ stocks weight>8% with weekly RSI <40
        heavy_stocks = ["HDFCBANK", "RELIANCE", "ICICIBANK"]
        heavy_drag = sum(
            1 for s in heavy_stocks
            if per_stock.get(s, {}).get("w_rsi", 50) < 40
        ) >= 2

        avg_w_rsi = np.mean([
            v["w_rsi"] for v in per_stock.values() if "w_rsi" in v
        ]) if per_stock else 50.0

        return {
            "per_stock":      per_stock,
            "rotation_signal": rotation,
            "heavy_drag":      heavy_drag,
            "avg_w_rsi":       round(avg_w_rsi, 1),
            "kill_switches":   {"heavy_drag": heavy_drag},
        }
