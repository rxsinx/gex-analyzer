"""
Kite Connect v3 integration
Reference: https://kite.trade/docs/connect/v3/market-quotes/

Design principles
-----------------
* Spot price  → kite.ltp()    (/quote/ltp,  up to 1000 instruments, fast)
* Full quotes → kite.quote()  (/quote,       up to 500 instruments)
* OHLC        → kite.ohlc()  (/quote/ohlc,  up to 1000 instruments)
* ALL instrument metadata (lot_size, tick_size, expiry, strike_interval)
  are read from the NFO instruments CSV – nothing is hardcoded.
* oi_day_high / oi_day_low are present in /quote response per API docs.
* IV is back-solved from LTP via Brent's method (Kite does not provide IV).
* BANKNIFTY weekly availability is detected dynamically from instruments.
"""

from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st
from kiteconnect import KiteConnect
from scipy.optimize import brentq
from scipy.stats import norm


# ---------------------------------------------------------------------------
# Kite v3 index quote symbols  (exchange:tradingsymbol)
# Source: /quote/ltp?i=NSE:NIFTY+50
# ---------------------------------------------------------------------------
_INDEX_LTP_KEY: dict[str, str] = {
    "NIFTY":      "NSE:NIFTY 50",
    "BANKNIFTY":  "NSE:NIFTY BANK",
    "FINNIFTY":   "NSE:NIFTY FIN SERVICE",
    "MIDCPNIFTY": "NSE:NIFTY MIDCAP SELECT",
    "SENSEX":     "BSE:SENSEX",
    "BANKEX":     "BSE:BANKEX",
}

# ---------------------------------------------------------------------------
# Black-Scholes helpers
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


def iv_from_ltp(S: float, K: float, T: float, r: float,
                ltp: float, opt: str = "call") -> float:
    """
    Back-solve implied volatility from market LTP.
    Returns IV as a decimal (0.15 = 15 %).
    Falls back to 0.15 on failure.
    """
    if T <= 0 or ltp <= 0:
        return 0.15
    intrinsic = max((S - K) if opt == "call" else (K - S), 0.0)
    if ltp <= intrinsic + 1e-6:
        return 0.001   # deep ITM or zero-value option
    try:
        return max(
            brentq(lambda s: _bs_price(S, K, T, r, s, opt) - ltp,
                   1e-4, 5.0, xtol=1e-6, maxiter=300),
            0.001,
        )
    except Exception:
        return 0.15


# ---------------------------------------------------------------------------
# KiteManager
# ---------------------------------------------------------------------------

