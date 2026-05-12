"""
Professional visualization module for GEX Terminal
Includes: GEX, OI, IV Smile, Greeks, PCR, VIX + Index 1-Hr with dynamic S/R
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ═══════════════════════════════════════════════════════════════════════════════
# Existing GEX / options charts (unchanged)
# ═══════════════════════════════════════════════════════════════════════════════

def plot_gex_profile(gex_df, spot_price, gamma_levels):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=gex_df['strike'], y=gex_df['call_gex'],
                         name='Call GEX', marker_color='rgba(239,68,68,0.7)',
                         hovertemplate='<b>Strike:</b> %{x}<br><b>Call GEX:</b> %{y:,.0f}<extra></extra>'))
    fig.add_trace(go.Bar(x=gex_df['strike'], y=gex_df['put_gex'],
                         name='Put GEX', marker_color='rgba(34,197,94,0.7)',
                         hovertemplate='<b>Strike:</b> %{x}<br><b>Put GEX:</b> %{y:,.0f}<extra></extra>'))
    fig.add_vline(x=spot_price, line_dash="dash", line_color="blue",
                  annotation_text=f"Spot: ₹{spot_price:,.0f}", annotation_position="top right")
    if gamma_levels.get('gamma_flip'):
        fig.add_vline(x=gamma_levels['gamma_flip'], line_dash="dot", line_color="purple",
                      annotation_text=f"Flip: ₹{gamma_levels['gamma_flip']:,.0f}",
                      annotation_position="bottom right")
    if gamma_levels.get('max_pain'):
        fig.add_vline(x=gamma_levels['max_pain'], line_dash="dashdot", line_color="orange",
                      annotation_text=f"Max Pain: ₹{gamma_levels['max_pain']:,.0f}",
                      annotation_position="top left")
    fig.add_hline(y=0, line_dash="solid", line_color="gray", line_width=1)
    fig.update_layout(title="📊 Gamma Exposure Profile", xaxis_title="Strike (₹)",
                      yaxis_title="GEX", barmode='relative', hovermode='x unified',
                      template='plotly_dark', height=500)
    return fig


def plot_oi_analysis(gex_df, spot_price):
    fig = make_subplots(rows=2, cols=1,
                        subplot_titles=('Open Interest Distribution', 'Volume Distribution'),
                        vertical_spacing=0.15, row_heights=[0.6, 0.4])
    fig.add_trace(go.Bar(x=gex_df['strike'], y=gex_df['call_oi'], name='Call OI',
                         marker_color='rgba(239,68,68,0.6)',
                         hovertemplate='<b>Strike:</b> %{x}<br><b>Call OI:</b> %{y:,.0f}<extra></extra>'), row=1, col=1)
    fig.add_trace(go.Bar(x=gex_df['strike'], y=gex_df['put_oi'], name='Put OI',
                         marker_color='rgba(34,197,94,0.6)',
                         hovertemplate='<b>Strike:</b> %{x}<br><b>Put OI:</b> %{y:,.0f}<extra></extra>'), row=1, col=1)
    fig.add_trace(go.Bar(x=gex_df['strike'], y=gex_df['call_volume'], name='Call Vol',
                         marker_color='rgba(239,68,68,0.4)', showlegend=False,
                         hovertemplate='<b>Strike:</b> %{x}<br><b>Call Vol:</b> %{y:,.0f}<extra></extra>'), row=2, col=1)
    fig.add_trace(go.Bar(x=gex_df['strike'], y=gex_df['put_volume'], name='Put Vol',
                         marker_color='rgba(34,197,94,0.4)', showlegend=False,
                         hovertemplate='<b>Strike:</b> %{x}<br><b>Put Vol:</b> %{y:,.0f}<extra></extra>'), row=2, col=1)
    fig.add_vline(x=spot_price, line_dash="dash", line_color="blue", row=1, col=1)
    fig.add_vline(x=spot_price, line_dash="dash", line_color="blue", row=2, col=1)
    fig.update_xaxes(title_text="Strike (₹)", row=2, col=1)
    fig.update_yaxes(title_text="Open Interest", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    fig.update_layout(barmode='group', template='plotly_dark', height=600, hovermode='x unified')
    return fig


def plot_iv_smile(gex_df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=gex_df['strike'], y=gex_df['call_iv'], mode='lines+markers',
                             name='Call IV', line=dict(color='rgb(239,68,68)', width=2),
                             hovertemplate='<b>Strike:</b> %{x}<br><b>Call IV:</b> %{y:.2f}%<extra></extra>'))
    fig.add_trace(go.Scatter(x=gex_df['strike'], y=gex_df['put_iv'], mode='lines+markers',
                             name='Put IV', line=dict(color='rgb(34,197,94)', width=2),
                             hovertemplate='<b>Strike:</b> %{x}<br><b>Put IV:</b> %{y:.2f}%<extra></extra>'))
    fig.update_layout(title="📈 Volatility Smile", xaxis_title="Strike (₹)",
                      yaxis_title="IV (%)", template='plotly_dark', height=400, hovermode='x unified')
    return fig


def plot_greeks_heatmap(gex_df, greek_name='gamma'):
    cg, pg = f'call_{greek_name}', f'put_{greek_name}'
    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=(f'Call {greek_name.title()}', f'Put {greek_name.title()}'),
                        horizontal_spacing=0.15)
    fig.add_trace(go.Bar(x=gex_df['strike'], y=gex_df[cg], name=f'Call {greek_name.title()}',
                         marker_color='rgba(239,68,68,0.7)'), row=1, col=1)
    fig.add_trace(go.Bar(x=gex_df['strike'], y=gex_df[pg], name=f'Put {greek_name.title()}',
                         marker_color='rgba(34,197,94,0.7)'), row=1, col=2)
    fig.update_layout(template='plotly_dark', height=400, showlegend=False)
    return fig


def plot_pcr_analysis(gex_df):
    pcr_vals = [row['put_oi'] / row['call_oi'] if row['call_oi'] > 0 else 0
                for _, row in gex_df.iterrows()]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=gex_df['strike'], y=pcr_vals, mode='lines+markers',
                             name='PCR', line=dict(color='purple', width=2),
                             fill='tozeroy', fillcolor='rgba(128,0,128,0.2)',
                             hovertemplate='<b>Strike:</b> %{x}<br><b>PCR:</b> %{y:.2f}<extra></extra>'))
    fig.add_hline(y=1,   line_dash="dash", line_color="gray",  annotation_text="PCR=1")
    fig.add_hline(y=0.8, line_dash="dot",  line_color="green", annotation_text="Bullish(0.8)")
    fig.add_hline(y=1.2, line_dash="dot",  line_color="red",   annotation_text="Bearish(1.2)")
    fig.update_layout(title="📊 PCR by Strike", xaxis_title="Strike (₹)",
                      yaxis_title="PCR", template='plotly_dark', height=400, hovermode='x unified')
    return fig


def plot_spot_gex_levels(gex_df, spot_price, gamma_levels, price_range=500):
    x = np.arange(spot_price - price_range, spot_price + price_range, 10)
    y = [gex_df['total_gex'].sum()] * len(x)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode='lines', name='Net GEX',
                             line=dict(color='blue', width=3),
                             fill='tozeroy', fillcolor='rgba(59,130,246,0.3)'))
    fig.add_vline(x=spot_price, line_dash="dash", line_color="red",
                  annotation_text=f"Current: ₹{spot_price:,.0f}")
    fig.add_hline(y=0, line_dash="solid", line_color="gray")
    fig.update_layout(title="📉 Net GEX vs Spot", xaxis_title="Spot (₹)",
                      yaxis_title="Net GEX", template='plotly_dark', height=400,
                      hovermode='x unified')
    return fig


def create_summary_metrics(gex_df, gamma_levels, spot_price):
    net_gex = gex_df['total_gex'].sum()
    return {
        'Total Call GEX': f"{gex_df['call_gex'].sum():,.0f}",
        'Total Put GEX':  f"{gex_df['put_gex'].sum():,.0f}",
        'Net GEX':        f"{net_gex:,.0f}",
        'Gamma Flip':     gamma_levels.get('gamma_flip', 'N/A'),
        'Max Pain':       gamma_levels.get('max_pain', 'N/A'),
        'PCR':            f"{gamma_levels.get('pcr', 0):.2f}",
        'Market Regime':  'Positive Gamma' if net_gex > 0 else 'Negative Gamma',
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Index + VIX 1-hour chart with dynamic S/R
# ═══════════════════════════════════════════════════════════════════════════════

# VIX colour zones (background shading on VIX panel)
_VIX_ZONES = [
    (0,  12,  "rgba(34,197,94,0.08)",  "Calm"),
    (12, 15,  "rgba(163,230,53,0.08)", "Low"),
    (15, 20,  "rgba(234,179,8,0.08)",  "Normal"),
    (20, 25,  "rgba(249,115,22,0.10)", "Elevated"),
    (25, 35,  "rgba(239,68,68,0.12)",  "High Fear"),
    (35, 100, "rgba(185,28,28,0.18)",  "Extreme Fear"),
]

# S/R line styles per type
_LEVEL_STYLE: dict[str, dict] = {
    "support":    {"color": "rgba(34,197,94,0.85)",  "dash": "solid",  "width": 1.5},
    "resistance": {"color": "rgba(239,68,68,0.85)",  "dash": "solid",  "width": 1.5},
    "pivot":      {"color": "rgba(168,85,247,0.75)", "dash": "dot",    "width": 1.2},
    "prev_day":   {"color": "rgba(251,191,36,0.85)", "dash": "dashdot","width": 1.5},
    "round":      {"color": "rgba(148,163,184,0.40)","dash": "dot",    "width": 0.8},
}


def plot_index_vix_chart(
    index_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    symbol: str,
    levels: dict,
    spot_price: Optional[float] = None,
    interval_label: str = "1 Hr",
) -> go.Figure:
    """
    3-panel interactive chart
    ──────────────────────────
    Panel 1 (68%): Index candlestick + dynamic S/R lines
    Panel 2 (12%): Volume bars (greyed out for index – often 0)
    Panel 3 (20%): India VIX line with fear-zone bands

    Parameters
    ----------
    index_df  : OHLCV DataFrame, DatetimeIndex
    vix_df    : OHLCV DataFrame, DatetimeIndex
    symbol    : e.g. 'NIFTY'
    levels    : dict from chart_analysis.analyse_levels()
    spot_price: current spot (draws horizontal reference)
    interval_label: shown in title
    """
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.68, 0.12, 0.20],
        vertical_spacing=0.02,
        subplot_titles=[
            f"{symbol}  {interval_label}",
            "Volume",
            "India VIX",
        ],
    )

    # ── Panel 1: Candlestick ──────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=index_df.index,
        open=index_df["open"],
        high=index_df["high"],
        low=index_df["low"],
        close=index_df["close"],
        name=symbol,
        increasing=dict(line=dict(color="#22c55e", width=1),
                        fillcolor="#22c55e"),
        decreasing=dict(line=dict(color="#ef4444", width=1),
                        fillcolor="#ef4444"),
        showlegend=False,
    ), row=1, col=1)

    # ── current spot line ─────────────────────────────────────────────────────
    if spot_price:
        fig.add_hline(
            y=spot_price, row=1, col=1,
            line=dict(color="rgba(96,165,250,0.9)", dash="dash", width=1.5),
            annotation_text=f"  LTP ₹{spot_price:,.0f}",
            annotation_position="right",
            annotation_font=dict(color="#60a5fa", size=11),
        )

    # ── S/R lines on Panel 1 ─────────────────────────────────────────────────
    _draw_levels(fig, levels, index_df, row=1)

    # ── Panel 2: Volume ───────────────────────────────────────────────────────
    if "volume" in index_df.columns:
        colours = [
            "#22c55e" if c >= o else "#ef4444"
            for o, c in zip(index_df["open"], index_df["close"])
        ]
        fig.add_trace(go.Bar(
            x=index_df.index,
            y=index_df["volume"],
            name="Volume",
            marker_color=colours,
            opacity=0.6,
            showlegend=False,
            hovertemplate="<b>%{x}</b><br>Vol: %{y:,.0f}<extra></extra>",
        ), row=2, col=1)

    # ── Panel 3: India VIX ───────────────────────────────────────────────────
    # Fear-zone background bands
    x_min = vix_df.index.min()
    x_max = vix_df.index.max()
    for lo, hi, colour, label in _VIX_ZONES:
        fig.add_hrect(
            y0=lo, y1=hi, row=3, col=1,
            fillcolor=colour, line_width=0,
            annotation_text=f" {label}" if lo > 0 else "",
            annotation_position="top left",
            annotation_font=dict(size=9, color="rgba(200,200,200,0.6)"),
        )

    # VIX line
    fig.add_trace(go.Scatter(
        x=vix_df.index,
        y=vix_df["close"],
        name="India VIX",
        mode="lines",
        line=dict(color="#f97316", width=2),
        fill="tozeroy",
        fillcolor="rgba(249,115,22,0.12)",
        hovertemplate="<b>%{x}</b><br>VIX: %{y:.2f}<extra></extra>",
    ), row=3, col=1)

    # current VIX label
    latest_vix = float(vix_df["close"].iloc[-1])
    vix_colour = (
        "#22c55e" if latest_vix < 15 else
        "#eab308" if latest_vix < 20 else
        "#f97316" if latest_vix < 25 else
        "#ef4444"
    )
    fig.add_annotation(
        x=vix_df.index[-1], y=latest_vix,
        text=f"  VIX {latest_vix:.1f}",
        showarrow=False, xref="x3", yref="y3",
        font=dict(color=vix_colour, size=12, family="monospace"),
        xanchor="left",
    )

    # ── layout ────────────────────────────────────────────────────────────────
    fig.update_layout(
        template="plotly_dark",
        height=750,
        hovermode="x unified",
        showlegend=False,
        margin=dict(l=60, r=40, t=60, b=20),
        xaxis_rangeslider_visible=False,
        plot_bgcolor="rgba(15,23,42,1)",
        paper_bgcolor="rgba(15,23,42,1)",
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor="rgba(51,65,85,0.5)",
        tickformat="%d %b\n%H:%M",
    )
    fig.update_yaxes(showgrid=True, gridcolor="rgba(51,65,85,0.5)")
    fig.update_yaxes(title_text=symbol, row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    fig.update_yaxes(title_text="VIX", row=3, col=1)

    return fig


def _draw_levels(fig: go.Figure, levels: dict, df: pd.DataFrame, row: int):
    """Add horizontal S/R lines to fig panel *row*."""
    # Compute price range visible on chart for clipping labels
    price_min = float(df["low"].min())
    price_max = float(df["high"].max())

    drawn: set[float] = set()  # avoid duplicate lines

    for level_type, items in levels.items():
        style = _LEVEL_STYLE.get(level_type, _LEVEL_STYLE["pivot"])
        for lvl in items:
            p = lvl.price
            # clip to visible range (with 5 % margin)
            if p < price_min * 0.95 or p > price_max * 1.05:
                continue
            # deduplicate within 0.05 %
            if any(abs(p - d) / max(d, 1) < 0.0005 for d in drawn):
                continue
            drawn.add(p)

            # stronger levels get thicker lines
            lw = style["width"] * (1.4 if lvl.strength == "strong" else 1.0)

            fig.add_hline(
                y=p, row=row, col=1,
                line=dict(
                    color=style["color"],
                    dash=style["dash"],
                    width=lw,
                ),
                annotation_text=f"  {lvl.label} ₹{p:,.0f}",
                annotation_position="right",
                annotation_font=dict(
                    color=style["color"].replace("0.85", "1").replace("0.75", "1"),
                    size=9,
                ),
            )


# ── S/R summary table ────────────────────────────────────────────────────────

def build_levels_table(levels: dict, spot: float) -> pd.DataFrame:
    """
    Flatten all levels into a DataFrame for display,
    sorted by proximity to spot.
    """
    from modules.chart_analysis import PriceLevel
    rows: list[dict] = []
    for ltype, items in levels.items():
        for lvl in items:
            dist_pct = (lvl.price - spot) / spot * 100
            rows.append({
                "Level":    f"₹{lvl.price:,.1f}",
                "Type":     lvl.label or ltype.title(),
                "Category": ltype.replace("_", " ").title(),
                "Touches":  lvl.touches,
                "Strength": lvl.strength.title(),
                "From Spot": f"{dist_pct:+.2f}%",
                "_dist_abs": abs(dist_pct),
                "_price":   lvl.price,
            })
    if not rows:
        return pd.DataFrame()
    df = (pd.DataFrame(rows)
          .sort_values("_dist_abs")
          .drop(columns=["_dist_abs", "_price"])
          .reset_index(drop=True))
    return df
