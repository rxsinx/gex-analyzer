"""
Multi-source data fetching module
Supports: NSE (nselib), Kite Connect v3, Sample Data

Key fix vs previous version
----------------------------
KiteError / KiteAuthError / KiteDataError are no longer caught here.
They propagate to app.py which shows them to the user.
Only non-Kite exceptions are caught quietly.
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
from modules.kite_connector import KiteError

_NSE_INDEX_NAME: dict[str, str] = {
    "NIFTY":      "NIFTY 50",
    "BANKNIFTY":  "NIFTY BANK",
    "FINNIFTY":   "NIFTY FIN SERVICE",
    "MIDCPNIFTY": "NIFTY MIDCAP SELECT",
}


def _bs_price(S, K, T, r, sigma, opt="call"):
    if T <= 0 or sigma <= 0:
        return max((S - K) if opt == "call" else (K - S), 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if opt == "call":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def _iv_from_ltp(S, K, T, r, ltp, opt="call"):
    if T <= 0 or ltp <= 0:
        return 0.0
    intrinsic = max((S - K) if opt == "call" else (K - S), 0.0)
    if ltp <= intrinsic + 1e-6:
        return 0.1
    try:
        iv = brentq(lambda s: _bs_price(S, K, T, r, s, opt) - ltp,
                    1e-4, 5.0, xtol=1e-6, maxiter=300)
        return round(max(0.001, iv) * 100, 4)
    except Exception:
        return 0.0


# ── Spot price ───────────────────────────────────────────────────────────────

def get_live_spot_price(symbol="NIFTY", source="nselib", kite_manager=None):
    """Return live spot price or None on failure. KiteErrors propagate."""
    if source == "kite" and kite_manager:
        return kite_manager.get_spot_ltp(symbol)   # KiteError propagates
    try:
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


# ── Option chain ─────────────────────────────────────────────────────────────

def fetch_option_chain(symbol="NIFTY", expiry_date=None,
                       source="nselib", kite_manager=None,
                       risk_free_rate=0.07):
    """
    Fetch option chain.
    For Kite source, KiteError subclasses are allowed to propagate so
    app.py can display them correctly.
    For nselib, non-critical failures return (None, None).
    """
    # ── Kite ─────────────────────────────────────────────────────────────────
    if source == "kite" and kite_manager:
        # KiteError propagates – app.py catches and shows it
        return kite_manager.get_option_chain(symbol, expiry_date, risk_free_rate)

    # ── NSE via nselib ────────────────────────────────────────────────────────
    try:
        if not _NSELIB:
            st.warning("nselib not installed.")
            return None, None

        sym = symbol.upper()
        if   sym == "NIFTY":      raw = _cm.nifty_option_chain()
        elif sym == "BANKNIFTY":  raw = _cm.bank_nifty_option_chain()
        elif sym == "FINNIFTY":   raw = _cm.finnifty_option_chain()
        else:
            st.warning(f"nselib does not support {symbol}.")
            return None, None

        spot = float(raw["records"]["underlyingValue"])
        dte  = 1 / 365
        if expiry_date:
            try:
                exp_dt = datetime.strptime(expiry_date, "%d-%b-%Y")
                dte = max((exp_dt - datetime.now()).total_seconds()/(365*86_400), 1/365)
            except Exception:
                pass

        rows = []
        for item in raw["records"].get("data", []):
            strike = float(item["strikePrice"])
            expiry = item["expiryDate"]
            if expiry_date and expiry.upper() != expiry_date.upper():
                continue
            for itype, key in [("CE","CE"),("PE","PE")]:
                if key not in item:
                    continue
                d = item[key]
                ltp = float(d.get("lastPrice",     0) or 0)
                oi  = int(d.get("openInterest",    0) or 0)
                vol = int(d.get("totalTradedVolume",0) or 0)
                nse_iv = float(d.get("impliedVolatility",0) or 0)
                iv_pct = (nse_iv if nse_iv > 0
                          else _iv_from_ltp(spot, strike, dte, risk_free_rate,
                                            ltp, "call" if itype=="CE" else "put"))
                rows.append({
                    "strike":    strike, "expiry": expiry, "type": itype,
                    "oi":        oi,
                    "oi_change": int(d.get("changeinOpenInterest",0) or 0),
                    "volume":    vol,    "iv":     iv_pct,
                    "ltp":       ltp,
                    "change":    float(d.get("change",0) or 0),
                    "bid_qty":   int(d.get("bidQty",0) or 0),
                    "ask_qty":   int(d.get("askQty",0) or 0),
                })
        if not rows:
            return None, None
        return pd.DataFrame(rows).sort_values("strike").reset_index(drop=True), spot

    except Exception as exc:
        print(f"[fetch_option_chain/nselib] {exc}")
        return None, None


# ── Market status / index quote ───────────────────────────────────────────────

def get_market_status() -> dict:
    base = {"market_state":"Unknown",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    try:
        if not _NSELIB:
            return base
        base["market_state"] = _cm.market_status().get("marketState","Unknown")
    except Exception:
        pass
    return base


def get_index_quote(symbol="NIFTY"):
    try:
        if not _NSELIB:
            return None
        target = _NSE_INDEX_NAME.get(symbol.upper(),"NIFTY 50")
        data   = _cm.market_watch_all_indices()
        for item in data.get("data",[]):
            if item.get("index") == target:
                return {
                    "last":  float(item.get("last",0)),
                    "change":float(item.get("percentChange",0)),
                    "open":  float(item.get("open",0)),
                    "high":  float(item.get("high",0)),
                    "low":   float(item.get("low",0)),
                    "close": float(item.get("previousClose",0)),
                }
        return None
    except Exception as exc:
        print(f"[get_index_quote] {exc}")
        return None


# ── Sample data ───────────────────────────────────────────────────────────────

def generate_sample_data(symbol="NIFTY", spot_price=None,
                         expiry_date=None, kite_manager=None):
    from modules.utils import (get_next_expiry_for_symbol, get_strike_interval,
                                get_fallback_spot, calculate_time_to_expiry)

    if spot_price is None:
        try:
            spot_price = get_live_spot_price(symbol) or get_fallback_spot(symbol)
        except Exception:
            spot_price = get_fallback_spot(symbol)

    if expiry_date is None:
        expiry_date = get_next_expiry_for_symbol(symbol)

    interval    = get_strike_interval(symbol, expiry_date, kite_manager)
    half        = 20
    atm         = round(spot_price / interval) * interval
    strikes     = np.arange(atm - half*interval, atm + (half+1)*interval, interval)
    T           = calculate_time_to_expiry(expiry_date)
    r, rng      = 0.07, np.random.default_rng(seed=42)

    rows = []
    for strike in strikes:
        mono = abs(strike - spot_price) / spot_price
        base = max(int(500_000 * np.exp(-mono * 15)), 5_000)
        c_iv = max(0.05, 0.14 + mono*0.08 + rng.uniform(-0.01,0.01))
        p_iv = max(0.05, 0.14 + mono*0.10 + rng.uniform(-0.01,0.01))
        c_ltp = max(_bs_price(spot_price, strike, T, r, c_iv, "call"), 0.05)
        p_ltp = max(_bs_price(spot_price, strike, T, r, p_iv, "put"),  0.05)
        for itype, iv, ltp in [("CE",c_iv,c_ltp),("PE",p_iv,p_ltp)]:
            rows.append({
                "strike": float(strike), "expiry": expiry_date, "type": itype,
                "oi":     int(base * rng.uniform(0.8,1.2)),
                "oi_change": int(rng.integers(-5_000,5_000)),
                "volume": int(rng.integers(1_000,50_000)),
                "iv":     round(iv*100, 2), "ltp": round(ltp,2),
                "change": round(float(rng.uniform(-10,10)), 2),
                "bid_qty": int(rng.integers(50,500)),
                "ask_qty": int(rng.integers(50,500)),
            })
    return pd.DataFrame(rows), float(spot_price)
