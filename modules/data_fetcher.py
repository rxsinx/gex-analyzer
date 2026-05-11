"""
Multi-source data fetching module
Supports: NSE (nselib), Kite Connect v3, Sample Data

All instrument metadata (lot size, strike interval, default spot) are
obtained from Kite or derived from live data.  Nothing is hardcoded
beyond clearly labelled last-resort guards.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

try:
    from nselib import capital_market as _cm
    _NSELIB = True
except ImportError:
    _NSELIB = False

import streamlit as st

# ---------------------------------------------------------------------------
# NSE index name → nselib / market watch key
# ---------------------------------------------------------------------------
_NSE_INDEX_NAME: dict[str, str] = {
    "NIFTY":      "NIFTY 50",
    "BANKNIFTY":  "NIFTY BANK",
    "FINNIFTY":   "NIFTY FIN SERVICE",
    "MIDCPNIFTY": "NIFTY MIDCAP SELECT",
}

# ---------------------------------------------------------------------------
# Black-Scholes helpers (local copy to avoid circular imports)
# ---------------------------------------------------------------------------

def _bs_price(S: float, K: float, T: float, r: float,
              sigma: float, opt: str = "call") -> float:
    if T <= 0 or sigma <= 0:
        return max((S - K) if opt == "call" else (K - S), 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if opt == "call":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def _iv_from_ltp(S: float, K: float, T: float, r: float,
                 ltp: float, opt: str = "call") -> float:
    """Return IV as percentage (e.g. 15.0 for 15 %).  Returns 0.0 on failure."""
    if T <= 0 or ltp <= 0:
        return 0.0
    intrinsic = max((S - K) if opt == "call" else (K - S), 0.0)
    if ltp <= intrinsic + 1e-6:
        return 0.1
    try:
        iv = brentq(
            lambda s: _bs_price(S, K, T, r, s, opt) - ltp,
            1e-4, 5.0, xtol=1e-6, maxiter=300,
        )
        return round(max(0.001, iv) * 100, 4)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Spot price
# ---------------------------------------------------------------------------

def get_live_spot_price(symbol: str = "NIFTY",
                         source: str = "nselib",
                         kite_manager=None) -> Optional[float]:
    """Return live spot price or None on failure."""
    try:
        if source == "kite" and kite_manager:
            return kite_manager.get_spot_ltp(symbol)

        if not _NSELIB:
            return None
        target = _NSE_INDEX_NAME.get(symbol.upper(), "NIFTY 50")
        data   = _cm.market_watch_all_indices()
        for item in data.get("data", []):
            if item.get("index") == target:
                return float(item["last"])
        return None
    except Exception as exc:
        print(f"[get_live_spot_price] {exc}")
        return None


# ---------------------------------------------------------------------------
# Option chain from NSE (nselib)
# ---------------------------------------------------------------------------

def fetch_option_chain(
    symbol: str = "NIFTY",
    expiry_date: Optional[str] = None,
    source: str = "nselib",
    kite_manager=None,
    risk_free_rate: float = 0.07,
) -> tuple[Optional[pd.DataFrame], Optional[float]]:
    """
    Fetch option chain from the chosen source.

    Returns (DataFrame, spot_price) or (None, None) on failure.
    """
    try:
        # ── Kite ────────────────────────────────────────────────────────────
        if source == "kite" and kite_manager:
            return kite_manager.get_option_chain(
                symbol, expiry_date, risk_free_rate
            )

        # ── NSE via nselib ───────────────────────────────────────────────────
        if not _NSELIB:
            st.warning("nselib is not installed.")
            return None, None

        sym = symbol.upper()
        if sym == "NIFTY":
            raw = _cm.nifty_option_chain()
        elif sym == "BANKNIFTY":
            raw = _cm.bank_nifty_option_chain()
        elif sym == "FINNIFTY":
            raw = _cm.finnifty_option_chain()
        else:
            st.warning(f"nselib does not support {symbol}.")
            return None, None

        spot = float(raw["records"]["underlyingValue"])

        # DTE for IV calculation
        dte = 1 / 365
        if expiry_date:
            try:
                exp_dt = datetime.strptime(expiry_date, "%d-%b-%Y")
                dte = max(
                    (exp_dt - datetime.now()).total_seconds() / (365 * 86_400),
                    1 / 365,
                )
            except Exception:
                pass

        rows: list[dict] = []
        for item in raw["records"].get("data", []):
            strike = float(item["strikePrice"])
            expiry = item["expiryDate"]

            if expiry_date and expiry.upper() != expiry_date.upper():
                continue

            for itype, key in [("CE", "CE"), ("PE", "PE")]:
                if key not in item:
                    continue
                d = item[key]

                ltp = float(d.get("lastPrice", 0) or 0)
                oi  = int(d.get("openInterest", 0) or 0)
                vol = int(d.get("totalTradedVolume", 0) or 0)

                # Use NSE-reported IV when available; else back-solve from LTP
                nse_iv = float(d.get("impliedVolatility", 0) or 0)
                iv_pct = (
                    nse_iv if nse_iv > 0
                    else _iv_from_ltp(
                        spot, strike, dte, risk_free_rate,
                        ltp, "call" if itype == "CE" else "put",
                    )
                )

                rows.append({
                    "strike":    strike,
                    "expiry":    expiry,
                    "type":      itype,
                    "oi":        oi,
                    "oi_change": int(d.get("changeinOpenInterest", 0) or 0),
                    "volume":    vol,
                    "iv":        iv_pct,
                    "ltp":       ltp,
                    "change":    float(d.get("change", 0) or 0),
                    "bid_qty":   int(d.get("bidQty", 0) or 0),
                    "ask_qty":   int(d.get("askQty", 0) or 0),
                })

        if not rows:
            return None, None

        df = (
            pd.DataFrame(rows)
            .sort_values("strike")
            .reset_index(drop=True)
        )
        return df, spot

    except Exception as exc:
        print(f"[fetch_option_chain] {exc}")
        return None, None


# ---------------------------------------------------------------------------
# Market status / index quote (NSE)
# ---------------------------------------------------------------------------

def get_market_status() -> dict:
    base = {"market_state": "Unknown",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    try:
        if not _NSELIB:
            return base
        data = _cm.market_status()
        base["market_state"] = data.get("marketState", "Unknown")
        return base
    except Exception:
        return base


def get_index_quote(symbol: str = "NIFTY") -> Optional[dict]:
    """Return OHLC + change for *symbol* from NSE."""
    try:
        if not _NSELIB:
            return None
        target = _NSE_INDEX_NAME.get(symbol.upper(), "NIFTY 50")
        data   = _cm.market_watch_all_indices()
        for item in data.get("data", []):
            if item.get("index") == target:
                return {
                    "last":    float(item.get("last", 0)),
                    "change":  float(item.get("percentChange", 0)),
                    "open":    float(item.get("open", 0)),
                    "high":    float(item.get("high", 0)),
                    "low":     float(item.get("low", 0)),
                    "close":   float(item.get("previousClose", 0)),
                }
        return None
    except Exception as exc:
        print(f"[get_index_quote] {exc}")
        return None


# ---------------------------------------------------------------------------
# Sample / fallback data
# ---------------------------------------------------------------------------

def generate_sample_data(
    symbol: str = "NIFTY",
    spot_price: Optional[float] = None,
    expiry_date: Optional[str] = None,
    kite_manager=None,
) -> tuple[pd.DataFrame, float]:
    """
    Generate realistic sample option chain data.

    * Strike interval is fetched from Kite when available.
    * LTP is computed from Black-Scholes → consistent with strike / IV.
    * Expiry uses the real next expiry from utils (not hardcoded).
    """
    from modules.utils import (
        get_next_expiry_for_symbol,
        get_strike_interval,
        get_fallback_spot,
        calculate_time_to_expiry,
    )

    if spot_price is None:
        spot_price = get_live_spot_price(symbol) or get_fallback_spot(symbol)

    if expiry_date is None:
        expiry_date = get_next_expiry_for_symbol(symbol)

    interval   = get_strike_interval(symbol, expiry_date, kite_manager)
    num_strikes = 40
    half        = num_strikes // 2

    atm     = round(spot_price / interval) * interval
    strikes = np.arange(
        atm - half * interval,
        atm + (half + 1) * interval,
        interval,
    )

    T   = calculate_time_to_expiry(expiry_date)
    r   = 0.07
    rng = np.random.default_rng(seed=42)

    rows: list[dict] = []
    for strike in strikes:
        moneyness = abs(strike - spot_price) / spot_price
        base_oi   = max(int(500_000 * np.exp(-moneyness * 15)), 5_000)

        # Realistic IV smile with put skew
        call_iv = max(0.05, 0.14 + moneyness * 0.08 + rng.uniform(-0.01, 0.01))
        put_iv  = max(0.05, 0.14 + moneyness * 0.10 + rng.uniform(-0.01, 0.01))

        call_ltp = max(_bs_price(spot_price, strike, T, r, call_iv, "call"), 0.05)
        put_ltp  = max(_bs_price(spot_price, strike, T, r, put_iv,  "put"),  0.05)

        for itype, iv, ltp in [
            ("CE", call_iv, call_ltp),
            ("PE", put_iv,  put_ltp),
        ]:
            rows.append({
                "strike":    float(strike),
                "expiry":    expiry_date,
                "type":      itype,
                "oi":        int(base_oi * rng.uniform(0.8, 1.2)),
                "oi_change": int(rng.integers(-5_000, 5_000)),
                "volume":    int(rng.integers(1_000, 50_000)),
                "iv":        round(iv * 100, 2),
                "ltp":       round(ltp, 2),
                "change":    round(float(rng.uniform(-10, 10)), 2),
                "bid_qty":   int(rng.integers(50, 500)),
                "ask_qty":   int(rng.integers(50, 500)),
            })

    return pd.DataFrame(rows), float(spot_price)
