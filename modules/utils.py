"""
Utility functions for GEX Analyzer

Key additions vs original
--------------------------
* get_next_expiry_for_symbol(symbol)  – respects each index's expiry weekday
  NIFTY      → Thursday (3)
  BANKNIFTY  → Wednesday (2)
  FINNIFTY   → Tuesday  (1)
  MIDCPNIFTY → Monday   (0)

* get_lot_size(symbol, kite_manager)  – fetches from Kite when connected,
  falls back to SEBI-current defaults

* get_expiries_for_symbol(symbol, kite_manager)  – returns Kite expiries when
  connected, otherwise falls back to computed weekly/monthly dates

* All previous helpers retained unchanged.
"""

import pandas as pd
from datetime import datetime, timedelta
import calendar


# ---------------------------------------------------------------------------
# Expiry weekday per index  (0 = Monday … 6 = Sunday)
# ---------------------------------------------------------------------------
_EXPIRY_WEEKDAY = {
    'NIFTY':      3,   # Thursday
    'BANKNIFTY':  2,   # Wednesday
    'FINNIFTY':   1,   # Tuesday
    'MIDCPNIFTY': 0,   # Monday
}
_DEFAULT_EXPIRY_WEEKDAY = 3   # Thursday if unknown


# ---------------------------------------------------------------------------
# Lot sizes – SEBI / NSE current values (as of May 2025)
# Update these when NSE revises lot sizes.
# ---------------------------------------------------------------------------
_LOT_SIZES = {
    'NIFTY':      75,
    'BANKNIFTY':  35,
    'FINNIFTY':   65,
    'MIDCPNIFTY': 120,
}


def get_lot_size(symbol: str, kite_manager=None) -> int:
    """
    Return the lot size for *symbol*.

    If *kite_manager* is supplied and connected, fetch from Kite instruments
    (authoritative source).  Otherwise use the local fallback table.
    """
    if kite_manager is not None:
        try:
            lot = kite_manager.get_lot_size(symbol)
            if lot and lot > 0:
                return lot
        except Exception:
            pass
    return _LOT_SIZES.get(symbol.upper(), 50)


# ---------------------------------------------------------------------------
# Next expiry helpers
# ---------------------------------------------------------------------------

