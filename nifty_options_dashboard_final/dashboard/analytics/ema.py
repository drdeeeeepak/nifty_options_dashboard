# analytics/ema.py
# MTF Proxy EMA Engine — Pages 01, 02, 03, 04
# 7 EMAs on daily chart proxy 200 EMA of lower timeframes.

import pandas as pd
import numpy as np
from analytics.base_strategy import BaseStrategy
from config import MTF_EMA_PERIODS


class EMAEngine(BaseStrategy):
    """
    Computes 7 MTF proxy EMAs on daily chart.
    Pages 01+02 use Nifty data.
    Pages 03+04 call breadth_signals() over the top 10 stocks.
    """

    PERIODS = list(MTF_EMA_PERIODS.keys())   # [3,8,16,30,60,120,200]
    COMPRESS_PCT = 1.0   # ribbon < 1% = squeeze
    EXPAND_PCT   = 3.0   # ribbon > 3% = expanded

    # Key crossover pairs ranked by significance for weekly options
    CROSSOVER_PAIRS = [
        (30,  60),   # 1hr × 2hr — highest for weekly options
        (60,  120),  # 2hr × 4hr
        (120, 200),  # 4hr × Daily — macro
        (16,  30),   # 30min × 1hr
        (8,   16),   # 15min × 30min
        (3,   8),    # 5min × 15min — lowest, intraday noise
    ]

    # ─────────────────────────────────────────────────────────────────────────

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add ema_3, ema_8, ... ema_200 columns."""
        for p in self.PERIODS:
            df[f"ema_{p}"] = self.ema(df["close"], p)
        return df

    # ─────────────────────────────────────────────────────────────────────────

    def signals(self, df: pd.DataFrame) -> dict:
        """
        Returns signals dict for Pages 01 and 02.
        home_score: 0–6 pts for EMA regime contribution.
        """
        df = self.compute(df.copy())
        r   = df.iloc[-1]
        spot = r["close"]

        ema_vals = {p: r[f"ema_{p}"] for p in self.PERIODS}

        regime          = self._regime(spot, ema_vals)
        alignment_score = self._alignment_score(spot, ema_vals)
        ribbon_pct      = self._ribbon_pct(spot, ema_vals)
        ribbon_state    = self._ribbon_state(ribbon_pct)
        support_ema     = self._nearest_support(spot, ema_vals)
        resistance_ema  = self._nearest_resistance(spot, ema_vals)
        crossovers      = self._crossovers(df, lookback=5)
        bull_pairs      = self._bull_ordered_pairs(ema_vals)
        slopes          = self._all_slopes(df)
        home_score      = self._home_score(alignment_score, ribbon_pct, crossovers)

        return {
            "ema_values":       {f"ema_{p}": round(v, 0) for p, v in ema_vals.items()},
            "spot":             round(spot, 0),
            "ema_regime":       regime,
            "alignment_score":  alignment_score,    # how many EMAs below spot
            "ribbon_pct":       round(ribbon_pct, 2),
            "ribbon_state":     ribbon_state,
            "support_ema":      support_ema,         # (period, value, proxy_tf)
            "resistance_ema":   resistance_ema,
            "crossovers":       crossovers,          # list of recent crossover dicts
            "bull_ordered_pairs": bull_pairs,        # count of pairs in bull order
            "slopes":           slopes,              # {period: slope_1d}
            "home_score":       home_score,
            "kill_switches": {
                "death_cross_3d": self._death_cross_recent(crossovers),
                "ribbon_compressed": ribbon_pct < self.COMPRESS_PCT,
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Breadth signals for Pages 03 + 04 (top 10 stocks)

    def breadth_signals(self, stock_dfs: dict[str, pd.DataFrame]) -> dict:
        """
        Run EMA engine on each of the top 10 stocks.
        Returns breadth count, multiplier, leader/laggard lists,
        and per-stock summary for display.
        """
        above_ema60  = 0
        above_ema200 = 0
        leaders      = []
        laggards     = []
        compressed   = []
        per_stock    = {}

        for sym, df in stock_dfs.items():
            if df.empty:
                continue
            sig = self.signals(df)
            spot = sig["spot"]
            ema60  = sig["ema_values"].get("ema_60", 0)
            ema200 = sig["ema_values"].get("ema_200", 0)

            if spot > ema60:
                above_ema60 += 1
            if spot > ema200:
                above_ema200 += 1

            rp = sig["ribbon_pct"]
            if rp > 2.0:
                leaders.append(sym)
            elif rp < 0.8:
                laggards.append(sym)
            if rp < self.COMPRESS_PCT:
                compressed.append(sym)

            per_stock[sym] = {
                "regime":        sig["ema_regime"],
                "ribbon_pct":    rp,
                "ribbon_state":  sig["ribbon_state"],
                "above_ema60":   spot > ema60,
                "above_ema200":  spot > ema200,
                "ema_values":    sig["ema_values"],
            }

        n = above_ema60
        breadth_regime = (
            "BULL"    if n >= 6 else
            "NEUTRAL" if n >= 4 else
            "BEAR"
        )
        size_mult = {
            10: 1.00, 9: 1.00, 8: 1.00,
             7: 0.85, 6: 0.85,
             5: 0.65, 4: 0.65,
        }.get(n, 0.40)

        home_score = 4 if n >= 6 else 2 if n >= 4 else 0

        # Rotation signal: banks bull + IT laggard
        banks = ["HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK"]
        it    = ["INFY", "TCS"]
        banks_bull = sum(1 for b in banks if per_stock.get(b, {}).get("above_ema60", False))
        it_bear    = sum(1 for t in it   if not per_stock.get(t, {}).get("above_ema60", True))
        rotation_signal = banks_bull >= 3 and it_bear >= 1

        return {
            "above_ema60":      above_ema60,
            "above_ema200":     above_ema200,
            "breadth_regime":   breadth_regime,
            "size_multiplier":  size_mult,
            "leaders":          leaders,
            "laggards":         laggards,
            "compressed":       compressed,
            "rotation_signal":  rotation_signal,
            "per_stock":        per_stock,
            "home_score":       home_score,
            "kill_switches":    {},
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers

    def _regime(self, spot: float, ema_vals: dict) -> str:
        below = sum(1 for v in ema_vals.values() if v < spot)
        if below >= 5:
            return "BULLISH_ALIGNED"
        elif below >= 3:
            return "NEUTRAL"
        else:
            return "BEARISH_ALIGNED"

    def _alignment_score(self, spot: float, ema_vals: dict) -> int:
        """Count of EMAs below spot (0–7)."""
        return sum(1 for v in ema_vals.values() if v < spot)

    def _ribbon_pct(self, spot: float, ema_vals: dict) -> float:
        vals = list(ema_vals.values())
        if spot == 0:
            return 0.0
        return (max(vals) - min(vals)) / spot * 100

    def _ribbon_state(self, ribbon_pct: float) -> str:
        if ribbon_pct < self.COMPRESS_PCT:
            return "COMPRESSED"
        elif ribbon_pct < self.EXPAND_PCT:
            return "NORMAL"
        return "EXPANDED"

    def _nearest_support(self, spot: float, ema_vals: dict):
        """Nearest EMA below spot."""
        below = {p: v for p, v in ema_vals.items() if v < spot}
        if not below:
            return None
        p = max(below, key=below.get)   # highest value still below spot
        return {"period": p, "value": below[p], "proxy": MTF_EMA_PERIODS.get(p, "")}

    def _nearest_resistance(self, spot: float, ema_vals: dict):
        """Nearest EMA above spot."""
        above = {p: v for p, v in ema_vals.items() if v > spot}
        if not above:
            return None
        p = min(above, key=above.get)   # lowest value still above spot
        return {"period": p, "value": above[p], "proxy": MTF_EMA_PERIODS.get(p, "")}

    def _crossovers(self, df: pd.DataFrame, lookback: int = 5) -> list[dict]:
        """Detect EMA crossovers in last N candles."""
        events = []
        for shorter, longer in self.CROSSOVER_PAIRS:
            col_s = f"ema_{shorter}"
            col_l = f"ema_{longer}"
            if col_s not in df.columns or col_l not in df.columns:
                continue
            for i in range(-lookback, 0):
                try:
                    prev_diff = df[col_s].iloc[i-1] - df[col_l].iloc[i-1]
                    curr_diff = df[col_s].iloc[i]   - df[col_l].iloc[i]
                    if prev_diff < 0 and curr_diff >= 0:
                        events.append({
                            "shorter": shorter, "longer": longer,
                            "type": "GOLDEN",
                            "days_ago": abs(i),
                            "proxy_shorter": MTF_EMA_PERIODS.get(shorter),
                            "proxy_longer":  MTF_EMA_PERIODS.get(longer),
                        })
                    elif prev_diff >= 0 and curr_diff < 0:
                        events.append({
                            "shorter": shorter, "longer": longer,
                            "type": "DEATH",
                            "days_ago": abs(i),
                            "proxy_shorter": MTF_EMA_PERIODS.get(shorter),
                            "proxy_longer":  MTF_EMA_PERIODS.get(longer),
                        })
                except IndexError:
                    pass
        return events

    def _bull_ordered_pairs(self, ema_vals: dict) -> int:
        """Count crossover pairs in bull order (shorter > longer). Max 6."""
        count = 0
        for shorter, longer in self.CROSSOVER_PAIRS:
            if ema_vals.get(shorter, 0) > ema_vals.get(longer, 0):
                count += 1
        return count

    def _all_slopes(self, df: pd.DataFrame) -> dict:
        """1-day slope for each EMA period."""
        slopes = {}
        for p in self.PERIODS:
            col = f"ema_{p}"
            if col in df.columns and len(df) >= 2:
                slopes[p] = round(df[col].iloc[-1] - df[col].iloc[-2], 2)
            else:
                slopes[p] = 0.0
        return slopes

    def _home_score(self, alignment: int, ribbon_pct: float,
                    crossovers: list) -> int:
        """
        EMA page contribution to home score (0–6 pts).
        +3 alignment (5+/7), +2 ribbon not compressed, +1 no death cross 3d.
        """
        score = 0
        if alignment >= 5:
            score += 3
        elif alignment >= 3:
            score += 1
        if ribbon_pct >= self.COMPRESS_PCT:
            score += 2
        recent_death = any(
            c["type"] == "DEATH" and c["days_ago"] <= 3
            for c in crossovers
        )
        if not recent_death:
            score += 1
        return score

    def _death_cross_recent(self, crossovers: list) -> bool:
        return any(
            c["type"] == "DEATH" and c["days_ago"] <= 3
            for c in crossovers
        )
