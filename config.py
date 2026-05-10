"""
Configuration file for GEX Terminal

NOTE: LOT SIZES here are FALLBACK defaults only.
When Kite Connect is authenticated, lot sizes are fetched dynamically
from the NFO instruments API so they always reflect the latest SEBI revision.
"""

# Kite Connect API Configuration
KITE_API_KEY = ""        # Add your Kite API key here
KITE_API_SECRET = ""     # Add your Kite API secret here
KITE_REDIRECT_URL = "http://127.0.0.1"

# Risk Parameters
DEFAULT_RISK_FREE_RATE = 0.07   # 7 % annual

# ---------------------------------------------------------------------------
# Fallback lot sizes  (authoritative source = Kite NFO instruments)
# Last updated: May 2025 per NSE circular
# ---------------------------------------------------------------------------
DEFAULT_LOT_SIZES = {
    'NIFTY':      65,   # revised from 75 → 65 
    'BANKNIFTY':  35,   # revised from 15 → 35
    'FINNIFTY':   65,   # revised from 40 → 65
    'MIDCPNIFTY': 120,  # revised from 75 → 120
}

# ---------------------------------------------------------------------------
# Expiry weekday per index (0 = Mon, 3 = Thu)
# Used as FALLBACK when Kite is not connected.
# ---------------------------------------------------------------------------
EXPIRY_WEEKDAYS = {
    'NIFTY':      3,   # Thursday
    'BANKNIFTY':  2,   # Wednesday
    'FINNIFTY':   1,   # Tuesday
    'MIDCPNIFTY': 0,   # Monday
}

# Trading Parameters
MAX_CAPITAL = 1_000_000      # Default max capital (₹)
MAX_RISK_PER_TRADE = 0.02    # 2 % max risk per trade

# Data Refresh
AUTO_REFRESH_INTERVAL = 15   # seconds
CACHE_TTL = 15               # seconds

# Strikes Configuration
STRIKE_RANGE_PERCENT = 10    # Default ± % around spot
NUM_STRIKES_TO_SHOW  = 40

# Greeks Calculation
MIN_TIME_TO_EXPIRY = 1 / 365   # 1 day minimum (years)
DEFAULT_IV         = 0.15      # 15 % default IV when calculation fails

# Alert Thresholds
PCR_BULLISH_THRESHOLD       = 0.8
PCR_BEARISH_THRESHOLD       = 1.2
MAX_PAIN_DISTANCE_THRESHOLD = 0.02   # 2 %

# UI Configuration
CHART_HEIGHT = 500
TABLE_HEIGHT = 400
THEME = 'plotly_dark'
