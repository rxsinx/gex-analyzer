"""
Configuration file for GEX Terminal
"""

# Kite Connect API Configuration
KITE_API_KEY = ""  # Add your Kite API key
KITE_API_SECRET = ""  # Add your Kite API secret
KITE_REDIRECT_URL = "http://127.0.0.1"

# Risk Parameters
DEFAULT_RISK_FREE_RATE = 0.07  # 7% annual
DEFAULT_LOT_SIZES = {
    'NIFTY': 50,
    'BANKNIFTY': 15,
    'FINNIFTY': 40,
    'MIDCPNIFTY': 75
}

# Trading Parameters
MAX_CAPITAL = 1000000  # Default max capital
MAX_RISK_PER_TRADE = 0.02  # 2% max risk per trade

# Data Refresh
AUTO_REFRESH_INTERVAL = 15  # seconds
CACHE_TTL = 15  # seconds

# Strikes Configuration
STRIKE_RANGE_PERCENT = 10  # Default strike range %
NUM_STRIKES_TO_SHOW = 40

# Greeks Calculation
MIN_TIME_TO_EXPIRY = 0.0027  # 1 day minimum
DEFAULT_IV = 0.15  # 15% default IV

# Alert Thresholds
PCR_BULLISH_THRESHOLD = 0.8
PCR_BEARISH_THRESHOLD = 1.2
MAX_PAIN_DISTANCE_THRESHOLD = 0.02  # 2%

# UI Configuration
CHART_HEIGHT = 500
TABLE_HEIGHT = 400
THEME = 'plotly_dark'
