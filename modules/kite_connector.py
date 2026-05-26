"""
Kite Connect v3 integration
Reference: https://kite.trade/docs/connect/v3/market-quotes/
           https://kite.trade/docs/connect/v3/historical/

Rules
-----
* NO st.* calls inside this module – callers handle UI.
  All failures raise KiteError subclasses so the caller can
  display them exactly where they belong in the Streamlit UI.
* Spot price  → kite.ltp()    (/quote/ltp,  ≤1000 instruments)
* Full quotes → kite.quote()  (/quote,       ≤500 instruments)
* OHLC        → kite.ohlc()  (/quote/ohlc,  ≤1000 instruments)
* History     → kite.historical_data()
* All NFO instrument metadata (lot_size, tick_size, strike_interval,
  expiry dates) come from the instruments CSV – nothing hardcoded.
"""

from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from kiteconnect import KiteConnect
from scipy.optimize import brentq
from scipy.stats import norm


# ── exception hierarchy ──────────────────────────────────────────────────────

class KiteError(Exception):
    """Base Kite error."""

class KiteAuthError(KiteError):
    """Session/auth failure – token may be expired."""

class KiteDataError(KiteError):
    """Data fetch failure."""


# ── index LTP keys (exchange:tradingsymbol per Kite v3 docs) ────────────────
_INDEX_LTP_KEY: dict[str, str] = {
    "NIFTY":      "NSE:NIFTY 50",
    "BANKNIFTY":  "NSE:NIFTY BANK",
    "FINNIFTY":   "NSE:NIFTY FIN SERVICE",
    "MIDCPNIFTY": "NSE:NIFTY MIDCAP SELECT",
    "SENSEX":     "BSE:SENSEX",
    "BANKEX":     "BSE:BANKEX",
}

# ── known instrument tokens for NSE indices (stable, NSE-assigned) ───────────
# Used as fallback when instruments-CSV search fails.
_KNOWN_INDEX_TOKENS: dict[str, int] = {
    "NIFTY 50":          256265,
    "NIFTY BANK":        260105,
    "INDIA VIX":         264969,
    "NIFTY FIN SERVICE": 257801,
    "NIFTY MIDCAP SELECT": 288009,
}


# ── Black-Scholes IV solver ──────────────────────────────────────────────────

