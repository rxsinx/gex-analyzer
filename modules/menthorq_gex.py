"""
modules/menthorq_gex.py
========================
MenthorQ-style horizontal Net GEX chart for the GEX Terminal.

Why Cumulative GEX, not raw DEX
---------------------------------
Raw DEX = delta × OI × spot.  For NIFTY ATM:
    GEX ≈  3 Cr   (gamma × OI × spot² × 0.01)
    DEX ≈ 61 Cr   (delta × OI × spot)
    Ratio ≈ 20×  → cannot share the same axis without destroying meaning.

Cumulative GEX = np.cumsum(net_gex, low→high strike) is the correct curve:
    • Same unit/scale as the bars — zero normalisation needed
    • Crosses zero exactly at the HVL / Gamma Flip level
    • Positive region  → dealers net long gamma (buy dips, sell rallies)
    • Negative region  → dealers net short gamma (chase the move)
    • Slope at strike K = the GEX bar height at K
    This is what SpotGamma and MenthorQ call the "dealer delta profile" —
    the aggregate hedging obligation accumulated as price sweeps each level.

Visual elements
---------------
1. Horizontal bars (green gradient / red-orange gradient)
2. GEX Profile line (yellow) — spline through bar tips
3. Cumulative GEX line (orange) — running sum, zero-crossing = HVL
4. Key level h-lines — Call Wall, Put Wall, HVL, Spot
5. Level dot markers on left margin
6. Gamma pin circle (white) — peak +GEX cluster near spot
7. Negative gamma pocket circle (red filled)
8. Legend annotation (top-right)
9. Auto analysis text via generate_gex_analysis()

Public API
----------
    from modules.menthorq_gex import plot_menthorq_gex, generate_gex_analysis

    fig   = plot_menthorq_gex(gex_df, spot_price, gamma_levels, symbol="NIFTY")
    lines = generate_gex_analysis(gex_df, spot_price, gamma_levels, symbol="NIFTY")
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go


# ── colour constants ──────────────────────────────────────────────────────────
_C_CALL  = "#EF4444"   # red  — call resistance
_C_PUT   = "#22C55E"   # green — put support
_C_HVL   = "#EAB308"   # yellow — HVL / gamma flip
_C_SPOT  = "#CBD5E1"   # cool-gray — spot price
_C_GEX   = "#FFD700"   # gold — GEX profile line
_C_CUM   = "#FF8C00"   # dark-orange — cumulative GEX line
_C_PIN   = "rgba(255,255,255,0.85)"
_C_NEG   = "rgba(239,68,68,0.85)"
_BG_PLOT = "#060606"
_BG_PAP  = "#0A0A0A"


# ── helpers ───────────────────────────────────────────────────────────────────

def _auto_scale(values: np.ndarray) -> tuple[float, str]:
    mx = float(max(np.abs(values).max(), 1.0))
    if mx >= 1e7:  return 1e7, "Cr"
    if mx >= 1e5:  return 1e5, "L"
    return 1.0, ""


def _bar_colour(v: float, v_max: float) -> str:
    i = min(abs(v) / v_max, 1.0)
    if v >= 0:
        return f"rgba(34,197,94,{0.38 + i*0.52:.2f})"
    r = int(185 + i * 58)
    g = int(55  * (1.0 - i * 0.85))
    return f"rgba({r},{g},12,0.90)"


# ═══════════════════════════════════════════════════════════════════════════════
# plot_menthorq_gex
# ═══════════════════════════════════════════════════════════════════════════════

def plot_menthorq_gex(
    gex_df:       pd.DataFrame,
    spot_price:   float,
    gamma_levels: dict,
    symbol:       str = "NIFTY",
) -> go.Figure:

    df      = gex_df.sort_values("strike").copy()
    strikes = df["strike"].values.astype(float)
    net_gex = df["total_gex"].values.astype(float)

    # ── scale ──────────────────────────────────────────────────────────────────
    divisor, unit = _auto_scale(net_gex)
    gex_sc  = net_gex / divisor
    gex_max = float(max(abs(gex_sc).max(), 0.01))

    # ── Cumulative GEX ─────────────────────────────────────────────────────────
    # Running sum from lowest → highest strike (same unit as bars).
    # Zero-crossing = HVL / Gamma Flip  — the regime boundary.
    cum_gex = np.cumsum(gex_sc)
    cum_max = float(max(abs(cum_gex).max(), 0.01))

    # strike interval
    si        = float(np.median(np.diff(np.sort(strikes)))) if len(strikes) > 1 else 50.0
    bar_width = si * 0.78
    bar_cols  = [_bar_colour(v, gex_max) for v in gex_sc]

    # ── key levels ─────────────────────────────────────────────────────────────
    call_wall  = float(gamma_levels.get("max_call_oi_strike", spot_price * 1.02))
    put_wall   = float(gamma_levels.get("max_put_oi_strike",  spot_price * 0.98))
    hvl        = float(gamma_levels.get("gamma_flip",         spot_price * 0.99))
    net_regime = gamma_levels.get("total_gex", 0)

    fig = go.Figure()

    # ── 1. Horizontal bars ────────────────────────────────────────────────────
    fig.add_trace(go.Bar(
        y=strikes, x=gex_sc,
        orientation="h", width=bar_width,
        marker=dict(color=bar_cols, line=dict(width=0)),
        name="Net GEX",
        hovertemplate=f"<b>Strike</b> ₹%{{y:,.0f}}<br><b>Net GEX</b> %{{x:.3f}} {unit}<extra></extra>",
    ))

    # ── 2. GEX Profile line (yellow) ──────────────────────────────────────────
    fig.add_trace(go.Scatter(
        y=strikes, x=gex_sc,
        mode="lines",
        line=dict(color=_C_GEX, width=2.3, shape="spline", smoothing=0.35),
        name="GEX Profile",
        hoverinfo="skip",
    ))

    # ── 3. Cumulative GEX line (orange) ───────────────────────────────────────
    # Replaces the normalised-DEX approach that had no physical meaning.
    fig.add_trace(go.Scatter(
        y=strikes, x=cum_gex,
        mode="lines",
        line=dict(color=_C_CUM, width=2.0, shape="spline", smoothing=0.35),
        name="Cumul. GEX",
        hovertemplate=f"<b>Strike</b> ₹%{{y:,.0f}}<br><b>Cumul. GEX</b> %{{x:.3f}} {unit}<extra></extra>",
    ))

    # annotate the regime-flip crossing on the cumulative line
    flip_idx = int(np.argmin(np.abs(cum_gex)))
    fig.add_annotation(
        x=float(cum_gex[flip_idx]), y=float(strikes[flip_idx]),
        text="  ← regime flip",
        showarrow=False,
        font=dict(color=_C_CUM, size=9, family="monospace"),
        xanchor="left",
    )

    # ── 4. Key level h-lines ──────────────────────────────────────────────────
    for price, color, dash, label, pos in [
        (call_wall,  _C_CALL, "dash", f"Call Resistance: {call_wall:,.0f}", "top right"),
        (put_wall,   _C_PUT,  "dash", f"Put Support: {put_wall:,.0f}",      "top right"),
        (hvl,        _C_HVL,  "dash", f"HVL: {hvl:,.0f}",                   "top left"),
        (spot_price, _C_SPOT, "dot",  f"Spot: {spot_price:,.0f}",            "top left"),
    ]:
        fig.add_hline(
            y=price,
            line=dict(color=color, width=1.3, dash=dash),
            annotation_text=f"  {label}  ",
            annotation_position=pos,
            annotation_font=dict(color=color, size=9, family="monospace"),
        )

    # ── 5. Level dot markers (left margin) ───────────────────────────────────
    dot_x = -gex_max * 1.25
    for price, color, name in [
        (call_wall,  _C_CALL, "Call Resistance"),
        (spot_price, _C_SPOT, "Spot Price"),
        (hvl,        _C_HVL,  "HVL"),
        (put_wall,   _C_PUT,  "Put Support"),
    ]:
        fig.add_trace(go.Scatter(
            x=[dot_x], y=[price],
            mode="markers",
            marker=dict(size=13, color=color, symbol="circle",
                        line=dict(width=1.5, color="rgba(0,0,0,0.5)")),
            name=name, showlegend=False,
            hovertemplate=f"<b>{name}</b>  ₹{price:,.0f}<extra></extra>",
        ))

    # ── 6. Gamma pin circle (white) ───────────────────────────────────────────
    near_mask = (
        (df["strike"] >= spot_price * 0.965) &
        (df["strike"] <= spot_price * 1.035) &
        (df["total_gex"] > 0)
    )
    if near_mask.any():
        near_sub   = df[near_mask]
        pin_sc     = float(near_sub["total_gex"].max()) / divisor
        pin_strike = float(near_sub.loc[near_sub["total_gex"].idxmax(), "strike"])
        cx, cy     = pin_sc * 0.48, pin_strike
        fig.add_shape(type="circle", xref="x", yref="y",
            x0=cx - pin_sc*0.68, y0=cy - si*2.8,
            x1=cx + pin_sc*0.68, y1=cy + si*2.8,
            line=dict(color=_C_PIN, width=2.8),
            fillcolor="rgba(255,255,255,0.03)")

    # ── 7. Negative gamma pocket circle (red filled) ──────────────────────────
    neg_mask = df["total_gex"] < 0
    if neg_mask.any():
        neg_sub   = df[neg_mask]
        worst_sc  = float(neg_sub["total_gex"].min()) / divisor
        worst_str = float(neg_sub.loc[neg_sub["total_gex"].idxmin(), "strike"])
        heavy     = neg_sub[neg_sub["total_gex"] <= neg_sub["total_gex"].quantile(0.30)]
        v_span    = float(heavy["strike"].max() - heavy["strike"].min()) if len(heavy) > 1 else si * 2.5
        cx, cy    = worst_sc * 0.52, worst_str
        fig.add_shape(type="circle", xref="x", yref="y",
            x0=cx - abs(worst_sc)*0.70, y0=cy - max(v_span*0.62, si*2.2),
            x1=cx + abs(worst_sc)*0.70, y1=cy + max(v_span*0.62, si*2.2),
            line=dict(color=_C_NEG, width=2.8),
            fillcolor="rgba(239,68,68,0.10)")

    # ── 8. Legend annotation (top-right) ──────────────────────────────────────
    fig.add_annotation(
        xref="paper", yref="paper",
        x=1.01, y=1.00,
        xanchor="left", yanchor="top",
        showarrow=False, align="left",
        bgcolor="rgba(8,8,8,0.90)",
        bordercolor="rgba(120,120,120,0.40)",
        borderwidth=1,
        font=dict(size=9.5, family="monospace", color="#E2E8F0"),
        width=275,
        text="<br>".join([
            "<b>Area / Feature</b>                  <b>Label / Insight</b>",
            "────────────────────────────────────",
            f"<span style='color:{_C_CALL}'>●</span>  Call Resistance        Major Dealer Resistance",
            "<span style='color:#22C55E'>●</span>  +GEX Cluster             Gamma Pin / Support",
            f"<span style='color:{_C_HVL}'>●</span>  HVL Regime Level       Volatility Trigger",
            "<span style='color:#F97316'>●</span>  –GEX Pocket              Acceleration Zone",
            f"<span style='color:{_C_SPOT}'>●</span>  Spot Price                Current Level",
            "────────────────────────────────────",
            f"<span style='color:{_C_GEX}'>━━</span> GEX Profile     per-strike bar envelope",
            f"<span style='color:{_C_CUM}'>━━</span> Cumul. GEX      running sum → zero = HVL",
        ]),
    )

    # ── 9. Layout ─────────────────────────────────────────────────────────────
    regime_lbl = (
        "Positive GEX ▲  Dealers stabilising"
        if net_regime > 0 else
        "Negative GEX ▼  Dealers amplifying"
    )
    x_right = max(gex_max, cum_max) * 1.80

    fig.update_layout(
        title=dict(
            text=(
                f"<b>Net GEX All Expirations — {symbol}</b><br>"
                f"<span style='font-size:12px;color:#64748B'>"
                f"Spot ₹{spot_price:,.2f}  ·  {regime_lbl}  ·  HVL ₹{hvl:,.0f}"
                f"</span>"
            ),
            font=dict(size=15, color="white"),
            x=0.38, y=0.97,
        ),
        plot_bgcolor=_BG_PLOT,
        paper_bgcolor=_BG_PAP,
        template="plotly_dark",
        height=740,
        hovermode="y unified",
        bargap=0.10,
        margin=dict(l=70, r=295, t=90, b=80),
        xaxis=dict(
            title=dict(text=f"GEX ({unit})" if unit else "GEX",
                       font=dict(size=11, color="#94A3B8")),
            gridcolor="rgba(255,255,255,0.045)",
            zerolinecolor="rgba(255,255,255,0.28)",
            zerolinewidth=1.8,
            tickfont=dict(size=9.5, color="#94A3B8"),
            range=[-gex_max * 1.45, x_right],
        ),
        yaxis=dict(
            title=dict(text="Strike Price", font=dict(size=11, color="#94A3B8")),
            gridcolor="rgba(255,255,255,0.045)",
            tickfont=dict(size=9.5, color="#94A3B8"),
            dtick=si * 2,
        ),
        legend=dict(
            x=0.01, y=0.01,
            bgcolor="rgba(0,0,0,0.55)",
            bordercolor="rgba(100,100,100,0.30)",
            borderwidth=1,
            font=dict(size=9.5, color="#94A3B8"),
            orientation="h",
        ),
    )

    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# generate_gex_analysis
# ═══════════════════════════════════════════════════════════════════════════════

def generate_gex_analysis(
    gex_df:       pd.DataFrame,
    spot_price:   float,
    gamma_levels: dict,
    symbol:       str = "NIFTY",
) -> list[str]:
    """
    Return 4 analysis sentences mirroring MenthorQ's bottom summary.
    Strings use **bold** markdown for emphasis.
    """
    net_gex   = gamma_levels.get("total_gex", 0)
    hvl       = gamma_levels.get("gamma_flip",         spot_price)
    call_wall = gamma_levels.get("max_call_oi_strike", spot_price)
    put_wall  = gamma_levels.get("max_put_oi_strike",  spot_price)

    above_hvl = spot_price >= hvl
    call_dist = (call_wall  - spot_price) / spot_price * 100
    hvl_dist  = abs(spot_price - hvl)    / spot_price * 100

    lines: list[str] = []

    # L1: regime
    if net_gex > 0:
        lines.append(
            f"⚡ **{symbol} is in positive gamma** — dealers buy dips and sell rallies, "
            f"dampening intraday volatility and supporting range-bound price action."
        )
    else:
        lines.append(
            f"⚡ **{symbol} is in negative gamma** — dealers must hedge in the direction "
            f"of price moves, amplifying both rallies and sell-offs."
        )

    # L2: call wall
    if call_dist > 0:
        lines.append(
            f"**Major call wall at ₹{call_wall:,.0f}** ({call_dist:.1f}% above spot) — "
            f"heavy dealer short-call positioning caps upside until cleared."
        )
    else:
        lines.append(
            f"Spot has pushed through the prior call wall (₹{call_wall:,.0f}). "
            f"Watch for new resistance from a fresh chain fetch."
        )

    # L3: HVL / cumulative GEX context
    if above_hvl:
        lines.append(
            f"Spot is **{hvl_dist:.1f}% above HVL (₹{hvl:,.0f})**. "
            f"Below HVL the cumulative GEX flips negative — "
            f"exposing a dealer short-gamma pocket that accelerates downside "
            f"toward the put wall at ₹{put_wall:,.0f}."
        )
    else:
        lines.append(
            f"Spot is **{hvl_dist:.1f}% below HVL (₹{hvl:,.0f})**. "
            f"Reclaiming HVL pushes cumulative GEX positive and flips "
            f"dealers long gamma — stabilising price action. "
            f"Put wall at ₹{put_wall:,.0f} is the near-term structural floor."
        )

    # L4: asymmetry conclusion
    if net_gex > 0 and above_hvl:
        lines.append(
            f"The market is stable near the gamma pin, but asymmetry is building: "
            f"**slow grind upside vs fast accelerated downside if HVL ₹{hvl:,.0f} breaks.**"
        )
    elif net_gex < 0:
        lines.append(
            f"**Both breakouts and breakdowns are amplified** by dealer hedging in "
            f"this negative gamma environment. Favour momentum over mean-reversion."
        )
    else:
        lines.append(
            f"**Key bifurcation: ₹{hvl:,.0f} HVL** — "
            f"above it the cumulative GEX is positive and dealers stabilise; "
            f"below it they accelerate. Watch the orange line crossing zero."
        )

    return lines
