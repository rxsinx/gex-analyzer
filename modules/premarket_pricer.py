"""
modules/premarket_pricer.py
============================
Pre-Market Option Price Calculator

How it works:
─────────────
NSE Pre-Open Session:
  9:00 AM → 9:08 AM : Order entry / modification / cancellation
  9:08 AM → 9:12 AM : Matching, equilibrium price (IEP) confirmation
  9:15 AM           : Regular market opens

At 9:07 AM, Kite `ltp()` on the index returns the Indicative Equilibrium
Price (IEP) — the expected opening spot.

Using that new spot + last session's implied volatilities (stored in gex_df)
+ Black-Scholes, we can calculate the EXPECTED option prices before market
opens. This helps traders:
  • Pre-plan entry strikes before 9:15
  • See which calls/puts gain/lose on gap-up or gap-down
  • Calculate expected straddle/strangle cost at open
  • Identify strikes that flip from OTM→ITM (or vice versa)

Public API:
───────────
  from modules.premarket_pricer import (
      get_premarket_spot,
      calculate_premarket_prices,
      get_premarket_summary,
  )

  pm_spot   = get_premarket_spot(kite_manager, symbol)
  pm_df     = calculate_premarket_prices(gex_df, pm_spot, expiry, rfr)
  summary   = get_premarket_summary(pm_df, pm_spot, prev_close, expiry)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm
from datetime import datetime


# ── Black-Scholes helpers ─────────────────────────────────────────────────────

def _bsm_price(S: float, K: float, T: float, r: float,
               sigma: float, opt: str = "call") -> float:
    """Return BSM theoretical price. Returns intrinsic value if T≤0 or σ≤0."""
    if T <= 0 or sigma <= 0:
        return max((S - K) if opt == "call" else (K - S), 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if opt == "call":
        return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


def _bsm_greeks(S: float, K: float, T: float, r: float,
                sigma: float, opt: str = "call") -> dict:
    """Return delta, gamma, theta for a single option."""
    if T <= 0 or sigma <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0}
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    gamma = float(norm.pdf(d1) / (S * sigma * np.sqrt(T)))
    theta_c = float((-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
                     - r * K * np.exp(-r * T) * norm.cdf(d2)) / 365)
    theta_p = float((-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
                     + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365)
    return {
        "delta": float(norm.cdf(d1) if opt == "call" else norm.cdf(d1) - 1),
        "gamma": gamma,
        "theta": theta_c if opt == "call" else theta_p,
    }


# ── Spot fetcher ──────────────────────────────────────────────────────────────

def get_premarket_spot(kite_manager, symbol: str) -> dict:
    """
    Fetch the NSE Indicative Equilibrium Price (IEP) during pre-open.
    Returns dict with 'spot', 'prev_close', 'gap', 'gap_pct', 'timestamp'.

    Works best between 9:00–9:08 AM IST.
    Outside pre-open window it returns the regular LTP — still valid for
    "what-if" scenario analysis.
    """
    try:
        # Get current LTP (IEP during pre-open, regular LTP otherwise)
        spot = kite_manager.get_spot_ltp(symbol)

        # Get OHLC for previous close
        ohlc = kite_manager.get_spot_ohlc(symbol)
        prev_close = ohlc.get("close", spot) if ohlc else spot

        gap     = spot - prev_close
        gap_pct = (gap / prev_close * 100) if prev_close else 0.0

        return {
            "spot":       round(spot, 2),
            "prev_close": round(prev_close, 2),
            "gap":        round(gap, 2),
            "gap_pct":    round(gap_pct, 3),
            "timestamp":  datetime.now().strftime("%H:%M:%S"),
            "error":      None,
        }
    except Exception as exc:
        return {
            "spot": None, "prev_close": None,
            "gap": None,  "gap_pct": None,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "error": str(exc),
        }


# ── Core pricer ───────────────────────────────────────────────────────────────

def calculate_premarket_prices(
    gex_df:        pd.DataFrame,
    premarket_spot: float,
    expiry_date:   str,
    risk_free_rate: float = 0.07,
) -> pd.DataFrame:
    """
    Calculate expected option prices at market open using:
      • Pre-market indicative spot (IEP at 9:07 AM)
      • Last session's implied volatilities stored in gex_df
      • Black-Scholes Model

    Args:
        gex_df          : GEX DataFrame from last chain fetch (has call_iv, put_iv, ltps)
        premarket_spot  : NSE indicative equilibrium price (~9:07 AM)
        expiry_date     : Current expiry string "DD-MMM-YYYY"
        risk_free_rate  : Risk-free rate (default 7%)

    Returns:
        DataFrame with columns:
          strike, prev_call, exp_call, call_chg, call_chg_pct,
          prev_put,  exp_put,  put_chg,  put_chg_pct,
          call_delta, put_delta, straddle_prev, straddle_exp,
          moneyness, signal
    """
    from modules.utils import calculate_time_to_expiry

    T = calculate_time_to_expiry(expiry_date)

    rows = []
    for _, row in gex_df.iterrows():
        strike     = float(row["strike"])
        call_iv    = float(row["call_iv"]) / 100   # decimal
        put_iv     = float(row["put_iv"])  / 100
        prev_call  = float(row["call_ltp"])
        prev_put   = float(row["put_ltp"])

        # ── Expected prices at new spot ───────────────────────────────────────
        exp_call = round(_bsm_price(premarket_spot, strike, T,
                                    risk_free_rate, call_iv, "call"), 2)
        exp_put  = round(_bsm_price(premarket_spot, strike, T,
                                    risk_free_rate, put_iv,  "put"),  2)

        # ── Greeks at new spot ────────────────────────────────────────────────
        cg = _bsm_greeks(premarket_spot, strike, T, risk_free_rate, call_iv, "call")
        pg = _bsm_greeks(premarket_spot, strike, T, risk_free_rate, put_iv,  "put")

        # ── Change vs previous close ──────────────────────────────────────────
        call_chg     = round(exp_call - prev_call, 2)
        put_chg      = round(exp_put  - prev_put,  2)
        call_chg_pct = round((call_chg / prev_call * 100) if prev_call > 0.5 else 0, 1)
        put_chg_pct  = round((put_chg  / prev_put  * 100) if prev_put  > 0.5 else 0, 1)

        # ── Straddle ─────────────────────────────────────────────────────────
        straddle_prev = round(prev_call + prev_put, 2)
        straddle_exp  = round(exp_call  + exp_put,  2)

        # ── Moneyness at pre-market spot ──────────────────────────────────────
        dist = premarket_spot - strike
        if   abs(dist) <= 50:          moneyness = "ATM"
        elif dist > 0:                 moneyness = "ITM Call"
        else:                          moneyness = "OTM Call"

        # ── Trade signal ──────────────────────────────────────────────────────
        if moneyness == "ATM":
            signal = "⭐ ATM"
        elif abs(call_chg_pct) >= 30 or abs(put_chg_pct) >= 30:
            if call_chg > 0 and call_chg_pct >= 30:
                signal = "🚀 Call surge"
            elif put_chg > 0 and put_chg_pct >= 30:
                signal = "🔻 Put surge"
            else:
                signal = "📉 Premium drop"
        else:
            signal = "—"

        rows.append({
            "strike":        int(strike),
            "prev_call":     prev_call,
            "exp_call":      exp_call,
            "call_chg":      call_chg,
            "call_chg_pct":  call_chg_pct,
            "prev_put":      prev_put,
            "exp_put":       exp_put,
            "put_chg":       put_chg,
            "put_chg_pct":   put_chg_pct,
            "call_delta":    round(cg["delta"], 3),
            "put_delta":     round(pg["delta"], 3),
            "call_gamma":    round(cg["gamma"], 6),
            "straddle_prev": straddle_prev,
            "straddle_exp":  straddle_exp,
            "straddle_chg":  round(straddle_exp - straddle_prev, 2),
            "moneyness":     moneyness,
            "signal":        signal,
        })

    return pd.DataFrame(rows).sort_values("strike").reset_index(drop=True)


# ── Summary metrics ───────────────────────────────────────────────────────────

def get_premarket_summary(
    pm_df:          pd.DataFrame,
    premarket_spot: float,
    prev_close:     float,
    expiry_date:    str,
) -> dict:
    """
    Return key pre-market summary stats for display in the dashboard.

    Returned keys:
      gap, gap_pct, gap_direction,
      atm_strike, atm_call_prev, atm_call_exp, atm_call_chg,
      atm_put_prev,  atm_put_exp,  atm_put_chg,
      atm_straddle_prev, atm_straddle_exp, atm_straddle_chg,
      atm_straddle_chg_pct,
      breakeven_up, breakeven_dn,
      oi_shift_note
    """
    if pm_df.empty:
        return {}

    gap     = premarket_spot - prev_close
    gap_pct = (gap / prev_close * 100) if prev_close else 0.0
    gap_dir = "GAP UP ▲" if gap > 0 else "GAP DOWN ▼" if gap < 0 else "FLAT ●"

    # ATM = strike closest to pre-market spot
    atm_idx  = (pm_df["strike"] - premarket_spot).abs().idxmin()
    atm      = pm_df.loc[atm_idx]
    atm_strd_chg_pct = (
        atm["straddle_chg"] / atm["straddle_prev"] * 100
        if atm["straddle_prev"] > 0 else 0
    )

    # Breakeven levels (straddle breakeven)
    breakeven_up = atm["strike"] + atm["straddle_exp"]
    breakeven_dn = atm["strike"] - atm["straddle_exp"]

    # Top call and put gainers
    top_call_gainer = pm_df.loc[pm_df["call_chg_pct"].idxmax()]
    top_put_gainer  = pm_df.loc[pm_df["put_chg_pct"].idxmax()]

    # Biggest losers (premium collapse)
    top_call_loser  = pm_df.loc[pm_df["call_chg_pct"].idxmin()]
    top_put_loser   = pm_df.loc[pm_df["put_chg_pct"].idxmin()]

    return {
        "gap":              round(gap, 2),
        "gap_pct":          round(gap_pct, 2),
        "gap_direction":    gap_dir,
        "premarket_spot":   premarket_spot,
        "prev_close":       prev_close,
        "expiry_date":      expiry_date,

        # ATM metrics
        "atm_strike":           int(atm["strike"]),
        "atm_call_prev":        atm["prev_call"],
        "atm_call_exp":         atm["exp_call"],
        "atm_call_chg":         atm["call_chg"],
        "atm_put_prev":         atm["prev_put"],
        "atm_put_exp":          atm["exp_put"],
        "atm_put_chg":          atm["put_chg"],
        "atm_straddle_prev":    atm["straddle_prev"],
        "atm_straddle_exp":     atm["straddle_exp"],
        "atm_straddle_chg":     atm["straddle_chg"],
        "atm_straddle_chg_pct": round(atm_strd_chg_pct, 1),
        "breakeven_up":         round(breakeven_up, 0),
        "breakeven_dn":         round(breakeven_dn, 0),

        # Movers
        "top_call_gainer_strike":  int(top_call_gainer["strike"]),
        "top_call_gainer_pct":     top_call_gainer["call_chg_pct"],
        "top_put_gainer_strike":   int(top_put_gainer["strike"]),
        "top_put_gainer_pct":      top_put_gainer["put_chg_pct"],
        "top_call_loser_strike":   int(top_call_loser["strike"]),
        "top_call_loser_pct":      top_call_loser["call_chg_pct"],
        "top_put_loser_strike":    int(top_put_loser["strike"]),
        "top_put_loser_pct":       top_put_loser["put_chg_pct"],
    }
