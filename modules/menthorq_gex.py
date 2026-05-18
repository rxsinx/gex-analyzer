"""
modules/menthorq_gex.py
========================
MenthorQ-style horizontal Net GEX chart for the GEX Terminal.

Visual elements replicated
--------------------------
1. Horizontal bars      — positive GEX (green gradient), negative GEX (red/orange gradient)
2. GEX Profile line     — yellow smooth curve tracing bar tips (same data as bars, as Scatter)
3. DEX Profile line     — orange smooth curve, DEX values scaled to fit same axis
4. Key level h-lines    — Call Resistance (red), Put Support (green), HVL/Flip (yellow), Spot (gray)
5. Level dot markers    — colored dots on the left margin at each key price level
6. Gamma pin circle     — white open circle around peak positive GEX cluster near spot
7. Neg gamma pocket     — red filled circle around worst negative GEX cluster
8. Legend table         — top-right annotation box (Area | Symbol | Insight)
9. Analysis text        — auto-generated market structure summary (5 lines, rendered in Streamlit)

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


# ── colour palette ────────────────────────────────────────────────────────────
_C_CALL_WALL  = "#EF4444"   # red
_C_PUT_WALL   = "#22C55E"   # green
_C_HVL        = "#EAB308"   # yellow
_C_SPOT       = "#CBD5E1"   # cool-gray / near-white
_C_GEX_LINE   = "#FFD700"   # gold (GEX profile)
_C_DEX_LINE   = "#FF8C00"   # dark-orange (DEX profile)
_C_PIN_CIRCLE = "rgba(255,255,255,0.85)"
_C_NEG_CIRCLE = "rgba(239,68,68,0.85)"
_BG_PLOT      = "#060606"
_BG_PAPER     = "#0A0A0A"


# ── helpers ───────────────────────────────────────────────────────────────────

def _auto_scale(values: np.ndarray) -> tuple[float, str]:
    """Return (divisor, unit_label) so displayed values are in 1–999 range."""
    mx = max(abs(values).max(), 1.0)
    if mx >= 1e7:
        return 1e7, "Cr"
    if mx >= 1e5:
        return 1e5, "L"
    return 1.0, ""


def _bar_colour(v: float, v_max: float) -> str:
    """Return RGBA colour for one bar depending on sign and magnitude."""
    intensity = min(abs(v) / v_max, 1.0)
    if v >= 0:
        # faint → bright green
        alpha = 0.38 + intensity * 0.52
        return f"rgba(34,197,94,{alpha:.2f})"
    else:
        # orange → deep red
        r = int(185 + intensity * 58)
        g = int(55  * (1.0 - intensity * 0.85))
        return f"rgba({r},{g},12,0.90)"


# ═══════════════════════════════════════════════════════════════════════════════
# Main chart
# ═══════════════════════════════════════════════════════════════════════════════

def plot_menthorq_gex(
    gex_df:       pd.DataFrame,
    spot_price:   float,
    gamma_levels: dict,
    symbol:       str = "NIFTY",
) -> go.Figure:
    """
    Build and return the MenthorQ-style horizontal GEX figure.

    Parameters
    ----------
    gex_df       : output of calculate_gex()
    spot_price   : current spot price
    gamma_levels : output of find_gamma_levels()
    symbol       : index name shown in title (e.g. 'NIFTY')
    """
    df = gex_df.sort_values("strike").copy()
    strikes   = df["strike"].values.astype(float)
    net_gex   = df["total_gex"].values.astype(float)
    total_dex = df["total_dex"].values.astype(float)

    # ── scale ─────────────────────────────────────────────────────────────────
    divisor, unit = _auto_scale(net_gex)
    gex_sc  = net_gex / divisor                          # display units
    gex_max = float(max(abs(gex_sc).max(), 0.01))

    # DEX: normalise to 150 % of GEX display range
    dex_raw_max = float(max(abs(total_dex).max(), 1.0))
    dex_disp    = total_dex / dex_raw_max * gex_max * 1.5

    # strike interval → bar width
    si        = float(np.median(np.diff(np.sort(strikes)))) if len(strikes) > 1 else 50.0
    bar_width = si * 0.78

    # bar colours
    bar_colors = [_bar_colour(v, gex_max) for v in gex_sc]

    # ── key levels ─────────────────────────────────────────────────────────────
    call_wall  = float(gamma_levels.get("max_call_oi_strike", spot_price * 1.02))
    put_wall   = float(gamma_levels.get("max_put_oi_strike",  spot_price * 0.98))
    hvl        = float(gamma_levels.get("gamma_flip",         spot_price * 0.99))
    net_regime = gamma_levels.get("total_gex", 0)

    fig = go.Figure()

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. Horizontal GEX bars
    # ═══════════════════════════════════════════════════════════════════════════
    fig.add_trace(go.Bar(
        y=strikes,
        x=gex_sc,
        orientation="h",
        width=bar_width,
        marker=dict(color=bar_colors, line=dict(width=0)),
        name="Net GEX",
        hovertemplate=(
            "<b>Strike</b> ₹%{y:,.0f}<br>"
            f"<b>Net GEX</b> %{{x:.3f}} {unit}"
            "<extra></extra>"
        ),
    ))

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. GEX Profile line (yellow) — smooth envelope through bar tips
    # ═══════════════════════════════════════════════════════════════════════════
    fig.add_trace(go.Scatter(
        y=strikes,
        x=gex_sc,
        mode="lines",
        line=dict(color=_C_GEX_LINE, width=2.3, shape="spline", smoothing=0.35),
        name="GEX Profile",
        hoverinfo="skip",
    ))

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. DEX Profile line (orange)
    # ═══════════════════════════════════════════════════════════════════════════
    fig.add_trace(go.Scatter(
        y=strikes,
        x=dex_disp,
        mode="lines",
        line=dict(color=_C_DEX_LINE, width=1.8, shape="spline", smoothing=0.35),
        name="DEX Profile",
        hoverinfo="skip",
    ))

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. Key level horizontal lines
    # ═══════════════════════════════════════════════════════════════════════════
    _hlines = [
        (call_wall,  _C_CALL_WALL, "dash", f"Call Resistance: {call_wall:,.0f}", "top right"),
        (put_wall,   _C_PUT_WALL,  "dash", f"Put Support: {put_wall:,.0f}",      "top right"),
        (hvl,        _C_HVL,       "dash", f"HVL: {hvl:,.0f}",                   "top left"),
        (spot_price, _C_SPOT,      "dot",  f"Spot: {spot_price:,.0f}",            "top left"),
    ]
    for price, color, dash, label, pos in _hlines:
        fig.add_hline(
            y=price,
            line=dict(color=color, width=1.3, dash=dash),
            annotation_text=f"  {label}  ",
            annotation_position=pos,
            annotation_font=dict(color=color, size=9, family="monospace"),
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # 5. Coloured dot markers on left margin
    # ═══════════════════════════════════════════════════════════════════════════
    dot_x = -gex_max * 1.25
    _dots = [
        (call_wall,  _C_CALL_WALL, "Call Resistance"),
        (spot_price, _C_SPOT,      "Spot Price"),
        (hvl,        _C_HVL,       "HVL"),
        (put_wall,   _C_PUT_WALL,  "Put Support"),
    ]
    for price, color, name in _dots:
        fig.add_trace(go.Scatter(
            x=[dot_x], y=[price],
            mode="markers",
            marker=dict(size=13, color=color, symbol="circle",
                        line=dict(width=1.5, color="rgba(0,0,0,0.5)")),
            name=name,
            showlegend=False,
            hovertemplate=f"<b>{name}</b>  ₹{price:,.0f}<extra></extra>",
        ))

    # ═══════════════════════════════════════════════════════════════════════════
    # 6. Gamma pin zone — white open circle around peak +GEX cluster near spot
    # ═══════════════════════════════════════════════════════════════════════════
    near_mask = (
        (df["strike"] >= spot_price * 0.965) &
        (df["strike"] <= spot_price * 1.035) &
        (df["total_gex"] > 0)
    )
    if near_mask.any():
        near_sub   = df[near_mask]
        pin_raw    = float(near_sub["total_gex"].max())
        pin_sc     = pin_raw / divisor
        pin_strike = float(near_sub.loc[near_sub["total_gex"].idxmax(), "strike"])

        cx  = pin_sc * 0.48           # circle centre x (between 0 and peak bar)
        cy  = pin_strike
        r_x = pin_sc * 0.68           # horizontal radius (data coords)
        r_y = si * 2.8                # vertical radius (strike units)

        fig.add_shape(
            type="circle",
            xref="x", yref="y",
            x0=cx - r_x, y0=cy - r_y,
            x1=cx + r_x, y1=cy + r_y,
            line=dict(color=_C_PIN_CIRCLE, width=2.8),
            fillcolor="rgba(255,255,255,0.03)",
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # 7. Negative gamma pocket — red filled circle around worst –GEX cluster
    # ═══════════════════════════════════════════════════════════════════════════
    neg_mask = df["total_gex"] < 0
    if neg_mask.any():
        neg_sub    = df[neg_mask]
        worst_raw  = float(neg_sub["total_gex"].min())
        worst_sc   = worst_raw / divisor          # negative value
        worst_str  = float(neg_sub.loc[neg_sub["total_gex"].idxmin(), "strike"])

        # vertical span: cluster of heavy-negative strikes (bottom 30 %)
        heavy = neg_sub[neg_sub["total_gex"] <= neg_sub["total_gex"].quantile(0.30)]
        v_span = float(heavy["strike"].max() - heavy["strike"].min()) if len(heavy) > 1 else si * 2.5

        cx  = worst_sc * 0.52           # centre on the left (negative) side
        cy  = worst_str
        r_x = abs(worst_sc) * 0.70
        r_y = max(v_span * 0.62, si * 2.2)

        fig.add_shape(
            type="circle",
            xref="x", yref="y",
            x0=cx - r_x, y0=cy - r_y,
            x1=cx + r_x, y1=cy + r_y,
            line=dict(color=_C_NEG_CIRCLE, width=2.8),
            fillcolor="rgba(239,68,68,0.10)",
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # 8. Legend annotation (top-right box — mirrors MenthorQ table)
    # ═══════════════════════════════════════════════════════════════════════════
    _legend_lines = [
        ("<b>Area / Feature</b>",                   "",           "<b>Label / Insight</b>"),
        ("─────────────────",                        "",           "──────────────────────"),
        (f"<span style='color:{_C_CALL_WALL}'>●</span>  Call Resistance",     "", "Major Dealer Resistance"),
        ("<span style='color:#22C55E'>●</span>  Positive Gamma Cluster", "", "Gamma Pin / Supportive Flow"),
        (f"<span style='color:{_C_HVL}'>●</span>  HVL Regime Level",           "", "Volatility Trigger"),
        ("<span style='color:#F97316'>●</span>  Negative Gamma Pocket", "", "Acceleration Zone"),
        (f"<span style='color:{_C_SPOT}'>●</span>  Spot Price",                  "", "Current Level"),
    ]
    legend_html = "<br>".join(
        f"{l}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{r}" for l, _, r in _legend_lines
    )
    fig.add_annotation(
        xref="paper", yref="paper",
        x=1.01, y=1.00,
        xanchor="left", yanchor="top",
        text=legend_html,
        showarrow=False,
        align="left",
        bgcolor="rgba(8,8,8,0.90)",
        bordercolor="rgba(120,120,120,0.40)",
        borderwidth=1,
        font=dict(size=9.5, family="monospace", color="#E2E8F0"),
        width=260,
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # 9. Layout
    # ═══════════════════════════════════════════════════════════════════════════
    regime_label = (
        "Positive GEX ▲  Dealers dampening volatility"
        if net_regime > 0 else
        "Negative GEX ▼  Dealers amplifying volatility"
    )
    flip_str = f"₹{hvl:,.0f}"

    fig.update_layout(
        title=dict(
            text=(
                f"<b>Net GEX All Expirations — {symbol}</b><br>"
                f"<span style='font-size:12px;color:#64748B'>"
                f"Spot ₹{spot_price:,.2f}  ·  {regime_label}  ·  HVL {flip_str}"
                f"</span>"
            ),
            font=dict(size=15, color="white"),
            x=0.38,
            y=0.97,
        ),
        plot_bgcolor=_BG_PLOT,
        paper_bgcolor=_BG_PAPER,
        template="plotly_dark",
        height=740,
        hovermode="y unified",
        bargap=0.10,
        margin=dict(l=70, r=280, t=90, b=80),

        xaxis=dict(
            title=dict(
                text=f"GEX ({unit})" if unit else "GEX",
                font=dict(size=11, color="#94A3B8"),
            ),
            gridcolor="rgba(255,255,255,0.045)",
            zerolinecolor="rgba(255,255,255,0.28)",
            zerolinewidth=1.8,
            tickfont=dict(size=9.5, color="#94A3B8"),
            range=[-gex_max * 1.45, gex_max * 1.8],
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
            traceorder="normal",
        ),
    )

    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# Analysis text generator
# ═══════════════════════════════════════════════════════════════════════════════

def generate_gex_analysis(
    gex_df:       pd.DataFrame,
    spot_price:   float,
    gamma_levels: dict,
    symbol:       str = "NIFTY",
) -> list[str]:
    """
    Return a list of 4–5 analysis sentences that mirror MenthorQ's bottom summary.
    Each string may contain <b>…</b> tags for bold emphasis (render with
    st.markdown or st.caption with unsafe_allow_html=True).
    """
    net_gex    = gamma_levels.get("total_gex", 0)
    hvl        = gamma_levels.get("gamma_flip", spot_price)
    call_wall  = gamma_levels.get("max_call_oi_strike", spot_price)
    put_wall   = gamma_levels.get("max_put_oi_strike",  spot_price)
    pcr        = gamma_levels.get("pcr", 1.0)

    above_hvl  = spot_price >= hvl
    call_dist  = (call_wall  - spot_price) / spot_price * 100
    put_dist   = (spot_price - put_wall)   / spot_price * 100
    hvl_dist   = abs(spot_price - hvl)    / spot_price * 100

    lines: list[str] = []

    # ── L1: regime summary ────────────────────────────────────────────────
    if net_gex > 0:
        lines.append(
            f"⚡ **{symbol} is in positive gamma** — dealers are hedging by buying dips and "
            f"selling rallies, supporting stable price action and dampening intraday volatility."
        )
    else:
        lines.append(
            f"⚡ **{symbol} is in negative gamma** — dealers must hedge in the direction of "
            f"price movement, amplifying both upsides and downsides. Expect wider ranges."
        )

    # ── L2: call wall ─────────────────────────────────────────────────────
    if call_dist > 0:
        lines.append(
            f"Price is approaching a **major call wall at ₹{call_wall:,.0f}** "
            f"({call_dist:.1f}% above spot) — heavy dealer short-call positioning "
            f"acts as a structural ceiling limiting upside expansion."
        )
    else:
        lines.append(
            f"Spot has broken above the prior call wall (₹{call_wall:,.0f}). "
            f"Next resistance from options flow needs to be identified on a fresh chain."
        )

    # ── L3: HVL context ───────────────────────────────────────────────────
    if above_hvl:
        lines.append(
            f"Spot is **{hvl_dist:.1f}% above the HVL (₹{hvl:,.0f})**. "
            f"Below HVL, the gamma regime flips — exposing a negative gamma pocket "
            f"that can accelerate downside toward the put wall at ₹{put_wall:,.0f}."
        )
    else:
        lines.append(
            f"Spot is **{hvl_dist:.1f}% below the HVL (₹{hvl:,.0f})**. "
            f"Reclaiming the HVL would flip dealers long gamma and stabilise price action. "
            f"Put wall at ₹{put_wall:,.0f} is the next structural support."
        )

    # ── L4: asymmetry conclusion ──────────────────────────────────────────
    if net_gex > 0 and above_hvl:
        lines.append(
            f"The market is stable near gamma pin, but asymmetry is building: "
            f"**slow grind upside vs fast accelerated downside if HVL at ₹{hvl:,.0f} breaks.**"
        )
    elif net_gex < 0:
        lines.append(
            f"In this negative gamma environment, **both breakouts and breakdowns will be "
            f"amplified by dealer hedging**. Mean-reversion strategies underperform; "
            f"momentum and volatility plays are favoured."
        )
    else:
        lines.append(
            f"**Key bifurcation level: ₹{hvl:,.0f} (HVL)** — "
            f"above it, positive gamma stabilises; below it, negative gamma accelerates."
        )

    return lines
