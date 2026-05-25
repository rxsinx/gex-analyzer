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
    
    # GAMMA-BASED LEVELS (Dealer hedging zones)
    # Call Resistance: Strike with MOST NEGATIVE call_gex
    call_wall_gamma_idx = df['call_gex'].idxmin()
    call_wall_gamma = float(df.loc[call_wall_gamma_idx, 'strike']) if call_wall_gamma_idx is not None else spot_price * 1.02
    
    # Put Support: Strike with MOST POSITIVE put_gex
    put_wall_gamma_idx = df['put_gex'].idxmax()
    put_wall_gamma = float(df.loc[put_wall_gamma_idx, 'strike']) if put_wall_gamma_idx is not None else spot_price * 0.98
    
    # OI-BASED LEVELS (Volume concentration)
    call_wall_oi = float(gamma_levels.get("max_call_oi_strike", spot_price * 1.02))
    put_wall_oi = float(gamma_levels.get("max_put_oi_strike", spot_price * 0.98))
    
    # Gamma Flip Point (unchanged)
    hvl = float(gamma_levels.get("gamma_flip", spot_price * 0.99))
    
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
    fig.add_trace(go.Scatter(
        y=strikes, x=cum_gex,
        mode="lines",
        line=dict(color=_C_CUM, width=2.0, shape="spline", smoothing=0.35),
        name="Cumul. GEX",
        hovertemplate=f"<b>Strike</b> ₹%{{y:,.0f}}<br><b>Cumul. GEX</b> %{{x:.3f}} {unit}<extra></extra>",
    ))
 
    # ── 4. GAMMA-BASED H-LINES (Solid Lines - Dealer Hedging Zones) ──────────
 
    # Calculate gamma intensity for better labels
    call_gamma_intensity = abs(df.loc[call_wall_gamma_idx, 'call_gex']) if call_wall_gamma_idx is not None else 0
    put_gamma_intensity = abs(df.loc[put_wall_gamma_idx, 'put_gex']) if put_wall_gamma_idx is not None else 0
    
    # Call Resistance (Gamma) - Solid Red
    fig.add_hline(
        y=call_wall_gamma,
        line=dict(color="#ef4444", width=2.2, dash="solid"),
        annotation_text=f"  ₹{call_wall_gamma:,.0f} - Call Gamma Peak  ",
        annotation_position="top right",
        annotation_font=dict(color="#ef4444", size=10, family="monospace", weight="bold"),
    )
    
    # Put Support (Gamma) - Solid Green
    fig.add_hline(
        y=put_wall_gamma,
        line=dict(color="#22c55e", width=2.2, dash="solid"),
        annotation_text=f"  ₹{put_wall_gamma:,.0f} - Put Gamma Floor  ",
        annotation_position="bottom right",
        annotation_font=dict(color="#22c55e", size=10, family="monospace", weight="bold"),
    )
 
    # ── 5. OI-BASED H-LINES (Dashed Lines - Position Concentration) ──────────
 
    # Get OI values for context
    call_oi_value = gex_df[gex_df['strike'] == call_wall_oi]['call_oi'].values
    put_oi_value = gex_df[gex_df['strike'] == put_wall_oi]['put_oi'].values
    
    call_oi_str = f"{call_oi_value[0]/1e5:.1f}L" if len(call_oi_value) > 0 else "—"
    put_oi_str = f"{put_oi_value[0]/1e5:.1f}L" if len(put_oi_value) > 0 else "—"
    
    # Call Wall (OI) - Dashed Red
    fig.add_hline(
        y=call_wall_oi,
        line=dict(color="#ef4444", width=1.8, dash="dash"),
        annotation_text=f"  ₹{call_wall_oi:,.0f} - Call OI Cluster ({call_oi_str})  ",
        annotation_position="bottom right",
        annotation_font=dict(color="#fca5a5", size=9, family="monospace"),
    )
    
    # Put Wall (OI) - Dashed Green
    fig.add_hline(
        y=put_wall_oi,
        line=dict(color="#22c55e", width=1.8, dash="dash"),
        annotation_text=f"  ₹{put_wall_oi:,.0f} - Put OI Cluster ({put_oi_str})  ",
        annotation_position="bottom right",
        annotation_font=dict(color="#86efac", size=9, family="monospace"),
    )
 
    # ── 6. GAMMA FLIP LEVEL (HVL) ───────────────────────────────────────────
    fig.add_hline(
        y=hvl,
        line=dict(color=_C_HVL, width=1.3, dash="dash"),
        annotation_text=f"  ₹{hvl:,.0f} - Regime Flip Point  ",
        annotation_position="top left",
        annotation_font=dict(color=_C_HVL, size=9, family="monospace"),
    )
 
    # ── 7. SPOT PRICE ────────────────────────────────────────────────────────
    fig.add_hline(
        y=spot_price,
        line=dict(color=_C_SPOT, width=1.5, dash="dot"),
        annotation_text=f"  Spot ₹{spot_price:,.0f}  ",
        annotation_position="top left",
        annotation_font=dict(color=_C_SPOT, size=10, family="monospace", weight="bold"),
    )
 
    # ── 8. Level dot markers (left margin) ───────────────────────────────────
    dot_x = -gex_max * 1.25
    for price, color, name in [
        (call_wall_gamma, _C_CALL, "Call Resistance (Γ)"),
        (call_wall_oi, "#fca5a5", "Call Wall (OI)"),
        (spot_price, _C_SPOT, "Spot Price"),
        (hvl, _C_HVL, "HVL"),
        (put_wall_gamma, _C_PUT, "Put Support (Γ)"),
        (put_wall_oi, "#86efac", "Put Wall (OI)"),
    ]:
        fig.add_trace(go.Scatter(
            x=[dot_x], y=[price],
            mode="markers",
            marker=dict(size=11, color=color, symbol="circle",
                        line=dict(width=1.5, color="rgba(0,0,0,0.5)")),
            name=name, showlegend=False,
            hovertemplate=f"<b>{name}</b>  ₹{price:,.0f}<extra></extra>",
        ))
 
    # ── 9. Gamma pin circle (white) ───────────────────────────────────────────
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
 
    # ── 10. Negative gamma pocket circle (red filled) ───────────────────────
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
 
    # ── 11. Enhanced Legend annotation with detailed explanations ────────────
    fig.add_annotation(
        xref="paper", yref="paper",
        x=1.01, y=1.00,
        xanchor="left", yanchor="top",
        showarrow=False, align="left",
        bgcolor="rgba(8,8,8,0.94)",
        bordercolor="rgba(120,120,120,0.50)",
        borderwidth=1.5,
        font=dict(size=12, family="monospace", color="#E2E8F0"),
        width=340,
        text=(
            "<b>KEY LEVELS & MEANINGS</b><br>"
            "═════════════════════════════════<br>"
            "<br>"
            "<span style='color:#ef4444;font-weight:bold'>━━ CALL RESISTANCE</span><br>"
            "Solid Red Line = Highest Call Gamma<br>"
            "• Dealers MOST short gamma on calls<br>"
            "• Rally stalls here (gamma cushion)<br>"
            "• Price resistance zone<br>"
            "<br>"
            "<span style='color:#fca5a5'>─ ─ CALL WALL (OI)</span><br>"
            "Dashed Red = Peak Call Volume<br>"
            "• Largest call concentration<br>"
            "• Where most bullish bets reside<br>"
            "• Secondary resistance (volume)<br>"
            "<br>"
            "<span style='color:#22c55e;font-weight:bold'>━━ PUT SUPPORT</span><br>"
            "Solid Green Line = Highest Put Gamma<br>"
            "• Dealers MOST long gamma on puts<br>"
            "• Dips bounce here (gamma floor)<br>"
            "• Price support zone<br>"
            "<br>"
            "<span style='color:#86efac'>─ ─ PUT WALL (OI)</span><br>"
            "Dashed Green = Peak Put Volume<br>"
            "• Largest put concentration<br>"
            "• Where most bearish bets reside<br>"
            "• Secondary support (volume)<br>"
            "<br>"
            "<span style='color:#EAB308'>━━ HVL (FLIP)</span><br>"
            "Yellow Dash = Gamma Regime Change<br>"
            "• Above: Positive GEX (stable)<br>"
            "• Below: Negative GEX (volatile)<br>"
            "<br>"
            "<span style='color:#FFD700'>━━ GEX PROFILE</span><br>"
            "Bar height = per-strike gamma<br>"
            "<br>"
            "<span style='color:#FF8C00'>━━ CUMUL. GEX</span><br>"
            "Running sum; zero = regime flip<br>"
            "═════════════════════════════════"
        ),
    )
 
    # ── Layout (adjust right margin for wider legend) ───────────────────────
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
                f"<span style='font-size:11px;color:#94A3B8'>"
                f"Why Price Sticks at Certain Levels: Gamma vs Volume Analysis"
                f"<br>"
                f"Spot ₹{spot_price:,.2f}  ·  {regime_lbl}  ·  Flip ₹{hvl:,.0f}"
                f"</span>"
            ),
            font=dict(size=14, color="white"),
            x=0.35, y=0.97,
        ),
        plot_bgcolor=_BG_PLOT,
        paper_bgcolor=_BG_PAP,
        template="plotly_dark",
        height=780,
        hovermode="y unified",
        bargap=0.10,
        margin=dict(l=70, r=360, t=100, b=80),
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
 
 
# ============================================================================
# ADDITIONAL: Update the generate_gex_analysis() function text explanations
# ============================================================================
 
