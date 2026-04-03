# config.py
# Central configuration for Nifty 50 Biweekly Credit Options Dashboard
# Update TOP_10_NIFTY quarterly at index rebalance

# ─── Kite instrument tokens (NSE) ─────────────────────────────────────────────
NIFTY_INDEX_TOKEN = 256265          # NSE:NIFTY 50
NIFTY_SYMBOL      = "NIFTY 50"

# ─── Top 10 Nifty 50 by weight — UPDATE QUARTERLY ─────────────────────────────
TOP_10_NIFTY = [
    "HDFCBANK",
    "RELIANCE",
    "ICICIBANK",
    "INFY",
    "TCS",
    "KOTAKBANK",
    "LT",
    "BHARTIARTL",
    "AXISBANK",
    "ITC",
]

# NSE instrument tokens for top 10 (NSE cash segment)
TOP_10_TOKENS = {
    "HDFCBANK":   341249,
    "RELIANCE":   738561,
    "ICICIBANK":  1270529,
    "INFY":       408065,
    "TCS":        2953217,
    "KOTAKBANK":  492033,
    "LT":         2939649,
    "BHARTIARTL": 2714625,
    "AXISBANK":   1510401,
    "ITC":        424961,
}

# ─── MTF Proxy EMA periods ────────────────────────────────────────────────────
# Each daily EMA proxies the 200 EMA of the corresponding intraday timeframe
MTF_EMA_PERIODS = {
    3:   "5min",
    8:   "15min",
    16:  "30min",
    30:  "1hr",
    60:  "2hr",
    120: "4hr",
    200: "Daily",
}

# ─── RSI engine thresholds ────────────────────────────────────────────────────
RSI_PERIOD = 14

# Weekly RSI regime boundaries
W_RSI_CAPIT      = 30
W_RSI_BEAR_MAX   = 40
W_RSI_BEAR_TRANS = 45
W_RSI_NEUTRAL_MID= 50
W_RSI_BULL_TRANS = 60
W_RSI_BULL_MIN   = 65
W_RSI_EXHAUST    = 70

# Daily RSI execution zones
D_RSI_CAPIT      = 32
D_RSI_BEAR_P     = 39
D_RSI_BAL_LOW    = 46
D_RSI_BAL_HIGH   = 54
D_RSI_BULL_P     = 61
D_RSI_EXHAUST    = 68

# Kill switch thresholds
RSI_KS_W_FLIP_BULL = 55    # weekly below this → K1 PE exit
RSI_KS_W_FLIP_BEAR = 45    # weekly above this → K1 CE exit

# ─── Bollinger Bands ──────────────────────────────────────────────────────────
BB_PERIOD   = 20
BB_STD      = 2.0
BB_SQUEEZE  = 3.5   # BW% < this = squeeze
BB_NORMAL_L = 5.0
BB_NORMAL_H = 7.0
BB_EXPAND   = 8.0   # BW% > this = expansion

# ─── Options Chain ────────────────────────────────────────────────────────────
OI_STRIKE_RANGE  = 500     # ATM ± 500 pts
OI_STRIKE_STEP   = 50      # Nifty strike intervals
OI_STABLE_MINS   = 60      # minutes for peak stability
OI_WALL_PCT      = 0.75    # 75% threshold for weakness/drift rules
PCR_BALANCED_LOW = 0.9
PCR_BALANCED_HI  = 1.1
WALL_DIST_RANGE  = 1.2     # % — below this = range regime
WALL_DIST_EXPAND = 2.5     # % — above this = expansion

# DTE zones
DTE_THETA_MIN = 5    # DTE > 5 = theta buffer
DTE_WARN_MIN  = 3    # DTE 3-5 = warning zone
DTE_GAMMA_MAX = 2    # DTE 0-2 = gamma danger

