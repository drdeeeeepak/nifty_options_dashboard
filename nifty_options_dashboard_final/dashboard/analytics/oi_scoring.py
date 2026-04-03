# analytics/oi_scoring.py
# OI Momentum Scoring Engine — Page 10B
# % Change OI scores, DTE panic amplifier, Wall Strength 1–10, Net Strike Score.
# Dual expiry: near = intelligence layer, far = your trade layer.

import pandas as pd
import numpy as np
from analytics.base_strategy import BaseStrategy
from config import (
    DTE_THETA_MIN, DTE_WARN_MIN,
    OI_SCORE_HIGH, OI_SCORE_MED, OI_SCORE_LOW, OI_NOISE,
    OI_UNWIND_MILD, OI_UNWIND_HEAVY, OI_PANIC,
    WALL_RATIO_LOW, WALL_RATIO_MID,
    WALL_INTRADAY_REINFORCE, WALL_INTRADAY_ABANDON,
)

class OIScoringEngine(BaseStrategy):
    """
    NEW layer on top of OptionsChainEngine.
    Works on both near expiry (intelligence) and far expiry (your trade).
    """

    # ─────────────────────────────────────────────────────────────────────────

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        return df   # chain data arrives pre-computed

    # ─────────────────────────────────────────────────────────────────────────

    def signals(self, near_df: pd.DataFrame, far_df: pd.DataFrame,
                near_dte: int, far_dte: int,
                near_expiry=None, far_expiry=None) -> dict:
        """
        Full dual-expiry scoring.
        Returns near_scored, far_scored, and position action rules.
        """
        near_scored = self.score_chain(near_df.copy(), near_dte) if not near_df.empty else pd.DataFrame()
        far_scored  = self.score_chain(far_df.copy(),  far_dte)  if not far_df.empty  else pd.DataFrame()

        # Position action at your specific short strikes (passed from page)
        return {
            "near_scored":   near_scored,
            "far_scored":    far_scored,
            "near_dte":      near_dte,
            "far_dte":       far_dte,
            "near_mult":     self.get_dte_multiplier(near_dte),
            "far_mult":      self.get_dte_multiplier(far_dte),
            "near_wall_mod": self.get_wall_modifier(near_dte),
            "far_wall_mod":  self.get_wall_modifier(far_dte),
            "near_expiry":   near_expiry,
            "far_expiry":    far_expiry,
            "kill_switches": {},
            "home_score":    0,   # 10B is informational — score lives in P10
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Core scoring pipeline

    def score_chain(self, df: pd.DataFrame, dte: int) -> pd.DataFrame:
        """
        Add scoring columns to options chain DataFrame.
        Returns df with: pe_base, ce_base, pe_adj, ce_adj,
                          net_score, pe_wall, ce_wall, position_action
        """
        mult     = self.get_dte_multiplier(dte)
        wall_mod = self.get_wall_modifier(dte)

        df["pe_base"] = df["pe_pct_change"].apply(self.score_pe_base)
        df["ce_base"] = df["ce_pct_change"].apply(self.score_ce_base)

        # Apply DTE multiplier ONLY to unwinding signals
        df["pe_adj"] = df["pe_base"].apply(
            lambda b: b * mult if b < 0 else float(b)
        )
        df["ce_adj"] = df["ce_base"].apply(
            lambda b: b * mult if b > 0 else float(b)
        )

        df["net_score"] = (df["pe_adj"] + df["ce_adj"]).clip(-6, 6).round()

        df["pe_wall"] = df.apply(
            lambda r: self.wall_strength(
                r["pe_oi"], r["ce_oi"], r["pe_pct_change"], dte
            ), axis=1
        )
        df["ce_wall"] = df.apply(
            lambda r: self.wall_strength(
                r["ce_oi"], r["pe_oi"], r["ce_pct_change"], dte
            ), axis=1
        )

        df["position_action"] = df.apply(
            lambda r: self._position_action(r["net_score"], r["pe_wall"], r["ce_wall"]),
            axis=1
        )

        return df

    # ─────────────────────────────────────────────────────────────────────────
    # DTE zone helpers

    def get_dte_multiplier(self, dte: int) -> float:
        """Panic amplifier for unwinding signals."""
        if   dte > DTE_THETA_MIN: return 1.0   # theta buffer
        elif dte >= DTE_WARN_MIN:  return 1.5   # warning zone
        else:                      return 2.0   # gamma danger

    def get_wall_modifier(self, dte: int) -> int:
        """Structural modifier to wall base score."""
        if   dte > DTE_THETA_MIN: return +2    # fortress
        elif dte >= DTE_WARN_MIN:  return  0    # standard
        else:                      return -2    # fragile

    def dte_zone(self, dte: int) -> str:
        if   dte > DTE_THETA_MIN: return "THETA_BUFFER"
        elif dte >= DTE_WARN_MIN:  return "WARNING"
        else:                      return "GAMMA_DANGER"

    # ─────────────────────────────────────────────────────────────────────────
    # Base scoring functions

    def score_pe_base(self, pct_change: float) -> int:
        """
        Put side: rising OI = support building (positive).
        Falling OI = writers covering = panic (negative → gets DTE mult).
        """
        if   pct_change >  OI_SCORE_HIGH: return  3
        elif pct_change >  OI_SCORE_MED:  return  2
        elif pct_change >  OI_SCORE_LOW:  return  1
        elif pct_change > -OI_NOISE:      return  0   # noise
        elif pct_change > OI_UNWIND_HEAVY:return -1   # mild unwind → DTE mult
        elif pct_change > OI_PANIC:       return -2   # heavy unwind → DTE mult
        else:                             return -3   # panic → DTE mult

    def score_ce_base(self, pct_change: float) -> int:
        """
        Call side: rising OI = resistance building (negative signal).
        Falling OI = call writers covering = ceiling weakening (positive → DTE mult).
        """
        if   pct_change >  OI_SCORE_HIGH: return -3
        elif pct_change >  OI_SCORE_MED:  return -2
        elif pct_change >  OI_SCORE_LOW:  return -1
        elif pct_change > -OI_NOISE:      return  0   # noise
        elif pct_change > OI_UNWIND_HEAVY:return  1   # short covering → DTE mult
        elif pct_change > OI_PANIC:       return  2   # heavy covering → DTE mult
        else:                             return  3   # panic covering → DTE mult

    # ─────────────────────────────────────────────────────────────────────────
    # Wall strength 1–10

    def wall_strength(self, dominant_oi: float, weaker_oi: float,
                      dominant_intraday_pct: float, dte: int) -> int:
        """
        Three-step wall strength calculation.
        Step A: OI dominance ratio → base 3/5/8
        Step B: DTE modifier ±2
        Step C: Intraday flow modifier +2 / −3
        Capped 1–10.
        """
        # Step A
        ratio = dominant_oi / weaker_oi if weaker_oi > 0 else 10.0
        if   ratio < WALL_RATIO_LOW: base = 3
        elif ratio < WALL_RATIO_MID: base = 5
        else:                        base = 8

        # Step B
        score = base + self.get_wall_modifier(dte)

        # Step C
        if   dominant_intraday_pct > WALL_INTRADAY_REINFORCE * 100: score += 2
        elif dominant_intraday_pct < WALL_INTRADAY_ABANDON:         score -= 3

        return int(np.clip(score, 1, 10))

    # ─────────────────────────────────────────────────────────────────────────
    # Position action at a strike

    def _position_action(self, net_score: float,
                          pe_wall: int, ce_wall: int) -> str:
        """
        Returns recommended action for the leg at this strike.
        Positive net = bullish (PE leg protected).
        Negative net = bearish (CE leg protected).
        """
        ns = int(net_score)
        # PE leg assessment
        if   ns >= 3 and pe_wall >= 7: return "HOLD_PE_CONFIDENT"
        elif ns >= 1 and pe_wall >= 4: return "HOLD_PE_MONITOR"
        elif ns <= -1:                 return "REDUCE_PE_50PCT"
        elif ns <= -2 and pe_wall <= 3:return "EXIT_PE"
        # CE leg assessment (negative net = CE protected)
        elif ns <= -3 and ce_wall >= 7:return "HOLD_CE_CONFIDENT"
        elif ns <  0  and ce_wall >= 4:return "HOLD_CE_MONITOR"
        elif ns >= 1  and ce_wall <= 3:return "REDUCE_CE_50PCT"
        elif ns >= 3:                  return "EXIT_CE"
        return "BALANCED_IC"

    # ─────────────────────────────────────────────────────────────────────────
    # Convergence check: near vs far at same strike

    def convergence_check(self, near_scored: pd.DataFrame,
                           far_scored: pd.DataFrame,
                           ce_strike: int, pe_strike: int) -> dict:
        """
        Check if near and far expiry agree on wall strength at your IC strikes.
        Dual-fortress (both ≥7) = maximum confidence.
        """
        def safe_get(df, strike, col):
            if df.empty or strike not in df.index:
                return 0
            return df.loc[strike, col] if col in df.columns else 0

        return {
            "pe_near_wall": safe_get(near_scored, pe_strike, "pe_wall"),
            "pe_far_wall":  safe_get(far_scored,  pe_strike, "pe_wall"),
            "ce_near_wall": safe_get(near_scored, ce_strike, "ce_wall"),
            "ce_far_wall":  safe_get(far_scored,  ce_strike, "ce_wall"),
            "pe_near_score":safe_get(near_scored, pe_strike, "net_score"),
            "pe_far_score": safe_get(far_scored,  pe_strike, "net_score"),
            "ce_near_score":safe_get(near_scored, ce_strike, "net_score"),
            "ce_far_score": safe_get(far_scored,  ce_strike, "net_score"),
            "pe_dual_fortress": (safe_get(near_scored, pe_strike, "pe_wall") >= 7 and
                                  safe_get(far_scored,  pe_strike, "pe_wall") >= 7),
            "ce_dual_fortress": (safe_get(near_scored, ce_strike, "ce_wall") >= 7 and
                                  safe_get(far_scored,  ce_strike, "ce_wall") >= 7),
        }
