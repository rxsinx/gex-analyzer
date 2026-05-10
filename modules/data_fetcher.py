"""
Multi-source data fetching module
Supports: NSE (nselib), Kite Connect, and Sample Data

Changes vs original
-------------------
* Removed hardcoded expiry '30-JAN-2026' from sample data – uses real next expiry
* NSE option chain now propagates actual LTP and IV (with BS-inverse fallback)
* generate_sample_data uses realistic strike interval per symbol
* get_live_spot_price returns None cleanly on failure (no swallowed exceptions)
"""

import pandas as pd
from datetime import datetime
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq

try:
    from nselib import capital_market
    NSELIB_AVAILABLE = True
except ImportError:
    NSELIB_AVAILABLE = False

import streamlit as st


# ---------------------------------------------------------------------------
# IV calculation (same helper as kite_connector – kept local to avoid circular)
# ---------------------------------------------------------------------------

def _bs_price(S, K, T, r, sigma, option_type='call'):
    if T <= 0 or sigma <= 0:
        return max(S - K, 0) if option_type == 'call' else max(K - S, 0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if option_type == 'call':
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def _iv_from_ltp(S, K, T, r, ltp, option_type='call'):
    """Return IV as a percentage (e.g. 15.0 for 15%). Returns 0 on failure."""
    if T <= 0 or ltp <= 0:
        return 0.0
    intrinsic = max(S - K, 0) if option_type == 'call' else max(K - S, 0)
    if ltp <= intrinsic:
        return 0.1
    try:
        iv = brentq(lambda s: _bs_price(S, K, T, r, s, option_type) - ltp,
                    1e-4, 5.0, xtol=1e-6, maxiter=200)
        return round(max(0.001, iv) * 100, 2)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Spot price
# ---------------------------------------------------------------------------

# NSE index name mapping
_NSE_INDEX_MAP = {
    'NIFTY':      'NIFTY 50',
    'BANKNIFTY':  'NIFTY BANK',
    'FINNIFTY':   'NIFTY FIN SERVICE',
    'MIDCPNIFTY': 'NIFTY MIDCAP SELECT',
}

def get_live_spot_price(symbol='NIFTY', source='nselib', kite_manager=None):
    """Return live spot price or None on failure."""
    try:
        if source == 'kite' and kite_manager:
            return kite_manager.get_spot_price(symbol)

        if not NSELIB_AVAILABLE:
            return None

        data = capital_market.market_watch_all_indices()
        target = _NSE_INDEX_MAP.get(symbol.upper(), 'NIFTY 50')
        for item in data.get('data', []):
            if item.get('index') == target:
                return float(item['last'])
        return None
    except Exception as e:
        print(f"[get_live_spot_price] {e}")
        return None


# ---------------------------------------------------------------------------
# Option chain from NSE (nselib)
# ---------------------------------------------------------------------------

def fetch_option_chain(symbol='NIFTY', expiry_date=None,
                       source='nselib', kite_manager=None,
                       risk_free_rate=0.07):
    """
    Fetch option chain from the chosen source.

    Returns
    -------
    (pd.DataFrame, float) – options dataframe + spot price
    Both are None on failure.
    """
    try:
        if source == 'kite' and kite_manager:
            return kite_manager.get_option_chain(symbol, expiry_date, risk_free_rate)

        # --- NSE via nselib ---
        if not NSELIB_AVAILABLE:
            return None, None

        sym_upper = symbol.upper()
        if sym_upper == 'NIFTY':
            oc_data = capital_market.nifty_option_chain()
        elif sym_upper == 'BANKNIFTY':
            oc_data = capital_market.bank_nifty_option_chain()
        elif sym_upper == 'FINNIFTY':
            oc_data = capital_market.finnifty_option_chain()
        else:
            st.warning(f"nselib does not support {symbol}; falling back to sample data.")
            return None, None

        spot_price = float(oc_data['records']['underlyingValue'])

        # Time to expiry for IV calculation
        dte_years = 0.0027  # fallback
        if expiry_date:
            try:
                exp_dt = datetime.strptime(expiry_date, '%d-%b-%Y')
                dte_years = max((exp_dt - datetime.now()).total_seconds() / (365 * 86400),
                                1 / 365)
            except Exception:
                pass

        options_data = []
        for item in oc_data['records'].get('data', []):
            strike = float(item['strikePrice'])
            expiry = item['expiryDate']

            # Filter by expiry if specified
            if expiry_date and expiry.upper() != expiry_date.upper():
                continue

            for opt_type, key in [('CE', 'CE'), ('PE', 'PE')]:
                if key not in item:
                    continue
                d = item[key]

                ltp  = float(d.get('lastPrice', 0) or 0)
                oi   = int(d.get('openInterest', 0) or 0)
                vol  = int(d.get('totalTradedVolume', 0) or 0)

                # IV: use NSE-reported if available, else calculate from LTP
                nse_iv = float(d.get('impliedVolatility', 0) or 0)
                if nse_iv > 0:
                    iv_pct = nse_iv
                else:
                    iv_pct = _iv_from_ltp(
                        spot_price, strike, dte_years,
                        risk_free_rate, ltp,
                        'call' if opt_type == 'CE' else 'put'
                    )

                options_data.append({
                    'strike':    strike,
                    'expiry':    expiry,
                    'type':      opt_type,
                    'oi':        oi,
                    'oi_change': int(d.get('changeinOpenInterest', 0) or 0),
                    'volume':    vol,
                    'iv':        iv_pct,
                    'ltp':       ltp,
                    'change':    float(d.get('change', 0) or 0),
                    'bid_qty':   int(d.get('bidQty', 0) or 0),
                    'ask_qty':   int(d.get('askQty', 0) or 0),
                })

        if not options_data:
            return None, None

        df = pd.DataFrame(options_data)
        df = df.sort_values('strike').reset_index(drop=True)
        return df, spot_price

    except Exception as e:
        print(f"[fetch_option_chain] {e}")
        return None, None


# ---------------------------------------------------------------------------
# Market status & index quote
# ---------------------------------------------------------------------------

def get_market_status():
    """Get current market status."""
    try:
        if not NSELIB_AVAILABLE:
            return {'market_state': 'Unknown',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        data = capital_market.market_status()
        return {
            'market_state': data.get('marketState', 'Unknown'),
            'timestamp':    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
    except Exception:
        return {'market_state': 'Unknown',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}


def get_index_quote(symbol='NIFTY'):
    """Get detailed index quote from NSE."""
    try:
        if not NSELIB_AVAILABLE:
            return None
        data = capital_market.market_watch_all_indices()
        target = _NSE_INDEX_MAP.get(symbol.upper(), 'NIFTY 50')
        for item in data.get('data', []):
            if item.get('index') == target:
                return {
                    'last':           float(item.get('last', 0)),
                    'change':         float(item.get('percentChange', 0)),
                    'open':           float(item.get('open', 0)),
                    'high':           float(item.get('high', 0)),
                    'low':            float(item.get('low', 0)),
                    'previous_close': float(item.get('previousClose', 0)),
                }
        return None
    except Exception as e:
        print(f"[get_index_quote] {e}")
        return None


# ---------------------------------------------------------------------------
# Sample / fallback data  (no hardcoded expiry, no hardcoded lot size)
# ---------------------------------------------------------------------------

# Strike intervals per index
_STRIKE_INTERVAL = {
    'NIFTY': 50, 'BANKNIFTY': 100,
    'FINNIFTY': 50, 'MIDCPNIFTY': 25,
}

# Default spot if live fetch fails
_DEFAULT_SPOT = {
    'NIFTY': 24500, 'BANKNIFTY': 52000,
    'FINNIFTY': 24000, 'MIDCPNIFTY': 12000,
}


def generate_sample_data(symbol='NIFTY', spot_price=None, expiry_date=None):
    """
    Generate realistic-looking sample option chain data.

    * Uses actual (live) spot if provided; falls back to sensible defaults.
    * Expiry date is the real next expiry (from utils), not hardcoded.
    * LTP is computed from Black-Scholes so it is consistent with the strike.
    """
    from modules.utils import get_next_expiry_for_symbol, calculate_time_to_expiry

    if spot_price is None:
        spot_price = get_live_spot_price(symbol) or _DEFAULT_SPOT.get(symbol, 24500)

    if expiry_date is None:
        expiry_date = get_next_expiry_for_symbol(symbol)

    interval = _STRIKE_INTERVAL.get(symbol.upper(), 50)
    num_strikes = 40
    half = num_strikes // 2

    atm = round(spot_price / interval) * interval
    strikes = np.arange(atm - half * interval,
                        atm + half * interval + interval,
                        interval)

    T = calculate_time_to_expiry(expiry_date)
    r = 0.07   # 7% risk-free rate

    rng = np.random.default_rng(seed=42)  # reproducible noise

    options_data = []
    for strike in strikes:
        moneyness = abs(strike - spot_price) / spot_price
        base_oi = max(int(500_000 * np.exp(-moneyness * 15)), 5_000)

        # Skewed IV smile (put skew)
        call_iv = 0.14 + moneyness * 0.08 + rng.uniform(-0.01, 0.01)
        put_iv  = 0.14 + moneyness * 0.10 + rng.uniform(-0.01, 0.01)
        call_iv = max(0.05, call_iv)
        put_iv  = max(0.05, put_iv)

        # LTP from Black-Scholes (realistic)
        call_ltp = max(_bs_price(spot_price, strike, T, r, call_iv, 'call'), 0.05)
        put_ltp  = max(_bs_price(spot_price, strike, T, r, put_iv,  'put'),  0.05)

        call_oi = int(base_oi * rng.uniform(0.8, 1.2))
        put_oi  = int(base_oi * rng.uniform(0.8, 1.2))

        options_data.append({
            'strike':    float(strike),
            'expiry':    expiry_date,
            'type':      'CE',
            'oi':        call_oi,
            'oi_change': int(rng.integers(-5000, 5000)),
            'volume':    int(rng.integers(1000, 50000)),
            'iv':        round(call_iv * 100, 2),
            'ltp':       round(call_ltp, 2),
            'change':    round(float(rng.uniform(-10, 10)), 2),
            'bid_qty':   int(rng.integers(50, 500)),
            'ask_qty':   int(rng.integers(50, 500)),
        })
        options_data.append({
            'strike':    float(strike),
            'expiry':    expiry_date,
            'type':      'PE',
            'oi':        put_oi,
            'oi_change': int(rng.integers(-5000, 5000)),
            'volume':    int(rng.integers(1000, 50000)),
            'iv':        round(put_iv * 100, 2),
            'ltp':       round(put_ltp, 2),
            'change':    round(float(rng.uniform(-10, 10)), 2),
            'bid_qty':   int(rng.integers(50, 500)),
            'ask_qty':   int(rng.integers(50, 500)),
        })

    df = pd.DataFrame(options_data)
    return df, float(spot_price)