# OI % change scoring thresholds
OI_SCORE_HIGH  = 50   # > 50% = score ±3
OI_SCORE_MED   = 25   # > 25% = score ±2
OI_SCORE_LOW   = 10   # > 10% = score ±1
OI_NOISE       = 10   # ±10% = noise = 0
OI_UNWIND_MILD = -10  # -10 to -20 = mild unwind
OI_UNWIND_HEAVY= -20  # -20 to -35 = heavy
OI_PANIC       = -35  # < -35 = panic

# Wall strength
WALL_RATIO_LOW  = 1.5   # base score 3
WALL_RATIO_MID  = 2.5   # base score 5
WALL_INTRADAY_REINFORCE = 0.15   # > 15% intraday = +2
WALL_INTRADAY_ABANDON   = 0.0    # < 0% = -3

# ─── VIX / IV thresholds ─────────────────────────────────────────────────────
VIX_COMPLACENT = 11
VIX_LOW_NORMAL = 17
VIX_SWEET_SPOT = 20
VIX_ELEVATED   = 28
VIX_CRISIS     = 40

IVP_AVOID   = 25
IVP_SMALL   = 35
IVP_IDEAL_H = 70
IVP_EXTREME = 80

HV_PERIOD   = 20    # days for realized vol calculation

# ─── Geometric Edge Scanner ───────────────────────────────────────────────────
GEO_PRICE_STRENGTH = {         # close vs open % threshold by segment
    "nifty50":    0.020,
    "nifty_next": 0.025,
    "midcap":     0.030,
    "smallcap":   0.035,
}
GEO_VOL_MULT = {               # volume vs 20d SMA multiplier
    "nifty50":    1.5,
    "nifty_next": 2.0,
    "midcap":     2.0,
    "smallcap":   2.5,
}
GEO_ADR = {                    # min 20d average daily range %
    "nifty50":    1.5,
    "nifty_next": 2.2,
    "midcap":     3.0,
    "smallcap":   4.0,
}
GEO_EP_GAP = {                 # min episodic pivot gap %
    "nifty50":    0.020,
    "nifty_next": 0.030,
    "midcap":     0.040,
    "smallcap":   0.060,
}
GEO_VOL_SMA_PERIOD = 20
GEO_MAX_RESULTS    = 10
GEO_MIN_RR         = 6         # minimum risk:reward for India friction
GEO_MARKET_HEALTH_BULL  = 350  # Nifty500 > 200SMA stocks → aggressive bull
GEO_MARKET_HEALTH_SELECT= 200  # → selective
# < 200 → bearish, pause all scans

# ─── Home page scoring weights ────────────────────────────────────────────────
HOME_WEIGHTS = {
    "options_chain":  25,
    "market_profile": 20,
    "rsi":            20,
    "bollinger":      15,
    "vix_iv":         10,
    "ema_regime":      6,
    "breadth":         4,
}

# Score → position size
HOME_SCORE_BANDS = {
    (0,  34):  0.00,   # no trade
    (35, 49):  0.00,   # wait
    (50, 64):  0.50,   # 50% size
    (65, 79):  0.75,   # 75% size
    (80, 100): 1.00,   # full size
}

# Breadth multiplier (applied after score band)
BREADTH_MULTIPLIERS = {
    10: 1.00, 9: 1.00, 8: 1.00,
     7: 0.85, 6: 0.85,
     5: 0.65, 4: 0.65,
     3: 0.40, 2: 0.40, 1: 0.40, 0: 0.40,
}

# ─── Cache TTLs (seconds) ─────────────────────────────────────────────────────
TTL_OPTIONS  = 30
TTL_PRICE    = 60
TTL_DAILY    = 86400
TTL_WEEKLY   = 604800

# ─── Expiry cycle ─────────────────────────────────────────────────────────────
EXPIRY_WEEKDAY = 1   # Tuesday (0=Mon, 1=Tue, ...)

# ─── Data paths ───────────────────────────────────────────────────────────────
PARQUET_DIR  = "data/parquet"
WATCHLIST_DIR= "data/watchlists"