# In modules/menthorq_gex.py, find generate_gex_analysis() function
 
# Update the lines to include reasons:
 
def generate_gex_analysis(
    gex_df:       pd.DataFrame,
    spot_price:   float,
    gamma_levels: dict,
    symbol:       str = "NIFTY",
) -> list[str]:
    """
    Return analysis sentences explaining WHY certain levels matter
    """
    net_gex   = gamma_levels.get("total_gex", 0)
    hvl       = gamma_levels.get("gamma_flip",         spot_price)
    
    # GAMMA-BASED levels
    call_wall_gamma = gex_df.loc[gex_df['call_gex'].idxmin(), 'strike']
    put_wall_gamma = gex_df.loc[gex_df['put_gex'].idxmax(), 'strike']
    
    # OI-BASED levels
    call_wall_oi = float(gamma_levels.get("max_call_oi_strike", spot_price))
    put_wall_oi = float(gamma_levels.get("max_put_oi_strike", spot_price))
    
    above_hvl = spot_price >= hvl
    call_dist = (call_wall_gamma - spot_price) / spot_price * 100
    put_dist = (spot_price - put_wall_gamma) / spot_price * 100
    hvl_dist  = abs(spot_price - hvl) / spot_price * 100
 
    lines: list[str] = []
 
    # L1: Regime explanation
    if net_gex > 0:
        lines.append(
            f"⚡ Positive Gamma Regime — Dealers are net long gamma across the board. "
            f"This means when spot moves down slightly, dealers must BUY (support), "
            f"and when spot moves up, dealers SELL (resistance). Price action is stabilized."
        )
    else:
        lines.append(
            f"⚡ Negative Gamma Regime — Dealers are net short gamma, forced to hedge in the direction of moves. "
            f"Down moves trigger MORE selling, up moves trigger MORE buying. Price action is amplified (trending)."
        )
 
    # L2: Call Resistance explanation
    lines.append(
        f"📊 Call Resistance @ ₹{call_wall_gamma:,.0f} (Gamma) — This is where the STRONGEST call gamma concentration exists. "
        f"Dealers holding short calls must hedge by selling into rallies near this strike. "
        f"Spot is {abs(call_dist):.1f}% {'below' if call_dist > 0 else 'above'} this level. "
        f"Separately, call volume is concentrated @ ₹{call_wall_oi:,.0f} (OI-based)."
    )
 
    # L3: Put Support explanation
    lines.append(
        f"🛡️ Put Support @ ₹{put_wall_gamma:,.0f} (Gamma) — This is where the STRONGEST put gamma floor exists. "
        f"Dealers holding long puts have gamma that ACCELERATES buying into dips. "
        f"Spot is {abs(put_dist):.1f}% above this level. "
        f"Separately, put volume is concentrated @ ₹{put_wall_oi:,.0f} (OI-based)."
    )
 
    # L4: HVL and asymmetry
    if above_hvl:
        lines.append(
            f"⚠️ Gamma Flip Risk — Spot is {hvl_dist:.1f}% above HVL (₹{hvl:,.0f}). "
            f"If spot breaks BELOW HVL, cumulative GEX flips negative, exposing a dealer short-gamma pocket. "
            f"This accelerates selling pressure down toward the put wall ₹{put_wall_gamma:,.0f}. "
            f"The asymmetry: slow up, fast down (if flip occurs)."
        )
    else:
        lines.append(
            f"✅ Stable Below HVL — Spot is {hvl_dist:.1f}% below HVL (₹{hvl:,.0f}). "
            f"Cumulative GEX is negative here, but as long as spot stays above the put floor ₹{put_wall_gamma:,.0f}, "
            f"the market is contained. Reclaiming HVL would reset cumulative GEX positive (more stable)."
        )
 
    return lines
