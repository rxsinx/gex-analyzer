"""
GEX Terminal – configuration

This file contains ONLY:
  • Kite Connect API credentials
  • UI / UX preferences (chart height, refresh interval, thresholds)

ALL instrument metadata (lot sizes, tick sizes, strike intervals, expiry
dates) are fetched live from Kite Connect instruments API.
Fallback tables for those values live in modules/utils.py and are clearly
labelled as estimates for use when Kite is not connected.
"""

# ---------------------------------------------------------------------------
# Kite Connect
# ---------------------------------------------------------------------------
KITE_API_KEY    = ""      # your Kite API key
KITE_API_SECRET = ""      # your Kite API secret
KITE_REDIRECT   = "http://127.0.0.1"

# ---------------------------------------------------------------------------
# Greeks
# ---------------------------------------------------------------------------
DEFAULT_RISK_FREE_RATE = 0.07   # 7 % p.a.

# ---------------------------------------------------------------------------
# UI / refresh
# ---------------------------------------------------------------------------
AUTO_REFRESH_INTERVAL  = 15    # seconds between full option-chain refreshes
SPOT_REFRESH_INTERVAL  = 5     # seconds between lightweight LTP spot updates
CACHE_TTL              = 15    # seconds

CHART_HEIGHT           = 500
TABLE_HEIGHT           = 400
THEME                  = "plotly_dark"

# ---------------------------------------------------------------------------
# Strike range shown in the terminal
# ---------------------------------------------------------------------------
DEFAULT_STRIKE_RANGE_PCT = 10   # ± % around spot

# ---------------------------------------------------------------------------
# Alert thresholds
# ---------------------------------------------------------------------------
PCR_BULLISH_THRESHOLD        = 0.8
PCR_BEARISH_THRESHOLD        = 1.2
MAX_PAIN_DISTANCE_THRESHOLD  = 0.02   # 2 %
GAMMA_FLIP_ZONE_THRESHOLD    = 0.01   # 1 %
