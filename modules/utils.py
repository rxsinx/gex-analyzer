"""
Utility functions for GEX Analyzer

All instrument metadata (lot size, strike interval, tick size, expiry schedule)
are derived from Kite instruments when available.  Fallback values are only
used when Kite is not connected and are clearly labelled as estimates.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# NSE expiry weekday rules  (0=Mon … 6=Sun)
# Source: NSE circulars as at May 2025
# BANKNIFTY moved to monthly-only in Sept 2023; weekly flag set to False.
# ---------------------------------------------------------------------------
_EXPIRY_RULES: dict[str, dict] = {
    "NIFTY": {
        "weekday":      3,      # Thursday
        "has_weekly":   True,
    },
    "BANKNIFTY": {
        "weekday":      2,      # Wednesday
        "has_weekly":   False,  # monthly only as of Sept 2023
    },
    "FINNIFTY": {
        "weekday":      1,      # Tuesday
        "has_weekly":   True,
    },
    "MIDCPNIFTY": {
        "weekday":      0,      # Monday
        "has_weekly":   True,
    },
    "SENSEX": {
        "weekday":      4,      # Friday  (BSE)
        "has_weekly":   True,
    },
    "BANKEX": {
        "weekday":      2,      # Wednesday (BSE)
        "has_weekly":   True,
    },
}
_DEFAULT_RULE = {"weekday": 3, "has_weekly": True}

# Fallback strike intervals (estimate only; real value from Kite instruments)
_FALLBACK_STRIKE_INTERVAL: dict[str, float] = {
    "NIFTY":      50.0,
    "BANKNIFTY":  100.0,
    "FINNIFTY":   50.0,
    "MIDCPNIFTY": 25.0,
    "SENSEX":     100.0,
    "BANKEX":     100.0,
}

# Fallback lot sizes (estimate; real value from Kite instruments)
_FALLBACK_LOT_SIZE: dict[str, int] = {
    "NIFTY":      75,
    "BANKNIFTY":  35,
    "FINNIFTY":   65,
    "MIDCPNIFTY": 120,
}

# Rough default spot prices for sample-data generation only
_FALLBACK_SPOT: dict[str, float] = {
    "NIFTY":      24_500.0,
    "BANKNIFTY":  52_000.0,
    "FINNIFTY":   24_000.0,
    "MIDCPNIFTY": 12_000.0,
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
    """
    Return True if *symbol* has weekly expiries.
    Kite instruments are the authoritative source; falls back to _EXPIRY_RULES.
    """
    if kite_manager is not None:
        try:
            return kite_manager.has_weekly_expiry(symbol)
        except Exception:
            pass
    return _EXPIRY_RULES.get(symbol.upper(), _DEFAULT_RULE)["has_weekly"]


def get_expiry_weekday(symbol: str) -> int:
    """Return the weekday (0=Mon…6=Sun) on which *symbol* expires."""
    return _EXPIRY_RULES.get(symbol.upper(), _DEFAULT_RULE)["weekday"]


def get_next_expiry_for_symbol(symbol: str,
                                expiry_type: str = "weekly") -> str:
    """
    Compute the next expiry date for *symbol* according to NSE rules.

    Parameters
    ----------
    symbol       : 'NIFTY', 'BANKNIFTY', etc.
    expiry_type  : 'weekly' or 'monthly'

    Returns
    -------
    'DD-MMM-YYYY' string
    """
    today   = datetime.now()
    rule    = _EXPIRY_RULES.get(symbol.upper(), _DEFAULT_RULE)
    weekday = rule["weekday"]

    # BANKNIFTY has no weekly expiry – always use monthly
    if symbol.upper() == "BANKNIFTY":
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
    2. Computed from NSE weekday rules

    BANKNIFTY always returns monthly dates (no weekly expiry on NSE).
    """
    sym = symbol.upper()

    # Force monthly for BANKNIFTY
    if sym == "BANKNIFTY":
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
