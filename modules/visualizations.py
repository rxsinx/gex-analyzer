"""
Professional visualization module for GEX Terminal
Includes: GEX, OI, IV Smile, Greeks Heatmap, Max Pain, Volume Analysis
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np


def plot_gex_profile(gex_df, spot_price, gamma_levels):
    """Enhanced GEX profile with annotations"""
    fig = go.Figure()
    
    # Call GEX
    fig.add_trace(go.Bar(
        x=gex_df['strike'],
        y=gex_df['call_gex'],
        name='Call GEX',
        marker_color='rgba(239, 68, 68, 0.7)',
        hovertemplate='<b>Strike:</b> %{x}<br><b>Call GEX:</b> %{y:,.0f}<extra></extra>'
    ))
    
    # Put GEX
    fig.add_trace(go.Bar(
        x=gex_df['strike'],
        y=gex_df['put_gex'],
        name='Put GEX',
        marker_color='rgba(34, 197, 94, 0.7)',
        hovertemplate='<b>Strike:</b> %{x}<br><b>Put GEX:</b> %{y:,.0f}<extra></extra>'
    ))
    
    # Spot price
    fig.add_vline(x=spot_price, line_dash="dash", line_color="blue",
                  annotation_text=f"Spot: ₹{spot_price:,.0f}", annotation_position="top right")
    
    # Gamma flip
    if gamma_levels.get('gamma_flip'):
        fig.add_vline(x=gamma_levels['gamma_flip'], line_dash="dot", line_color="purple",
                      annotation_text=f"Flip: ₹{gamma_levels['gamma_flip']:,.0f}", 
                      annotation_position="bottom right")
    
    # Max Pain
    if gamma_levels.get('max_pain'):
        fig.add_vline(x=gamma_levels['max_pain'], line_dash="dashdot", line_color="orange",
                      annotation_text=f"Max Pain: ₹{gamma_levels['max_pain']:,.0f}", 
                      annotation_position="top left")
    
    fig.add_hline(y=0, line_dash="solid", line_color="gray", line_width=1)
    
    fig.update_layout(
        title="📊 Gamma Exposure (GEX) Profile",
        xaxis_title="Strike Price (₹)",
        yaxis_title="GEX",
        barmode='relative',
        hovermode='x unified',
        template='plotly_dark',
        height=500,
        showlegend=True
    )
    
    return fig


def plot_oi_analysis(gex_df, spot_price):
    """Enhanced OI analysis with volume"""
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=('Open Interest Distribution', 'Volume Distribution'),
        vertical_spacing=0.15,
        row_heights=[0.6, 0.4]
    )
    
    # OI Chart
    fig.add_trace(go.Bar(
        x=gex_df['strike'],
        y=gex_df['call_oi'],
        name='Call OI',
        marker_color='rgba(239, 68, 68, 0.6)',
        hovertemplate='<b>Strike:</b> %{x}<br><b>Call OI:</b> %{y:,.0f}<extra></extra>'
    ), row=1, col=1)
    
    fig.add_trace(go.Bar(
        x=gex_df['strike'],
        y=gex_df['put_oi'],
        name='Put OI',
        marker_color='rgba(34, 197, 94, 0.6)',
        hovertemplate='<b>Strike:</b> %{x}<br><b>Put OI:</b> %{y:,.0f}<extra></extra>'
    ), row=1, col=1)
    
    # Volume Chart
    fig.add_trace(go.Bar(
        x=gex_df['strike'],
        y=gex_df['call_volume'],
        name='Call Volume',
        marker_color='rgba(239, 68, 68, 0.4)',
        showlegend=False,
        hovertemplate='<b>Strike:</b> %{x}<br><b>Call Vol:</b> %{y:,.0f}<extra></extra>'
    ), row=2, col=1)
    
    fig.add_trace(go.Bar(
        x=gex_df['strike'],
        y=gex_df['put_volume'],
        name='Put Volume',
        marker_color='rgba(34, 197, 94, 0.4)',
        showlegend=False,
        hovertemplate='<b>Strike:</b> %{x}<br><b>Put Vol:</b> %{y:,.0f}<extra></extra>'
    ), row=2, col=1)
    
    # Spot lines
    fig.add_vline(x=spot_price, line_dash="dash", line_color="blue", row=1, col=1)
    fig.add_vline(x=spot_price, line_dash="dash", line_color="blue", row=2, col=1)
    
    fig.update_xaxes(title_text="Strike Price (₹)", row=2, col=1)
    fig.update_yaxes(title_text="Open Interest", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    
    fig.update_layout(
        barmode='group',
        template='plotly_dark',
        height=600,
        hovermode='x unified'
    )
    
    return fig


def plot_iv_smile(gex_df):
    """Volatility smile chart"""
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=gex_df['strike'],
        y=gex_df['call_iv'],
        mode='lines+markers',
        name='Call IV',
        line=dict(color='rgb(239, 68, 68)', width=2),
        marker=dict(size=6),
        hovertemplate='<b>Strike:</b> %{x}<br><b>Call IV:</b> %{y:.2f}%<extra></extra>'
    ))
    
    fig.add_trace(go.Scatter(
        x=gex_df['strike'],
        y=gex_df['put_iv'],
        mode='lines+markers',
        name='Put IV',
        line=dict(color='rgb(34, 197, 94)', width=2),
        marker=dict(size=6),
        hovertemplate='<b>Strike:</b> %{x}<br><b>Put IV:</b> %{y:.2f}%<extra></extra>'
    ))
    
    fig.update_layout(
        title="📈 Volatility Smile",
        xaxis_title="Strike Price (₹)",
        yaxis_title="Implied Volatility (%)",
        template='plotly_dark',
        height=400,
        hovermode='x unified'
    )
    
    return fig


def plot_greeks_heatmap(gex_df, greek_name='gamma'):
    """Greeks heatmap visualization"""
    call_greek = f'call_{greek_name}'
    put_greek = f'put_{greek_name}'
    
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=(f'Call {greek_name.title()}', f'Put {greek_name.title()}'),
        horizontal_spacing=0.15
    )
    
    # Call Greeks
    fig.add_trace(go.Bar(
        x=gex_df['strike'],
        y=gex_df[call_greek],
        name=f'Call {greek_name.title()}',
        marker_color='rgba(239, 68, 68, 0.7)',
        hovertemplate=f'<b>Strike:</b> %{{x}}<br><b>Call {greek_name.title()}:</b> %{{y:.6f}}<extra></extra>'
    ), row=1, col=1)
    
    # Put Greeks
    fig.add_trace(go.Bar(
        x=gex_df['strike'],
        y=gex_df[put_greek],
        name=f'Put {greek_name.title()}',
        marker_color='rgba(34, 197, 94, 0.7)',
        hovertemplate=f'<b>Strike:</b> %{{x}}<br><b>Put {greek_name.title()}:</b> %{{y:.6f}}<extra></extra>'
    ), row=1, col=2)
    
    fig.update_xaxes(title_text="Strike (₹)", row=1, col=1)
    fig.update_xaxes(title_text="Strike (₹)", row=1, col=2)
    fig.update_yaxes(title_text=greek_name.title(), row=1, col=1)
    fig.update_yaxes(title_text=greek_name.title(), row=1, col=2)
    
    fig.update_layout(
        template='plotly_dark',
        height=400,
        showlegend=False
    )
    
    return fig


def plot_pcr_analysis(gex_df):
    """Put-Call Ratio analysis"""
    pcr_by_strike = []
    
    for _, row in gex_df.iterrows():
        pcr = row['put_oi'] / row['call_oi'] if row['call_oi'] > 0 else 0
        pcr_by_strike.append({
            'strike': row['strike'],
            'pcr': pcr
        })
    
    pcr_df = pd.DataFrame(pcr_by_strike)
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=pcr_df['strike'],
        y=pcr_df['pcr'],
        mode='lines+markers',
        name='PCR',
        line=dict(color='purple', width=2),
        marker=dict(size=6),
        fill='tozeroy',
        fillcolor='rgba(128, 0, 128, 0.2)',
        hovertemplate='<b>Strike:</b> %{x}<br><b>PCR:</b> %{y:.2f}<extra></extra>'
    ))
    
    fig.add_hline(y=1, line_dash="dash", line_color="gray", annotation_text="PCR = 1")
    fig.add_hline(y=0.8, line_dash="dot", line_color="green", annotation_text="Bullish (0.8)")
    fig.add_hline(y=1.2, line_dash="dot", line_color="red", annotation_text="Bearish (1.2)")
    
    fig.update_layout(
        title="📊 Put-Call Ratio (PCR) by Strike",
        xaxis_title="Strike Price (₹)",
        yaxis_title="PCR (Put OI / Call OI)",
        template='plotly_dark',
        height=400,
        hovermode='x unified'
    )
    
    return fig


def plot_spot_gex_levels(gex_df, spot_price, gamma_levels, price_range=500):
    """Net GEX vs spot movement"""
    import numpy as np
    
    spot_range = np.arange(spot_price - price_range, spot_price + price_range, 10)
    gex_at_spot = [gex_df['total_gex'].sum()] * len(spot_range)
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=spot_range,
        y=gex_at_spot,
        mode='lines',
        name='Net GEX',
        line=dict(color='blue', width=3),
        fill='tozeroy',
        fillcolor='rgba(59, 130, 246, 0.3)'
    ))
    
    fig.add_vline(x=spot_price, line_dash="dash", line_color="red",
                  annotation_text=f"Current: ₹{spot_price:,.0f}")
    fig.add_hline(y=0, line_dash="solid", line_color="gray")
    
    fig.update_layout(
        title="📉 Net GEX vs Spot Price Movement",
        xaxis_title="Spot Price (₹)",
        yaxis_title="Net GEX",
        template='plotly_dark',
        height=400,
        hovermode='x unified'
    )
    
    return fig


def create_summary_metrics(gex_df, gamma_levels, spot_price):
    """Summary metrics dictionary"""
    total_call_gex = gex_df['call_gex'].sum()
    total_put_gex = gex_df['put_gex'].sum()
    net_gex = gex_df['total_gex'].sum()
    
    return {
        'Total Call GEX': f"{total_call_gex:,.0f}",
        'Total Put GEX': f"{total_put_gex:,.0f}",
        'Net GEX': f"{net_gex:,.0f}",
        'Gamma Flip': gamma_levels.get('gamma_flip', 'N/A'),
        'Support Level': gamma_levels.get('support', 'N/A'),
        'Resistance Level': gamma_levels.get('resistance', 'N/A'),
        'Max Pain': gamma_levels.get('max_pain', 'N/A'),
        'PCR': f"{gamma_levels.get('pcr', 0):.2f}",
        'Market Regime': 'Positive Gamma' if net_gex > 0 else 'Negative Gamma'
    }
