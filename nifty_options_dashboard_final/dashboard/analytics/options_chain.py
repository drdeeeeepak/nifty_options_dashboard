# analytics/options_chain.py
# Options Chain Analysis Engine — Page 10 (Rules 1–20)
# PCR, Max Pain, OI Walls, GEX, Migration, IV Skew, Stability.

import pandas as pd
import numpy as np
from analytics.base_strategy import BaseStrategy
from config import (
    OI_STRIKE_STEP, PCR_BALANCED_LOW, PCR_BALANCED_HI,
    WALL_DIST_RANGE, WALL_DIST_EXPAND, OI_WALL_PCT,
    DTE_THETA_MIN, DTE_WARN_MIN,
)

class OptionsChainEngine(BaseStrategy):
    """
    Implements all 20 options chain rules.
    Input: options chain DataFrame from live_fetcher.get_options_chain()
    """

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """No column addition needed — chain data comes pre-fetched."""
        return df

    # ─────────────────────────────────────────────────────────────────────────

    def signals(self, df: pd.DataFrame, spot: float, dte: int) -> dict:
        """
        Full 20-rule analysis.
        Returns comprehensive signal dict for page and home score.
        """
        if df.empty:
            return self._empty_signals()

        pcr          = self._pcr(df)
        max_pain     = self._max_pain(df)
        call_wall    = self._oi_wall(df, "ce_oi")
        put_wall     = self._oi_wall(df, "pe_oi")
        call_vol_wall= self._oi_wall(df, "ce_vol")
        put_vol_wall = self._oi_wall(df, "pe_vol")
        wall_dist_pts= call_wall - put_wall
        wall_dist_pct= abs(wall_dist_pts) / spot * 100 if spot > 0 else 0
        gex          = self._gex(df, spot)
        migration    = self._migration_status(df, spot)
        ce_weakness  = self._weakness(df, side="ce")
        pe_weakness  = self._weakness(df, side="pe")
        straddle     = self._straddle_price(df, spot)
        atm_iv       = self._atm_iv(df, spot)
        iv_skew      = self._iv_skew(df, spot)
        regime       = self._determine_regime(
            pcr, wall_dist_pct, gex["total_gex"], migration["detected"]
        )
        kills        = self._kill_switches(df, spot, wall_dist_pct, migration, gex)
        home_score   = self._home_score(
            gex, pcr, migration, wall_dist_pct, kills
        )

        return {
            # Rule 1
            "spot":             round(spot, 0),
            "dte":              dte,
            # Rules 2-6: OI walls
            "call_wall":        call_wall,
            "put_wall":         put_wall,
            "call_vol_wall":    call_vol_wall,
            "put_vol_wall":     put_vol_wall,
            "wall_dist_pts":    wall_dist_pts,
            "wall_dist_pct":    round(wall_dist_pct, 2),
            # Rule 7: Range/expansion
            "market_regime":    regime,
            # Rule 8: PCR
            "pcr":              round(pcr, 2),
            # Rule 9: Max pain
            "max_pain":         max_pain,
            "max_pain_dist":    round(abs(spot - max_pain), 0),
            # Rule 13-15: GEX
            "gex":              gex,
            # Rule 16-18: Migration
            "migration":        migration,
            # Rules 3-4: Weakness
            "ce_weakness":      ce_weakness,
            "pe_weakness":      pe_weakness,
            # Options pricing
            "straddle_price":   round(straddle, 2),
            "atm_iv":           round(atm_iv, 2),
            "iv_skew":          round(iv_skew, 2),
            # Decision
            "strategy":         self._strategy(regime, gex, migration, ce_weakness, pe_weakness),
            "kill_switches":    kills,
            "home_score":       home_score,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Rule 8 — PCR

    def _pcr(self, df: pd.DataFrame) -> float:
        total_pe = df["pe_oi"].sum()
        total_ce = df["ce_oi"].sum()
        if total_ce == 0:
            return 0.0
        return total_pe / total_ce

    # ─────────────────────────────────────────────────────────────────────────
    # Rule 9 — Max Pain

    def _max_pain(self, df: pd.DataFrame) -> int:
        """
        Strike where total option writer losses are minimised.
        For each strike, compute total OI × intrinsic value of all options.
        """
        strikes = df.index.tolist()
        losses  = {}
        for candidate in strikes:
            ce_loss = sum(
                max(0, candidate - s) * df.loc[s, "ce_oi"]
                for s in strikes
            )
            pe_loss = sum(
                max(0, s - candidate) * df.loc[s, "pe_oi"]
                for s in strikes
            )
            losses[candidate] = ce_loss + pe_loss
        return min(losses, key=losses.get)

    # ─────────────────────────────────────────────────────────────────────────
    # Rules 2, 5 — OI / Vol walls

    def _oi_wall(self, df: pd.DataFrame, col: str) -> int:
        if col not in df.columns or df[col].max() == 0:
            return 0
        return int(df[col].idxmax())

    # ─────────────────────────────────────────────────────────────────────────
    # Rule 7 — Market regime from wall distance

    def _determine_regime(self, pcr, wall_dist_pct, total_gex, migration) -> str:
        if migration:
            return "MIGRATION"
        if total_gex < 0:
            return "NEGATIVE_GEX_EXPANSION"
        if wall_dist_pct < WALL_DIST_RANGE and PCR_BALANCED_LOW <= pcr <= PCR_BALANCED_HI:
            return "RANGE_IC"
        if wall_dist_pct > WALL_DIST_EXPAND:
            return "EXPANSION"
        return "DIRECTIONAL"

    # ─────────────────────────────────────────────────────────────────────────
    # Rules 13-15 — GEX (Gamma Exposure)

    def _gex(self, df: pd.DataFrame, spot: float) -> dict:
        """
        GEX = sum over strikes of (CE_OI - PE_OI) × Gamma × spot² × 0.01
        We approximate using open interest as a gamma proxy.
        Positive GEX = dealers long gamma = pinning effect.
        """
        # Simplified: net OI weighted by distance from spot
        if "ce_oi" not in df.columns:
            return {"total_gex": 0, "flip_level": spot, "regime": "UNKNOWN"}

        gex_by_strike = {}
        for strike in df.index:
            distance = abs(strike - spot) / spot
            weight   = np.exp(-distance * 10)   # exponential decay from ATM
            net_oi   = df.loc[strike, "ce_oi"] - df.loc[strike, "pe_oi"]
            gex_by_strike[strike] = net_oi * weight

        total_gex = sum(gex_by_strike.values())

        # Flip level = where cumulative GEX changes sign
        cumsum = 0
        flip   = spot
        for strike in sorted(df.index):
            cumsum += gex_by_strike.get(strike, 0)
            if cumsum > 0:
                flip = strike
                break

        regime = "POSITIVE_PINNING" if total_gex > 0 else "NEGATIVE_EXPANSION"

        return {
            "total_gex":  round(total_gex, 0),
            "flip_level": flip,
            "regime":     regime,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Rules 16-18 — OI migration

    def _migration_status(self, df: pd.DataFrame, spot: float) -> dict:
        """
        Migration = peak OI has shifted 2+ strikes intraday.
        Signal: 2nd highest OI strike > 75% of peak AND closer to spot.
        """
        if "pe_oi" not in df.columns:
            return {"detected": False, "direction": None}

        peak_pe    = df["pe_oi"].idxmax()
        second_pe  = df["pe_oi"].nlargest(2).index[-1]
        peak_ce    = df["ce_oi"].idxmax()
        second_ce  = df["ce_oi"].nlargest(2).index[-1]

        pe_ratio   = df.loc[second_pe, "pe_oi"] / max(df.loc[peak_pe, "pe_oi"], 1)
        ce_ratio   = df.loc[second_ce, "ce_oi"] / max(df.loc[peak_ce, "ce_oi"], 1)

        # Migration: second peak very close in OI AND 2+ strikes away from peak
        pe_migr = (pe_ratio > OI_WALL_PCT and
                   abs(second_pe - peak_pe) >= 2 * OI_STRIKE_STEP)
        ce_migr = (ce_ratio > OI_WALL_PCT and
                   abs(second_ce - peak_ce) >= 2 * OI_STRIKE_STEP)

        return {
            "detected":    pe_migr or ce_migr,
            "pe_migration":pe_migr,
            "ce_migration":ce_migr,
            "direction":   "DOWN" if pe_migr else "UP" if ce_migr else None,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Rules 3-4 — OI / Vol weakness

    def _weakness(self, df: pd.DataFrame, side: str) -> dict:
        """
        CE weakness: CE vol < 75% of PE vol (resistance weaker than support).
        PE weakness: PE vol < 75% of CE vol.
        """
        total_ce_vol = df["ce_vol"].sum()
        total_pe_vol = df["pe_vol"].sum()
        if side == "ce":
            detected = (total_pe_vol > 0 and
                        total_ce_vol < OI_WALL_PCT * total_pe_vol)
        else:
            detected = (total_ce_vol > 0 and
                        total_pe_vol < OI_WALL_PCT * total_ce_vol)
        return {"detected": detected,
                "ce_vol": total_ce_vol,
                "pe_vol": total_pe_vol}

    # ─────────────────────────────────────────────────────────────────────────
    # Pricing helpers

    def _straddle_price(self, df: pd.DataFrame, spot: float) -> float:
        atm = self.round_strike(spot)
        if atm not in df.index:
            return 0.0
        return float(df.loc[atm, "ce_ltp"] + df.loc[atm, "pe_ltp"])

    def _atm_iv(self, df: pd.DataFrame, spot: float) -> float:
        atm = self.round_strike(spot)
        if atm not in df.index:
            return 0.0
        return float((df.loc[atm, "ce_iv"] + df.loc[atm, "pe_iv"]) / 2)

    def _iv_skew(self, df: pd.DataFrame, spot: float) -> float:
        """Put IV minus Call IV at equidistant 200pt strikes."""
        otm_put  = self.round_strike(spot - 200)
        otm_call = self.round_strike(spot + 200)
        if otm_put not in df.index or otm_call not in df.index:
            return 0.0
        return float(df.loc[otm_put, "pe_iv"] - df.loc[otm_call, "ce_iv"])

    # ─────────────────────────────────────────────────────────────────────────
    # Rule 19 — Strategy decision

    def _strategy(self, regime, gex, migration, ce_weakness, pe_weakness) -> str:
        if migration["detected"] or gex["total_gex"] < 0:
            return "NO_TRADE"
        if regime == "RANGE_IC":
            return "IRON_CONDOR"
        if pe_weakness["detected"] and not ce_weakness["detected"]:
            return "BEAR_CALL_SPREAD"
        if ce_weakness["detected"] and not pe_weakness["detected"]:
            return "BULL_PUT_SPREAD"
        return "IRON_CONDOR"

    # ─────────────────────────────────────────────────────────────────────────
    # Kill switches

    def _kill_switches(self, df, spot, wall_dist_pct, migration, gex) -> dict:
        K1 = wall_dist_pct > 2.5   # VA breach proxy
        K2 = False                  # Trend day — detected via Market Profile
        K3 = False                  # Gap beyond VA — detected via MP
        K4 = migration["detected"]  # Migration = soft K4 proxy
        K5 = gex["total_gex"] < 0  # Negative GEX = expansion risk

        return {
            "K1_wall_breach":    bool(K1),
            "K2_trend_day":      bool(K2),
            "K3_gap_unfilled":   bool(K3),
            "K4_migration":      bool(K4),
            "K5_negative_gex":   bool(K5),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Home score (max 25)

    def _home_score(self, gex, pcr, migration, wall_dist_pct, kills) -> int:
        if any(kills.values()):
            return 0
        score = 0
        if gex["total_gex"] > 0:                            score += 8
        if PCR_BALANCED_LOW <= pcr <= PCR_BALANCED_HI:      score += 5
        if not migration["detected"]:                        score += 5
        if wall_dist_pct < 1.5:                             score += 4
        # IVP handled by VIX/IV engine — proxy: if spread exists
        score += 3   # placeholder — overridden by VIX engine IVP
        return min(score, 25)

    def _empty_signals(self) -> dict:
        return {
            "spot": 0, "dte": 0,
            "call_wall": 0, "put_wall": 0, "wall_dist_pct": 0,
            "pcr": 0, "max_pain": 0, "gex": {"total_gex": 0, "flip_level": 0, "regime": "UNKNOWN"},
            "migration": {"detected": False}, "strategy": "NO_TRADE",
            "kill_switches": {}, "home_score": 0,
        }