def _bs_price(S, K, T, r, sigma, opt="call"):
    if T <= 0 or sigma <= 0:
        return max((S - K) if opt == "call" else (K - S), 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if opt == "call":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def iv_from_ltp(S, K, T, r, ltp, opt="call"):
    """Back-solve IV from LTP. Returns IV as decimal (0.15 = 15 %)."""
    if T <= 0 or ltp <= 0:
        return 0.15
    intrinsic = max((S - K) if opt == "call" else (K - S), 0.0)
    if ltp <= intrinsic + 1e-6:
        return 0.001
    try:
        return max(brentq(
            lambda s: _bs_price(S, K, T, r, s, opt) - ltp,
            1e-4, 5.0, xtol=1e-6, maxiter=300), 0.001)
    except Exception:
        return 0.15


# ── KiteManager ─────────────────────────────────────────────────────────────

class KiteManager:
    """
    Wraps Kite Connect v3 API with clean error propagation.
    No st.* calls – all failures raise KiteError subclasses.
    """

    def __init__(self, api_key: str, api_secret: str):
        self.api_key    = api_key
        self.api_secret = api_secret
        self.kite       = KiteConnect(api_key=api_key)
        self.access_token: Optional[str] = None
        self._cache: dict[str, list] = {}   # exchange → instruments list

    # ── auth ────────────────────────────────────────────────────────────────

    def get_login_url(self) -> str:
        return self.kite.login_url()

    def set_access_token(self, request_token: str) -> tuple[bool, str]:
        """
        Returns (success, message).
        Caller decides how to display it.
        """
        try:
            data = self.kite.generate_session(
                request_token, api_secret=self.api_secret)
            self.access_token = data["access_token"]
            self.kite.set_access_token(self.access_token)
            profile = self.kite.profile()
            name = profile.get("user_name", "Unknown")
            return True, f"Logged in as {name}"
        except Exception as exc:
            return False, str(exc)

    # ── step-by-step connection test ────────────────────────────────────────

    def test_connection(self, symbol: str = "NIFTY") -> dict[str, dict]:
        """
        Run sequential connection checks.
        Returns dict of {step: {ok, msg}} for display in a debug panel.
        """
        results: dict[str, dict] = {}

        # 1. Profile / session
        try:
            p = self.kite.profile()
            results["1_session"] = {
                "ok": True,
                "label": "Session",
                "msg": f"Valid – {p.get('user_name','')} ({p.get('email','')})",
            }
        except Exception as exc:
            results["1_session"] = {
                "ok": False, "label": "Session",
                "msg": f"FAILED – {exc}  ← token may be expired (resets 6 AM)",
            }
            return results   # nothing else will work

        # 2. LTP
        key = _INDEX_LTP_KEY.get(symbol.upper(), "NSE:NIFTY 50")
        try:
            resp = self.kite.ltp([key])
            data = resp.get(key, {})
            ltp  = data.get("last_price")
            results["2_ltp"] = {
                "ok": ltp is not None,
                "label": f"LTP ({key})",
                "msg": f"₹{ltp:,.2f}" if ltp else f"key '{key}' missing in response {list(resp.keys())}",
            }
        except Exception as exc:
            results["2_ltp"] = {"ok": False, "label": f"LTP ({key})", "msg": str(exc)}

        # 3. NFO instruments
        try:
            insts = self._instruments("NFO")
            results["3_instruments"] = {
                "ok": len(insts) > 0,
                "label": "NFO Instruments",
                "msg": f"{len(insts):,} rows loaded",
            }
        except Exception as exc:
            results["3_instruments"] = {
                "ok": False, "label": "NFO Instruments", "msg": str(exc)}

        # 4. Symbol contracts
        try:
            rows = self._sym_instruments(symbol)
            expiries = sorted({r["expiry"] for r in rows if r.get("expiry")})
            results["4_symbol_contracts"] = {
                "ok": len(rows) > 0,
                "label": f"{symbol} Contracts",
                "msg": (f"{len(rows):,} CE+PE contracts across "
                        f"{len(expiries)} expiries "
                        f"(nearest: {expiries[0] if expiries else 'none'})"),
            }
        except Exception as exc:
            results["4_symbol_contracts"] = {
                "ok": False, "label": f"{symbol} Contracts", "msg": str(exc)}

        # 5. Single /quote test
        try:
            rows = self._sym_instruments(symbol)
            if rows:
                ts  = f"NFO:{rows[0]['tradingsymbol']}"
                q   = self.kite.quote([ts])
                got = q.get(ts, {})
                results["5_quote"] = {
                    "ok": bool(got),
                    "label": f"/quote ({ts})",
                    "msg": (f"LTP={got.get('last_price')}, OI={got.get('oi')}"
                            if got else "empty response"),
                }
            else:
                results["5_quote"] = {
                    "ok": False, "label": "/quote", "msg": "No contracts to test"}
        except Exception as exc:
            results["5_quote"] = {"ok": False, "label": "/quote", "msg": str(exc)}

        return results

    # ── instruments cache ────────────────────────────────────────────────────

    def _instruments(self, exchange: str = "NFO") -> list[dict]:
        """Return cached instruments for exchange. Raises KiteDataError on failure."""
        if exchange not in self._cache:
            try:
                self._cache[exchange] = self.kite.instruments(exchange)
            except Exception as exc:
                raise KiteDataError(
                    f"Could not load {exchange} instruments: {exc}"
                ) from exc
        return self._cache[exchange]

    def _sym_instruments(self, symbol: str) -> list[dict]:
        """All NFO CE/PE rows for symbol."""
        sym = symbol.upper()
        return [
            i for i in self._instruments("NFO")
            if i.get("name", "").upper() == sym
            and i.get("instrument_type") in ("CE", "PE")
        ]

    def invalidate_cache(self):
        """Force re-download of instruments on next call."""
        self._cache.clear()

    # ── derived metadata ─────────────────────────────────────────────────────

    def get_lot_size(self, symbol: str) -> int:
        rows  = self._sym_instruments(symbol)
        sizes = {int(r["lot_size"]) for r in rows if int(r.get("lot_size", 0)) > 0}
        return min(sizes) if sizes else 50

    def get_tick_size(self, symbol: str) -> float:
        rows  = self._sym_instruments(symbol)
        ticks = {float(r["tick_size"]) for r in rows if float(r.get("tick_size", 0)) > 0}
        return min(ticks) if ticks else 0.05

    def get_strike_interval(self, symbol: str, expiry: Optional[str] = None) -> float:
        rows = self._sym_instruments(symbol)
        if expiry:
            try:
                tgt  = datetime.strptime(expiry, "%d-%b-%Y").date()
                rows = [r for r in rows if r.get("expiry") == tgt] or rows
            except Exception:
                pass
        strikes = sorted({float(r["strike"]) for r in rows if float(r.get("strike", 0)) > 0})
        if len(strikes) < 2:
            return 50.0
        diffs = [b - a for a, b in zip(strikes, strikes[1:]) if b > a]
        return min(diffs) if diffs else 50.0

    def get_available_expiries(self, symbol: str) -> list[str]:
        today = date.today()
        rows  = self._sym_instruments(symbol)
        exp_set: set[date] = set()
        for r in rows:
            exp = r.get("expiry")
            if isinstance(exp, date) and exp >= today:
                exp_set.add(exp)
        return [d.strftime("%d-%b-%Y").upper() for d in sorted(exp_set)]

    def has_weekly_expiry(self, symbol: str) -> bool:
        expiries = self.get_available_expiries(symbol)
        if len(expiries) < 2:
             # Check hardcoded rules for quick answer
             return _EXPIRY_RULES.get(symbol.upper(), _DEFAULT_RULE)["has_weekly"]
    
        dates = [datetime.strptime(e, "%d-%b-%Y").date() for e in expiries]
        today = date.today()
    
        # Check if NEXT expiry is within 7-10 days
        next_expiry = dates[0]
        days_to_next = (next_expiry - today).days
               
        # If next expiry is 7-10 days away, it's weekly
        # OR check gap between first two expiries
        if 6 <= days_to_next <= 11:
            return True
        if len(dates) >= 2:
            if 6 <= (dates[1] - dates[0]).days <= 11:
                return True
               
        return False   

    # ── v3 quote wrappers ────────────────────────────────────────────────────

    def get_spot_ltp(self, symbol: str) -> float:
        """
        /quote/ltp for index spot.  Raises KiteAuthError or KiteDataError.
        """
        key = _INDEX_LTP_KEY.get(symbol.upper())
        if not key:
            raise KiteDataError(f"No LTP key for '{symbol}'")
        try:
            resp = self.kite.ltp([key])
        except Exception as exc:
            err = str(exc).lower()
            if "token" in err or "session" in err or "login" in err or "403" in err:
                raise KiteAuthError(f"Session error on ltp({key}): {exc}") from exc
            raise KiteDataError(f"ltp({key}) failed: {exc}") from exc

        data = resp.get(key)
        if not data:
            raise KiteDataError(
                f"ltp response missing key '{key}'. "
                f"Got keys: {list(resp.keys())}. "
                "Check that the exchange:tradingsymbol is correct."
            )
        ltp = data.get("last_price")
        if ltp is None:
            raise KiteDataError(f"last_price missing in ltp response for '{key}'")
        return float(ltp)

    def get_spot_ohlc(self, symbol: str) -> Optional[dict]:
        """
        /quote/ohlc – returns dict(last_price, open, high, low, close)
        Returns None on failure (non-critical, used for display only).
        """
        key = _INDEX_LTP_KEY.get(symbol.upper())
        if not key:
            return None
        try:
            resp = self.kite.ohlc([key])
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
        except Exception:
            return None

    def _quote_chunked(self, keys: list[str], chunk_size: int = 450) -> dict:
        """Fetch /quote in ≤500-key chunks. Collects all; re-raises on total failure."""
        merged: dict = {}
        errors: list[str] = []
        for i in range(0, len(keys), chunk_size):
            chunk = keys[i:i + chunk_size]
            try:
                merged.update(self.kite.quote(chunk))
            except Exception as exc:
                errors.append(f"chunk[{i}:{i+chunk_size}]: {exc}")
        if not merged and errors:
            err_str = "; ".join(errors)
            if any(w in err_str.lower() for w in ("token", "session", "login", "403")):
                raise KiteAuthError(f"Quote failed (session?): {err_str}")
            raise KiteDataError(f"All quote chunks failed: {err_str}")
        return merged

    # ── option chain ─────────────────────────────────────────────────────────

    def get_option_chain(
        self,
        symbol: str,
        expiry: str,
        risk_free_rate: float = 0.07,
    ) -> tuple[pd.DataFrame, float]:
        """
        Fetch option chain via Kite /quote.
        Raises KiteAuthError or KiteDataError on failure.
        Returns (DataFrame, spot_price).
        """
        # 1. parse expiry
        try:
            target_date = datetime.strptime(expiry, "%d-%b-%Y").date()
        except ValueError as exc:
            raise KiteDataError(f"Invalid expiry '{expiry}': {exc}") from exc

        # 2. filter instruments
        all_rows = self._sym_instruments(symbol)
        if not all_rows:
            raise KiteDataError(
                f"No NFO instruments found for '{symbol}'. "
                "Instruments may not have loaded – check session."
            )
        rows = [r for r in all_rows if r.get("expiry") == target_date]
        if not rows:
            avail = self.get_available_expiries(symbol)[:6]
            raise KiteDataError(
                f"No contracts for {symbol} expiry {expiry}. "
                f"First 6 available: {avail}"
            )

        # 3. spot price
        spot = self.get_spot_ltp(symbol)   # raises on failure

        # 4. DTE
        now = datetime.now()
        dte = max(
            (datetime.combine(target_date, datetime.min.time()) - now
             ).total_seconds() / (365 * 86_400),
            1 / 365,
        )

        # 5. fetch quotes
        ts_keys = [f"NFO:{r['tradingsymbol']}" for r in rows]
        quotes  = self._quote_chunked(ts_keys)   # raises on total failure

        # 6. build DataFrame
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
            itype  = inst["instrument_type"]

            oi_change = int(
                float(q.get("oi_day_high") or 0)
                - float(q.get("oi_day_low") or 0)
            )

            depth     = q.get("depth") or {}
            buy_side  = depth.get("buy")  or []
            sell_side = depth.get("sell") or []
            bid_qty   = int(buy_side[0]["quantity"])  if buy_side  else 0
            ask_qty   = int(sell_side[0]["quantity"]) if sell_side else 0

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
                "iv":        round(iv_dec * 100, 4),
                "ltp":       ltp,
                "change":    float(q.get("net_change", 0) or 0),
                "bid_qty":   bid_qty,
                "ask_qty":   ask_qty,
                "lot_size":  int(inst.get("lot_size", 0)),
                "tick_size": float(inst.get("tick_size", 0.05)),
            })

        if not option_rows:
            raise KiteDataError(
                f"All {len(rows)} contracts returned empty quotes. "
                f"({missing} missing entirely). "
                "Market may be closed or session may have expired."
            )

        df = (pd.DataFrame(option_rows)
              .sort_values("strike")
              .reset_index(drop=True))
        return df, spot

    # ── historical data for charts ───────────────────────────────────────────

    def _get_instrument_token(self, tradingsymbol: str, exchange: str = "NSE") -> Optional[int]:
        """
        Find instrument token by exact tradingsymbol match.
        Falls back to _KNOWN_INDEX_TOKENS for major indices.
        """
        # Try instruments CSV first
        try:
            insts = self._instruments(exchange)
            for inst in insts:
                if inst.get("tradingsymbol", "").upper() == tradingsymbol.upper():
                    return int(inst["instrument_token"])
        except Exception:
            pass
        # Fallback: known tokens
        return _KNOWN_INDEX_TOKENS.get(tradingsymbol.upper())

    def get_historical_candles(
        self,
        instrument_token: int,
        interval: str = "60minute",
        days_back: int = 22,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV history via Kite historical data API.

        interval: minute, 3minute, 5minute, 10minute, 15minute,
                  30minute, 60minute, day, week, month
        days_back: calendar days to look back (use ~22 for 1-month of 1hr data)
        """
        to_dt   = datetime.now()
        from_dt = to_dt - timedelta(days=days_back + 10)   # +10 for weekends

        try:
            raw = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_dt,
                to_date=to_dt,
                interval=interval,
                continuous=False,
                oi=False,
            )
        except Exception as exc:
            raise KiteDataError(
                f"historical_data(token={instrument_token}, interval={interval}) "
                f"failed: {exc}"
            ) from exc

        if not raw:
            raise KiteDataError(
                f"historical_data returned 0 candles for token={instrument_token}. "
                "Token may be invalid or market has no data for this range."
            )

        df = pd.DataFrame(raw)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()

        # Keep only 'days_back' worth of calendar days
        cutoff = pd.Timestamp.now(tz=df.index.tz) - pd.Timedelta(days=days_back)
        df = df[df.index >= cutoff]

        return df

    def get_index_and_vix_data(
        self,
        symbol: str,
        interval: str = "60minute",
        days_back: int = 22,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Fetch 1-hr (or any interval) candles for *symbol* and India VIX.
        Returns (index_df, vix_df).  Both DataFrames have DatetimeIndex
        and columns [open, high, low, close, volume].
        """
        ltp_key   = _INDEX_LTP_KEY.get(symbol.upper(), "NSE:NIFTY 50")
        exchange, ts = ltp_key.split(":", 1)

        index_token = self._get_instrument_token(ts, exchange)
        vix_token   = self._get_instrument_token("INDIA VIX", "NSE")

        if index_token is None:
            raise KiteDataError(
                f"Could not find instrument token for {ts} on {exchange}. "
                "Check NSE instruments list."
            )
        if vix_token is None:
            raise KiteDataError(
                "Could not find INDIA VIX instrument token on NSE."
            )

        index_df = self.get_historical_candles(index_token, interval, days_back)
        vix_df   = self.get_historical_candles(vix_token,   interval, days_back)

        return index_df, vix_df


# ── Streamlit session helper ─────────────────────────────────────────────────

def init_kite_session() -> Optional[KiteManager]:
    import streamlit as st
    for key, val in [("kite_manager", None), ("kite_authenticated", False)]:
        if key not in st.session_state:
            st.session_state[key] = val
    return st.session_state.kite_manager