class KiteManager:
    """
    Wraps Kite Connect v3 API.

    Instrument metadata (lot size, tick size, expiry, strike interval)
    are always read from the NFO instruments CSV.  Nothing is hardcoded.
    """

    def __init__(self, api_key: str, api_secret: str) -> None:
        self.api_key    = api_key
        self.api_secret = api_secret
        self.kite       = KiteConnect(api_key=api_key)
        self.access_token: Optional[str] = None
        # cache: exchange → list[dict]
        self._cache: dict[str, list] = {}
        # per-symbol derived cache
        self._sym_meta: dict[str, dict] = {}

    # ── auth ────────────────────────────────────────────────────────────────

    def get_login_url(self) -> str:
        return self.kite.login_url()

    def set_access_token(self, request_token: str) -> bool:
        try:
            data = self.kite.generate_session(
                request_token, api_secret=self.api_secret
            )
            self.access_token = data["access_token"]
            self.kite.set_access_token(self.access_token)
            st.success("✅ Kite session established.")
            return True
        except Exception as exc:
            st.error(f"Kite authentication failed: {exc}")
            return False

    # ── instruments (cached once per session) ───────────────────────────────

    def _instruments(self, exchange: str = "NFO") -> list[dict]:
        if exchange not in self._cache:
            try:
                self._cache[exchange] = self.kite.instruments(exchange)
                st.caption(
                    f"📥 Loaded {len(self._cache[exchange]):,} "
                    f"{exchange} instruments from Kite."
                )
            except Exception as exc:
                st.warning(f"Could not load {exchange} instruments: {exc}")
                self._cache[exchange] = []
        return self._cache[exchange]

    def _sym_instruments(self, symbol: str) -> list[dict]:
        """Return all NFO CE/PE rows for *symbol*."""
        sym = symbol.upper()
        return [
            i for i in self._instruments("NFO")
            if i.get("name", "").upper() == sym
            and i.get("instrument_type") in ("CE", "PE")
        ]

    # ── derived metadata from instruments ──────────────────────────────────

    def get_lot_size(self, symbol: str) -> int:
        """Lot size from NFO instruments CSV. Never hardcoded."""
        rows = self._sym_instruments(symbol)
        sizes = {int(r["lot_size"]) for r in rows if int(r.get("lot_size", 0)) > 0}
        return min(sizes) if sizes else 50   # 50 is just a last-resort guard

    def get_tick_size(self, symbol: str) -> float:
        """Tick size from NFO instruments CSV."""
        rows = self._sym_instruments(symbol)
        ticks = {float(r["tick_size"]) for r in rows if float(r.get("tick_size", 0)) > 0}
        return min(ticks) if ticks else 0.05

    def get_strike_interval(self, symbol: str,
                             expiry: Optional[str] = None) -> float:
        """
        Derive the strike interval by finding the minimum non-zero gap
        between adjacent strikes for *symbol* on *expiry* (or nearest expiry).
        """
        rows = self._sym_instruments(symbol)
        if expiry:
            try:
                target = datetime.strptime(expiry, "%d-%b-%Y").date()
                rows = [r for r in rows if r.get("expiry") == target]
            except Exception:
                pass
        if not rows:
            rows = self._sym_instruments(symbol)

        strikes = sorted({float(r["strike"]) for r in rows if float(r.get("strike", 0)) > 0})
        if len(strikes) < 2:
            return 50.0   # last-resort guard only

        diffs = [strikes[i+1] - strikes[i] for i in range(len(strikes)-1)]
        pos_diffs = [d for d in diffs if d > 0]
        return min(pos_diffs) if pos_diffs else 50.0

    def get_available_expiries(self, symbol: str) -> list[str]:
        """
        All future expiry dates for *symbol* from instruments CSV,
        sorted ascending, formatted 'DD-MMM-YYYY'.
        """
        today = date.today()
        rows  = self._sym_instruments(symbol)
        expiry_set: set[date] = set()
        for r in rows:
            exp = r.get("expiry")
            if isinstance(exp, date) and exp >= today:
                expiry_set.add(exp)
        return [d.strftime("%d-%b-%Y").upper() for d in sorted(expiry_set)]

    def has_weekly_expiry(self, symbol: str) -> bool:
        """
        Return True if *symbol* has more than one expiry per month
        (i.e., weekly expiries exist).  Determined entirely from instruments data.
        """
        expiries = self.get_available_expiries(symbol)
        if len(expiries) < 2:
            return False
        # Count expiries in the first calendar month that has data
        dates = [datetime.strptime(e, "%d-%b-%Y").date() for e in expiries]
        first_month = dates[0].month
        first_year  = dates[0].year
        count_in_month = sum(
            1 for d in dates
            if d.month == first_month and d.year == first_year
        )
        return count_in_month > 1

    # ── v3 quote wrappers ───────────────────────────────────────────────────
    # Reference: https://kite.trade/docs/connect/v3/market-quotes/
    #
    # /quote/ltp  → kite.ltp(instruments)   up to 1000
    # /quote/ohlc → kite.ohlc(instruments)  up to 1000
    # /quote      → kite.quote(instruments) up to 500

    def get_spot_ltp(self, symbol: str) -> Optional[float]:
        """
        Fetch live spot price using /quote/ltp  (fastest, up to 1000 instruments).
        Returns None on failure with a visible st.warning.
        """
        key = _INDEX_LTP_KEY.get(symbol.upper())
        if not key:
            st.warning(f"No Kite LTP key configured for '{symbol}'")
            return None
        try:
            resp = self.kite.ltp([key])      # SDK: calls /quote/ltp
            data = resp.get(key)
            if not data:
                st.warning(
                    f"LTP response missing key '{key}'. "
                    f"Got: {list(resp.keys())}"
                )
                return None
            return float(data["last_price"])
        except Exception as exc:
            st.warning(f"get_spot_ltp({symbol}): {exc}")
            return None

    def get_spot_ohlc(self, symbol: str) -> Optional[dict]:
        """
        Fetch OHLC + LTP using /quote/ohlc.
        Returns dict with keys: last_price, open, high, low, close
        """
        key = _INDEX_LTP_KEY.get(symbol.upper())
        if not key:
            return None
        try:
            resp = self.kite.ohlc([key])     # SDK: calls /quote/ohlc
            data = resp.get(key)
            if not data:
                return None
            return {
                "last_price": float(data["last_price"]),
                "open":       float(data["ohlc"]["open"]),
                "high":       float(data["ohlc"]["high"]),
                "low":        float(data["ohlc"]["low"]),
                "close":      float(data["ohlc"]["close"]),
            }
        except Exception as exc:
            st.warning(f"get_spot_ohlc({symbol}): {exc}")
            return None

    def _quote_chunked(self, keys: list[str],
                        chunk_size: int = 450) -> dict:
        """
        Fetch /quote in chunks (Kite limit = 500 per call).
        Returns merged dict.  Logs per-chunk warnings on failure.
        """
        merged: dict = {}
        for start in range(0, len(keys), chunk_size):
            chunk = keys[start : start + chunk_size]
            try:
                merged.update(self.kite.quote(chunk))
            except Exception as exc:
                st.warning(
                    f"Quote chunk [{start}:{start+chunk_size}] failed: {exc}"
                )
        return merged

    # ── option chain ────────────────────────────────────────────────────────

    def get_option_chain(
        self,
        symbol: str,
        expiry: str,
        risk_free_rate: float = 0.07,
    ) -> tuple[Optional[pd.DataFrame], Optional[float]]:
        """
        Fetch option chain from Kite NFO using /quote (v3).

        Parameters
        ----------
        symbol         e.g. 'NIFTY'
        expiry         'DD-MMM-YYYY'
        risk_free_rate annual decimal

        Returns
        -------
        (DataFrame, spot_price) or (None, None)
        """
        # 1 ── parse expiry ──────────────────────────────────────────────────
        try:
            target_date = datetime.strptime(expiry, "%d-%b-%Y").date()
        except ValueError as exc:
            st.error(f"Invalid expiry format '{expiry}': {exc}")
            return None, None

        # 2 ── filter instruments ─────────────────────────────────────────────
        all_rows = self._sym_instruments(symbol)
        if not all_rows:
            st.error(
                f"NFO instruments list empty for '{symbol}'. "
                "Check Kite connection."
            )
            return None, None

        rows = [r for r in all_rows if r.get("expiry") == target_date]
        if not rows:
            avail = self.get_available_expiries(symbol)[:5]
            st.warning(
                f"No contracts found for {symbol} expiry {expiry}. "
                f"Available (first 5): {avail}"
            )
            return None, None

        st.info(f"Found {len(rows):,} {symbol} contracts for {expiry}.")

        # 3 ── spot price (LTP endpoint – fast) ──────────────────────────────
        spot = self.get_spot_ltp(symbol)
        if spot is None:
            st.error(
                f"Could not fetch spot for {symbol}. "
                "Verify Kite access token is valid."
            )
            return None, None

        # 4 ── time to expiry ─────────────────────────────────────────────────
        now = datetime.now()
        dte = max(
            (datetime.combine(target_date, datetime.min.time()) - now
             ).total_seconds() / (365 * 86_400),
            1 / 365,
        )

        # 5 ── fetch /quote in chunks ─────────────────────────────────────────
        ts_keys = [f"NFO:{r['tradingsymbol']}" for r in rows]
        quotes  = self._quote_chunked(ts_keys)

        if not quotes:
            st.error(
                "Kite returned zero quotes. "
                "Market may be closed or session expired."
            )
            return None, None

        # 6 ── build rows ─────────────────────────────────────────────────────
        # API response fields (from v3 docs):
        #   last_price, oi, oi_day_high, oi_day_low,
        #   volume, net_change, ohlc, depth
        option_rows: list[dict] = []
        missing = 0

        for inst in rows:
            key = f"NFO:{inst['tradingsymbol']}"
            q   = quotes.get(key)
            if not q:
                missing += 1
                continue

            ltp    = float(q.get("last_price", 0) or 0)
            oi     = int(q.get("oi", 0) or 0)
            vol    = int(q.get("volume", 0) or 0)
            strike = float(inst["strike"])
            itype  = inst["instrument_type"]           # 'CE' or 'PE'

            # oi_day_high / oi_day_low are present in /quote per API docs
            oi_day_high = float(q.get("oi_day_high") or 0)
            oi_day_low  = float(q.get("oi_day_low")  or 0)
            oi_change   = int(oi_day_high - oi_day_low)

            # safe depth access (5-level depth per docs)
            depth     = q.get("depth") or {}
            buy_depth = depth.get("buy")  or []
            sel_depth = depth.get("sell") or []
            bid_qty   = int(buy_depth[0]["quantity"]) if buy_depth else 0
            ask_qty   = int(sel_depth[0]["quantity"]) if sel_depth else 0

            # IV from LTP (Kite does not provide IV)
            iv_dec = iv_from_ltp(
                spot, strike, dte, risk_free_rate,
                ltp, "call" if itype == "CE" else "put",
            )

            option_rows.append({
                "strike":    strike,
                "expiry":    expiry,
                "type":      itype,
                "oi":        oi,
                "oi_change": oi_change,
                "volume":    vol,
                "iv":        round(iv_dec * 100, 4),   # stored as %
                "ltp":       ltp,
                "change":    float(q.get("net_change", 0) or 0),
                "bid_qty":   bid_qty,
                "ask_qty":   ask_qty,
                "lot_size":  int(inst.get("lot_size", 0)),
                "tick_size": float(inst.get("tick_size", 0.05)),
            })

        if missing:
            st.caption(f"ℹ️ {missing}/{len(rows)} contracts had no quote data.")

        if not option_rows:
            st.error("All option contracts returned empty quotes.")
            return None, None

        df = (
            pd.DataFrame(option_rows)
            .sort_values("strike")
            .reset_index(drop=True)
        )
        return df, spot


# ---------------------------------------------------------------------------
# Streamlit session helper
# ---------------------------------------------------------------------------

def init_kite_session() -> Optional[KiteManager]:
    for key, val in [
        ("kite_manager",       None),
        ("kite_authenticated", False),
    ]:
        if key not in st.session_state:
            st.session_state[key] = val
    return st.session_state.kite_manager