def _next_weekday(from_date: datetime, weekday: int) -> datetime:
    """Return the next *weekday* (0=Mon … 6=Sun) on or after *from_date*."""
    days_ahead = (weekday - from_date.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7          # if today is the weekday, go to next occurrence
    return from_date + timedelta(days=days_ahead)


def get_next_expiry_for_symbol(symbol: str, expiry_type: str = 'weekly') -> str:
    """
    Return the next expiry date for *symbol* in 'DD-MMM-YYYY' format.

    Parameters
    ----------
    symbol : str        e.g. 'NIFTY', 'BANKNIFTY'
    expiry_type : str   'weekly' or 'monthly'
    """
    today = datetime.now()
    weekday = _EXPIRY_WEEKDAY.get(symbol.upper(), _DEFAULT_EXPIRY_WEEKDAY)

    if expiry_type == 'weekly':
        expiry = _next_weekday(today, weekday)
    else:
        # Last occurrence of *weekday* in the current month
        last_day = calendar.monthrange(today.year, today.month)[1]
        candidate = datetime(today.year, today.month, last_day)
        # Walk backwards to find the last weekday
        while candidate.weekday() != weekday:
            candidate -= timedelta(days=1)
        # If we've already passed it, go to next month
        if candidate.date() <= today.date():
            if today.month == 12:
                nxt = datetime(today.year + 1, 1, 1)
            else:
                nxt = datetime(today.year, today.month + 1, 1)
            last_day = calendar.monthrange(nxt.year, nxt.month)[1]
            candidate = datetime(nxt.year, nxt.month, last_day)
            while candidate.weekday() != weekday:
                candidate -= timedelta(days=1)
        expiry = candidate

    return expiry.strftime('%d-%b-%Y').upper()


def get_next_expiry(expiry_type='weekly', symbol='NIFTY') -> str:
    """Backward-compatible wrapper."""
    return get_next_expiry_for_symbol(symbol, expiry_type)


def get_expiries_for_symbol(symbol: str, kite_manager=None,
                             expiry_type: str = 'weekly',
                             num_expiries: int = 8) -> list[str]:
    """
    Return a list of upcoming expiry dates for *symbol*.

    Preference order:
    1. Kite instruments (authoritative, actual calendar)
    2. Computed dates based on known weekday rules
    """
    # Try Kite first
    if kite_manager is not None:
        try:
            expiries = kite_manager.get_available_expiries(symbol)
            if expiries:
                # Separate into weekly (all) and monthly (last of month)
                if expiry_type == 'monthly':
                    monthly = []
                    for e in expiries:
                        d = datetime.strptime(e, '%d-%b-%Y')
                        # Last expiry of a calendar month
                        next_d = d + timedelta(days=7)
                        if next_d.month != d.month:
                            monthly.append(e)
                    return monthly[:num_expiries] if monthly else expiries[:num_expiries]
                return expiries[:num_expiries]
        except Exception:
            pass

    # Fallback: compute dates
    today = datetime.now()
    weekday = _EXPIRY_WEEKDAY.get(symbol.upper(), _DEFAULT_EXPIRY_WEEKDAY)
    expiries = []
    current = today

    if expiry_type == 'weekly':
        for _ in range(num_expiries):
            expiry = _next_weekday(current, weekday)
            expiries.append(expiry.strftime('%d-%b-%Y').upper())
            current = expiry + timedelta(days=1)
    else:
        for _ in range(num_expiries):
            # Last weekday of current month
            last_day = calendar.monthrange(current.year, current.month)[1]
            candidate = datetime(current.year, current.month, last_day)
            while candidate.weekday() != weekday:
                candidate -= timedelta(days=1)
            if candidate.date() <= current.date():
                if current.month == 12:
                    current = datetime(current.year + 1, 1, 1)
                else:
                    current = datetime(current.year, current.month + 1, 1)
                last_day = calendar.monthrange(current.year, current.month)[1]
                candidate = datetime(current.year, current.month, last_day)
                while candidate.weekday() != weekday:
                    candidate -= timedelta(days=1)
            expiries.append(candidate.strftime('%d-%b-%Y').upper())
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1)
            else:
                current = datetime(current.year, current.month + 1, 1)

    return expiries


# ---------------------------------------------------------------------------
# Remaining helpers (unchanged from original)
# ---------------------------------------------------------------------------

def get_atm_strike(spot_price: float, strike_interval: int = 50) -> int:
    return round(spot_price / strike_interval) * strike_interval


def format_number(num: float) -> str:
    if abs(num) >= 10_000_000:
        return f"₹{num / 10_000_000:.2f}Cr"
    elif abs(num) >= 100_000:
        return f"₹{num / 100_000:.2f}L"
    else:
        return f"₹{num:,.0f}"


def calculate_time_to_expiry(expiry_date_str: str) -> float:
    """Return time to expiry in years (minimum 1 day = 1/365)."""
    try:
        expiry_date = datetime.strptime(expiry_date_str, '%d-%b-%Y')
        days = (expiry_date - datetime.now()).days
        return max(days / 365.0, 1 / 365)
    except Exception:
        return 1 / 365


def filter_strikes(df, spot_price: float, range_pct: int = 10):
    """Filter strikes within *range_pct* % of spot price."""
    lo = spot_price * (1 - range_pct / 100)
    hi = spot_price * (1 + range_pct / 100)
    return df[(df['strike'] >= lo) & (df['strike'] <= hi)]


def get_available_expiries(symbol: str = 'NIFTY',
                            kite_manager=None) -> list[str]:
    """Backward-compatible wrapper around get_expiries_for_symbol."""
    return get_expiries_for_symbol(symbol, kite_manager)
