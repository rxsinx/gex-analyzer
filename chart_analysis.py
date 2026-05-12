"""
Technical chart analysis – dynamic Support & Resistance detection.

Algorithms
----------
1. Swing-high / swing-low pivot detection (configurable lookback)
2. Price-level clustering (merge levels within tolerance %)
3. Classical daily pivot points  (P, R1-R3, S1-S3)
4. Previous-day high / low / close
5. Round-number levels (psychological levels at round intervals)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class PriceLevel:
    price: float
    touches: int
    level_type: str   # 'support' | 'resistance' | 'pivot' | 'prev_day' | 'round'
    label: str = ""
    strength: str = "normal"   # 'strong' | 'normal' | 'weak'


# ── swing detection ──────────────────────────────────────────────────────────

def detect_swing_levels(
    df: pd.DataFrame,
    lookback: int = 5,
    tolerance_pct: float = 0.0015,   # 0.15 %
    min_touches: int = 2,
) -> Tuple[List[PriceLevel], List[PriceLevel]]:
    """
    Detect swing support & resistance from OHLC data.

    Parameters
    ----------
    df            : DataFrame with index=DatetimeIndex, cols include high/low
    lookback      : candles on each side to confirm a local extreme
    tolerance_pct : merge threshold as fraction of price (e.g. 0.0015 = 0.15 %)
    min_touches   : minimum cluster size to keep a level

    Returns
    -------
    (support_levels, resistance_levels)
    """
    n = len(df)
    if n < lookback * 2 + 3:
        return [], []

    swing_highs: list[float] = []
    swing_lows:  list[float] = []

    highs = df["high"].values
    lows  = df["low"].values

    for i in range(lookback, n - lookback):
        window_h = highs[i - lookback : i + lookback + 1]
        window_l = lows[i  - lookback : i + lookback + 1]

        if highs[i] == window_h.max():
            swing_highs.append(float(highs[i]))
        if lows[i] == window_l.min():
            swing_lows.append(float(lows[i]))

    supports    = _cluster(swing_lows,  tolerance_pct, "support",    min_touches)
    resistances = _cluster(swing_highs, tolerance_pct, "resistance", min_touches)

    return supports, resistances


def _cluster(
    prices: list[float],
    tolerance_pct: float,
    level_type: str,
    min_touches: int,
) -> List[PriceLevel]:
    if not prices:
        return []

    prices = sorted(prices)
    clusters: list[list[float]] = [[prices[0]]]

    for p in prices[1:]:
        mean = float(np.mean(clusters[-1]))
        if abs(p - mean) / mean <= tolerance_pct:
            clusters[-1].append(p)
        else:
            clusters.append([p])

    levels: list[PriceLevel] = []
    for cl in clusters:
        if len(cl) < min_touches:
            continue
        avg = float(np.mean(cl))
        touches = len(cl)
        strength = "strong" if touches >= 4 else "normal" if touches >= 2 else "weak"
        levels.append(PriceLevel(
            price=round(avg, 2),
            touches=touches,
            level_type=level_type,
            label=f"{level_type.capitalize()} ×{touches}",
            strength=strength,
        ))

    return sorted(levels, key=lambda x: (-x.touches, x.price))


# ── previous-day levels ──────────────────────────────────────────────────────

def get_prev_day_levels(df: pd.DataFrame) -> List[PriceLevel]:
    """Extract PDH, PDL, PDC from the most recent completed trading day."""
    if df is None or len(df) == 0:
        return []
    try:
        idx = df.index
        # normalise timezone
        if idx.tz is not None:
            dates = idx.tz_convert("Asia/Kolkata").date
        else:
            dates = idx.date

        unique_dates = sorted(set(dates))
        if len(unique_dates) < 2:
            return []

        prev_date = unique_dates[-2]
        mask      = np.array(dates) == prev_date
        prev      = df[mask]

        return [
            PriceLevel(round(float(prev["high"].max()),        2), 1, "prev_day", "PDH", "normal"),
            PriceLevel(round(float(prev["low"].min()),         2), 1, "prev_day", "PDL", "normal"),
            PriceLevel(round(float(prev["close"].iloc[-1]),    2), 1, "prev_day", "PDC", "weak"),
        ]
    except Exception:
        return []


# ── classical pivot points ───────────────────────────────────────────────────

def get_pivot_points(df: pd.DataFrame) -> List[PriceLevel]:
    """Classical floor pivot points from the most recent completed session."""
    if df is None or len(df) == 0:
        return []
    try:
        idx = df.index
        dates = (idx.tz_convert("Asia/Kolkata").date
                 if idx.tz is not None else idx.date)
        unique_dates = sorted(set(dates))
        if len(unique_dates) < 2:
            return []

        prev_date = unique_dates[-2]
        prev      = df[np.array(dates) == prev_date]

        H = float(prev["high"].max())
        L = float(prev["low"].min())
        C = float(prev["close"].iloc[-1])

        P  = (H + L + C) / 3
        R1 = 2 * P - L
        R2 = P + (H - L)
        R3 = H + 2 * (P - L)
        S1 = 2 * P - H
        S2 = P - (H - L)
        S3 = L - 2 * (H - P)

        return [
            PriceLevel(round(R3, 1), 1, "pivot", "R3", "weak"),
            PriceLevel(round(R2, 1), 1, "pivot", "R2", "normal"),
            PriceLevel(round(R1, 1), 1, "pivot", "R1", "strong"),
            PriceLevel(round(P,  1), 1, "pivot", "Pivot", "strong"),
            PriceLevel(round(S1, 1), 1, "pivot", "S1", "strong"),
            PriceLevel(round(S2, 1), 1, "pivot", "S2", "normal"),
            PriceLevel(round(S3, 1), 1, "pivot", "S3", "weak"),
        ]
    except Exception:
        return []


# ── round-number levels ───────────────────────────────────────────────────────

def get_round_number_levels(
    spot: float,
    interval: float,
    n_above: int = 5,
    n_below: int = 5,
) -> List[PriceLevel]:
    """
    Return round-number psychological levels near spot.
    e.g. for NIFTY with interval=100: 24000, 24100, …
    """
    base = round(spot / interval) * interval
    levels = []
    for i in range(-n_below, n_above + 1):
        p = base + i * interval
        if p <= 0:
            continue
        is_major = (p % (interval * 5) == 0)
        levels.append(PriceLevel(
            price=round(p, 1),
            touches=1,
            level_type="round",
            label=f"{'★ ' if is_major else ''}₹{p:,.0f}",
            strength="strong" if is_major else "weak",
        ))
    return levels


# ── combined analysis ────────────────────────────────────────────────────────

def analyse_levels(
    df: pd.DataFrame,
    spot: float,
    swing_lookback: int = 5,
    tolerance_pct: float = 0.0015,
    min_swing_touches: int = 2,
    include_pivots: bool = True,
    include_prev_day: bool = True,
    include_round: bool = False,
    round_interval: float = 100.0,
) -> dict:
    """
    Run all S/R algorithms and return a structured dict.

    Returns
    -------
    {
      "supports":    [PriceLevel, ...],
      "resistances": [PriceLevel, ...],
      "pivots":      [PriceLevel, ...],
      "prev_day":    [PriceLevel, ...],
      "round":       [PriceLevel, ...],
    }
    """
    supports, resistances = detect_swing_levels(
        df, swing_lookback, tolerance_pct, min_swing_touches
    )
    pivots   = get_pivot_points(df) if include_pivots   else []
    prev_day = get_prev_day_levels(df) if include_prev_day else []
    rounds   = (get_round_number_levels(spot, round_interval)
                if include_round else [])

    return {
        "supports":    supports,
        "resistances": resistances,
        "pivots":      pivots,
        "prev_day":    prev_day,
        "round":       rounds,
    }
