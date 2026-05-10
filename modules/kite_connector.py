"""
Kite Connect integration for live market data
- Dynamic lot size detection from instruments
- Dynamic expiry date fetching from instruments
- IV calculation from LTP (Kite does not provide IV directly)
"""

from kiteconnect import KiteConnect
import pandas as pd
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq
from datetime import datetime
import streamlit as st


# ---------------------------------------------------------------------------
# Implied Volatility helper (Black-Scholes inverse)
# ---------------------------------------------------------------------------

def _bs_price(S, K, T, r, sigma, option_type='call'):
    """Black-Scholes theoretical price."""
    if T <= 0 or sigma <= 0:
        return max(S - K, 0) if option_type == 'call' else max(K - S, 0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if option_type == 'call':
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def calculate_iv_from_ltp(S, K, T, r, market_price, option_type='call'):
    """
    Calculate implied volatility from market LTP using Brent's method.
    Returns IV as a decimal (e.g. 0.15 for 15%).
    Falls back to 0.15 if calculation fails.
    """
    if T <= 0 or market_price <= 0:
        return 0.15

    intrinsic = max(S - K, 0) if option_type == 'call' else max(K - S, 0)
    if market_price <= intrinsic:
        return 0.001  # deep ITM / degenerate

    try:
        def objective(sigma):
            return _bs_price(S, K, T, r, sigma, option_type) - market_price

        # Brent's method – bracket [0.1%, 500%]
        iv = brentq(objective, 1e-4, 5.0, xtol=1e-6, maxiter=200)
        return max(0.001, iv)
    except Exception:
        return 0.15


# ---------------------------------------------------------------------------
# Expiry weekday map  (NSE rules as of FY-2025)
# ---------------------------------------------------------------------------
EXPIRY_WEEKDAY = {
    'NIFTY':      3,   # Thursday
    'BANKNIFTY':  2,   # Wednesday
    'FINNIFTY':   1,   # Tuesday
    'MIDCPNIFTY': 0,   # Monday
    'SENSEX':     4,   # Friday (BSE)
}


# ---------------------------------------------------------------------------
# KiteManager
# ---------------------------------------------------------------------------

class KiteManager:
    """Manage Kite Connect API operations."""

    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.kite = KiteConnect(api_key=api_key)
        self.access_token = None
        # Cache instruments to avoid repeated API calls
        self._instruments_cache: dict[str, list] = {}

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def get_login_url(self):
        return self.kite.login_url()

    def set_access_token(self, request_token):
        try:
            data = self.kite.generate_session(request_token, api_secret=self.api_secret)
            self.access_token = data["access_token"]
            self.kite.set_access_token(self.access_token)
            return True
        except Exception as e:
            st.error(f"Authentication failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Instruments helpers
    # ------------------------------------------------------------------

    def _get_instruments(self, exchange='NFO') -> list:
        """Return cached instrument list for the given exchange."""
        if exchange not in self._instruments_cache:
            try:
                self._instruments_cache[exchange] = self.kite.instruments(exchange)
            except Exception as e:
                st.error(f"Error fetching instruments: {e}")
                self._instruments_cache[exchange] = []
        return self._instruments_cache[exchange]

    def get_lot_size(self, symbol: str) -> int:
        """
        Fetch the current lot size for *symbol* from Kite's NFO instruments.
        Falls back to hardcoded defaults if lookup fails.
        """
        FALLBACK = {'NIFTY': 75, 'BANKNIFTY': 35, 'FINNIFTY': 65, 'MIDCPNIFTY': 120}
        try:
            instruments = self._get_instruments('NFO')
            for inst in instruments:
                if (inst.get('name', '').upper() == symbol.upper()
                        and inst.get('instrument_type') in ('CE', 'PE')
                        and inst.get('lot_size', 0) > 0):
                    return int(inst['lot_size'])
        except Exception:
            pass
        return FALLBACK.get(symbol.upper(), 50)

    def get_available_expiries(self, symbol: str) -> list[str]:
        """
        Return sorted list of available expiry dates for *symbol* from Kite,
        formatted as 'DD-MMM-YYYY'.
        """
        try:
            instruments = self._get_instruments('NFO')
            expiry_set = set()
            today = datetime.now().date()
            for inst in instruments:
                if inst.get('name', '').upper() != symbol.upper():
                    continue
                if inst.get('instrument_type') not in ('CE', 'PE'):
                    continue
                exp = inst.get('expiry')
                if exp and exp >= today:
                    expiry_set.add(exp)
            sorted_expiries = sorted(expiry_set)
            return [d.strftime('%d-%b-%Y').upper() for d in sorted_expiries]
        except Exception as e:
            st.warning(f"Could not fetch expiries from Kite: {e}")
            return []

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_spot_price(self, symbol: str) -> float | None:
        """Get current spot price."""
        try:
            key = f'NSE:{symbol}'
            quote = self.kite.quote(key)
            return float(quote[key]['last_price'])
        except Exception as e:
            st.error(f"Error fetching spot price: {e}")
            return None

    def get_option_chain(self, symbol: str, expiry: str,
                         risk_free_rate: float = 0.07):
        """
        Fetch option chain from Kite NFO for *symbol* and *expiry*.

        Parameters
        ----------
        symbol : str   e.g. 'NIFTY'
        expiry : str   e.g. '15-MAY-2025'
        risk_free_rate : float  annual rate as decimal

        Returns
        -------
        (pd.DataFrame, float)  options dataframe + spot price
        """
        try:
            instruments = self._get_instruments('NFO')

            # Parse target expiry to date
            target_expiry = datetime.strptime(expiry, '%d-%b-%Y').date()

            # Filter matching options
            matching = [
                i for i in instruments
                if (i.get('name', '').upper() == symbol.upper()
                    and i.get('instrument_type') in ('CE', 'PE')
                    and i.get('expiry') == target_expiry)
            ]

            if not matching:
                st.warning(f"No instruments found for {symbol} expiry {expiry}")
                return None, None

            # Build tradingsymbol list for quote API (max 500 per call)
            ts_list = [f'NFO:{i["tradingsymbol"]}' for i in matching]
            quotes = {}
            for i in range(0, len(ts_list), 450):
                chunk = ts_list[i:i + 450]
                quotes.update(self.kite.quote(chunk))

            # Spot price
            spot_price = self.get_spot_price(symbol)
            if spot_price is None:
                return None, None

            # Time to expiry (years)
            today = datetime.now()
            dte = max((datetime.combine(target_expiry,
                       datetime.min.time()) - today).total_seconds() / (365 * 86400),
                      1 / 365)

            option_rows = []
            for inst in matching:
                key = f'NFO:{inst["tradingsymbol"]}'
                q = quotes.get(key, {})
                if not q:
                    continue

                ltp = float(q.get('last_price', 0))
                oi = int(q.get('oi', 0))
                volume = int(q.get('volume', 0))
                strike = float(inst['strike'])
                opt_type = inst['instrument_type']  # 'CE' or 'PE'

                # Compute IV from LTP
                iv = calculate_iv_from_ltp(
                    spot_price, strike, dte, risk_free_rate,
                    ltp, 'call' if opt_type == 'CE' else 'put'
                )

                depth = q.get('depth', {})
                bid_qty = (depth.get('buy', [{}])[0].get('quantity', 0)
                           if depth.get('buy') else 0)
                ask_qty = (depth.get('sell', [{}])[0].get('quantity', 0)
                           if depth.get('sell') else 0)

                option_rows.append({
                    'strike':    strike,
                    'expiry':    expiry,
                    'type':      opt_type,
                    'oi':        oi,
                    'oi_change': int(q.get('oi_day_high', 0)) - int(q.get('oi_day_low', 0)),
                    'volume':    volume,
                    'iv':        round(iv * 100, 2),   # store as %
                    'ltp':       ltp,
                    'change':    float(q.get('net_change', 0)),
                    'bid_qty':   bid_qty,
                    'ask_qty':   ask_qty,
                })

            if not option_rows:
                return None, None

            df = pd.DataFrame(option_rows)
            df = df.sort_values('strike').reset_index(drop=True)
            return df, spot_price

        except Exception as e:
            st.error(f"Error fetching Kite option chain: {e}")
            return None, None


# ---------------------------------------------------------------------------
# Streamlit session helper
# ---------------------------------------------------------------------------

def init_kite_session():
    """Initialise Kite session state variables."""
    if 'kite_manager' not in st.session_state:
        st.session_state.kite_manager = None
        st.session_state.kite_authenticated = False
    return st.session_state.kite_manager
