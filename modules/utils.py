"""
Utility functions for GEX Analyzer

All instrument metadata (lot size, strike interval, tick size, expiry schedule)
are derived from Kite instruments when available.  Fallback values are only
used when Kite is not connected and are clearly labelled as estimates.

CORRECTED EXPIRY RULES (as of Jan 2025):
- NIFTY:      Tuesday,    both weekly & monthly
- BANKNIFTY:  Tuesday,    monthly only
- FINNIFTY:   Tuesday,    monthly only
- MIDCPNIFTY: Tuesday,    monthly only
- SENSEX:     Thursday,   both weekly & monthly
- BANKEX:     Thursday,   monthly only
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# CORRECTED NSE/BSE expiry weekday rules (0=Mon … 6=Sun)
# Updated: Jan 2025
# All NSE indices expire on TUESDAY (not mixed days)
# All BSE indices: SENSEX on THURSDAY (weekly+monthly), BANKEX on THURSDAY (monthly)
# ---------------------------------------------------------------------------
_EXPIRY_RULES: dict[str, dict] = {
    "NIFTY": {
        "weekday":      1,      # TUESDAY (CORRECTED from Thursday)
        "has_weekly":   True,   # Both weekly AND monthly
    },
    "BANKNIFTY": {
        "weekday":      1,      # TUESDAY (CORRECTED from Wednesday)
        "has_weekly":   False,  # Monthly only (CORRECTED from has_weekly=True)
    },
    "FINNIFTY": {
        "weekday":      1,      # TUESDAY (same, but clarified)
        "has_weekly":   False,  # Monthly only (CORRECTED from True)
    },
    "MIDCPNIFTY": {
        "weekday":      1,      # TUESDAY (CORRECTED from Monday)
        "has_weekly":   False,  # Monthly only (CORRECTED from True)
    },
    "SENSEX": {
        "weekday":      3,      # THURSDAY (same)
        "has_weekly":   True,   # Both weekly AND monthly (same)
    },
    "BANKEX": {
        "weekday":      3,      # THURSDAY (CORRECTED from Wednesday)
        "has_weekly":   False,  # Monthly only (same)
    },
}
_DEFAULT_RULE = {"weekday": 1, "has_weekly": True}

# Fallback strike intervals (estimate only; real value from Kite instruments)
_FALLBACK_STRIKE_INTERVAL: dict[str, float] = {
    "NIFTY":      50.0,
    "BANKNIFTY":  100.0,
    "FINNIFTY":   50.0,
    "MIDCPNIFTY": 25.0,
    "SENSEX":     100.0,      # BSE typically uses 100 point intervals
    "BANKEX":     100.0,      # BSE typically uses 100 point intervals
}

# CORRECTED Fallback lot sizes
_FALLBACK_LOT_SIZE: dict[str, int] = {
    "NIFTY":      65,         # CORRECTED from 75
    "BANKNIFTY":  30,         # CORRECTED from 35
    "FINNIFTY":   60,         # CORRECTED from 65
    "MIDCPNIFTY": 120,        # Same
    "SENSEX":     20,         # Same
    "BANKEX":     30,         # Same
}

# Rough default spot prices for sample-data generation only
_FALLBACK_SPOT: dict[str, float] = {
    "NIFTY":      24_500.0,
    "BANKNIFTY":  52_000.0,
    "FINNIFTY":   24_000.0,
    "MIDCPNIFTY": 12_000.0,
    "SENSEX":     75_000.0,
    "BANKEX":     45_000.0,
}


# ---------------------------------------------------------------------------
# Expiry helpers
# ---------------------------------------------------------------------------

def _next_occurrence(from_dt: datetime, weekday: int) -> datetime:
    """Return the **next** occurrence of *weekday* strictly after *from_dt*."""
    days = (weekday - from_dt.weekday()) % 7
    if days == 0:
        days = 7
    return from_dt + timedelta(days=days)


def _last_occurrence_in_month(year: int, month: int,
                               weekday: int) -> datetime:
    """Return the last *weekday* in *year*/*month*."""
    last_day = calendar.monthrange(year, month)[1]
    candidate = datetime(year, month, last_day)
    while candidate.weekday() != weekday:
        candidate -= timedelta(days=1)
    return candidate


def has_weekly_expiry(symbol: str, kite_manager=None) -> bool:
    from modules.utils import _EXPIRY_RULES, _DEFAULT_RULE
    rule = _EXPIRY_RULES.get(symbol.upper(), _DEFAULT_RULE)
    return bool(rule.get("has_weekly", True))
    """
    Return True if *symbol* has weekly expiries.
    Kite instruments are the authoritative source; falls back to _EXPIRY_RULES.
    
    CORRECTED RULES:
    - NIFTY:      Weekly ✅
    - BANKNIFTY:  Monthly only ❌
    - FINNIFTY:   Monthly only ❌
    - MIDCPNIFTY: Monthly only ❌
    - SENSEX:     Weekly ✅
    - BANKEX:     Monthly only ❌
    """
    if kite_manager is not None:
        try:
            return kite_manager.has_weekly_expiry(symbol)
        except Exception:
            pass
    return _EXPIRY_RULES.get(symbol.upper(), _DEFAULT_RULE)["has_weekly"]


def get_expiry_weekday(symbol: str) -> int:
    """Return the weekday (0=Mon…6=Sun) on which *symbol* expires.
    
    CORRECTED:
    - All NSE indices: Tuesday (1)
    - SENSEX: Thursday (3)
    - BANKEX: Thursday (3)
    """
    return _EXPIRY_RULES.get(symbol.upper(), _DEFAULT_RULE)["weekday"]


def get_next_expiry_for_symbol(symbol: str,
                                expiry_type: str = "weekly") -> str:
    """
    Compute the next expiry date for *symbol* according to NSE/BSE rules.

    Parameters
    ----------
    symbol       : 'NIFTY', 'BANKNIFTY', 'SENSEX', 'BANKEX', etc.
    expiry_type  : 'weekly' or 'monthly'

    Returns
    -------
    'DD-MMM-YYYY' string
    
    CORRECTED LOGIC:
    - NIFTY only: supports weekly
    - SENSEX only: supports weekly
    - All others: monthly only
    """
    today   = datetime.now()
    rule    = _EXPIRY_RULES.get(symbol.upper(), _DEFAULT_RULE)
    weekday = rule["weekday"]

    # Force monthly for indices without weekly expiry
    # CORRECTED: Only NIFTY and SENSEX have weekly
    if symbol.upper() not in ["NIFTY", "SENSEX"]:
        expiry_type = "monthly"

    if expiry_type == "weekly":
        expiry = _next_occurrence(today, weekday)
    else:
        # Last weekday of the current month
        candidate = _last_occurrence_in_month(today.year, today.month, weekday)
        if candidate.date() <= today.date():
            # Already passed – move to next month
            if today.month == 12:
                candidate = _last_occurrence_in_month(today.year + 1, 1, weekday)
            else:
                candidate = _last_occurrence_in_month(today.year, today.month + 1, weekday)
        expiry = candidate

    return expiry.strftime("%d-%b-%Y").upper()


# backward-compatible alias
def get_next_expiry(expiry_type: str = "weekly",
                    symbol: str = "NIFTY") -> str:
    return get_next_expiry_for_symbol(symbol, expiry_type)


def get_expiries_for_symbol(
    symbol: str,
    kite_manager=None,
    expiry_type: str = "weekly",
    num: int = 12,
) -> list[str]:
    """
    Return upcoming expiry dates for *symbol*.

    Priority:
    1. Kite instruments (authoritative – includes holiday adjustments)
    2. Computed from NSE/BSE weekday rules

    CORRECTED:
    - Only NIFTY and SENSEX have weekly expiries
    - All others are monthly only
    """
    sym = symbol.upper()

    # Force monthly for indices without weekly expiry
    # CORRECTED: Only NIFTY and SENSEX support weekly
    if sym not in ["NIFTY", "SENSEX"]:
        expiry_type = "monthly"

    # ── Try Kite ─────────────────────────────────────────────────────────────
    if kite_manager is not None:
        try:
            all_expiries = kite_manager.get_available_expiries(symbol)
            if all_expiries:
                if expiry_type == "monthly":
                    # Keep only the last expiry of each calendar month
                    monthly = []
                    for e in all_expiries:
                        d      = datetime.strptime(e, "%d-%b-%Y")
                        next_d = d + timedelta(days=7)
                        if next_d.month != d.month:
                            monthly.append(e)
                    result = monthly[:num] if monthly else all_expiries[:num]
                else:
                    result = all_expiries[:num]
                return result
        except Exception:
            pass

    # ── Compute fallback ──────────────────────────────────────────────────────
    weekday = get_expiry_weekday(sym)
    today   = datetime.now()
    result: list[str] = []
    cursor  = today

    if expiry_type == "weekly":
        for _ in range(num):
            exp = _next_occurrence(cursor, weekday)
            result.append(exp.strftime("%d-%b-%Y").upper())
            cursor = exp + timedelta(days=1)
    else:
        seen_months: set[tuple[int, int]] = set()
        # Go through upcoming months until we have enough
        yr, mo = today.year, today.month
        while len(result) < num:
            candidate = _last_occurrence_in_month(yr, mo, weekday)
            if candidate.date() > today.date() and (yr, mo) not in seen_months:
                result.append(candidate.strftime("%d-%b-%Y").upper())
                seen_months.add((yr, mo))
            mo += 1
            if mo > 12:
                mo, yr = 1, yr + 1

    return result


def get_available_expiries(symbol: str = "NIFTY",
                            kite_manager=None) -> list[str]:
    """Backward-compatible wrapper."""
    return get_expiries_for_symbol(symbol, kite_manager)


# ---------------------------------------------------------------------------
# Lot size / strike interval
# ---------------------------------------------------------------------------

def get_lot_size(symbol: str, kite_manager=None) -> int:
    """
    Return lot size.  Kite instruments are authoritative.
    Falls back to _FALLBACK_LOT_SIZE if Kite unavailable.
    
    CORRECTED LOT SIZES:
    - NIFTY:      65 qty
    - BANKNIFTY:  30 qty
    - FINNIFTY:   60 qty
    - MIDCPNIFTY: 120 qty
    - SENSEX:     20 qty
    - BANKEX:     30 qty
    """
    if kite_manager is not None:
        try:
            lot = kite_manager.get_lot_size(symbol)
            if lot and lot > 0:
                return lot
        except Exception:
            pass
    return _FALLBACK_LOT_SIZE.get(symbol.upper(), 50)


def get_strike_interval(symbol: str, expiry: str | None = None,
                         kite_manager=None) -> float:
    """
    Return the strike interval for *symbol*.
    Kite instruments are authoritative.
    Falls back to _FALLBACK_STRIKE_INTERVAL.
    
    NSE Indices:
      NIFTY:      50
      BANKNIFTY:  100
      FINNIFTY:   50
      MIDCPNIFTY: 25
    
    BSE Indices:
      SENSEX:     100
      BANKEX:     100
    """
    if kite_manager is not None:
        try:
            iv = kite_manager.get_strike_interval(symbol, expiry)
            if iv and iv > 0:
                return iv
        except Exception:
            pass
    return _FALLBACK_STRIKE_INTERVAL.get(symbol.upper(), 50.0)


def get_fallback_spot(symbol: str) -> float:
    """Last-resort spot price for sample data generation."""
    return _FALLBACK_SPOT.get(symbol.upper(), 24_500.0)


# ---------------------------------------------------------------------------
# ATM / formatting / filtering helpers
# ---------------------------------------------------------------------------

def get_atm_strike(spot: float, interval: float) -> float:
    """Round spot to the nearest *interval*."""
    return round(spot / interval) * interval


def format_number(num: float) -> str:
    """Format large numbers with ₹ prefix and Cr/L suffix."""
    a = abs(num)
    if a >= 1e7:
        return f"₹{num/1e7:.2f}Cr"
    if a >= 1e5:
        return f"₹{num/1e5:.2f}L"
    return f"₹{num:,.0f}"


def calculate_time_to_expiry(expiry_str: str) -> float:
    """Return time to expiry in years (minimum 1 day)."""
    try:
        exp = datetime.strptime(expiry_str, "%d-%b-%Y")
        days = (exp - datetime.now()).days
        return max(days / 365.0, 1 / 365)
    except Exception:
        return 1 / 365


def filter_strikes(df: pd.DataFrame, spot: float,
                   range_pct: float = 10.0) -> pd.DataFrame:
    """Return rows whose strike is within ±range_pct % of spot."""
    lo = spot * (1 - range_pct / 100)
    hi = spot * (1 + range_pct / 100)
    return df[(df["strike"] >= lo) & (df["strike"] <= hi)].copy()
