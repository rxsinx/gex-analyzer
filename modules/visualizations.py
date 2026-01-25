"""
Visualization module for GEX analysis
"""

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd


def plot_gex_profile(gex_df, spot_price, gamma_levels):
    """
    Plot GEX profile with call and put GEX
    
    Args:
        gex_df (pd.DataFrame): GEX data
        spot_price (float): Current spot price
        gamma_levels (dict): Key gamma levels
    
    Returns:
        plotly.graph_objects.Figure: GEX profile chart
    """
    fig = go.Figure()
    
    # Add Call GEX (negative)
    fig.add_trace(go.Bar(
        x=gex_df['strike'],
        y=gex_df['call_gex'],
        name='Call GEX',
        marker_color='rgba(239, 68, 68, 0.7)',
        hovertemplate='Strike: %{x}<br>Call GEX: %{y:,.0f}<extra></extra>'
    ))
    
    # Add Put GEX (positive)
    fig.add_trace(go.Bar(
        x=gex_df['strike'],
        y=gex_df['put_gex'],
        name='Put GEX',
        marker_color='rgba(34, 197, 94, 0.7)',
        hovertemplate='Strike: %{x}<br>Put GEX: %{y:,.0f}<extra></extra>'
    ))
    
    # Add spot price line
    fig.add_vline(
        x=spot_price,
        line_dash="dash",
        line_color="blue",
        annotation_text=f"Spot: {spot_price}",
        annotation_position="top"
    )
    
    # Add gamma flip line
    if gamma_levels.get('gamma_flip'):
        fig.add_vline(
            x=gamma_levels['gamma_flip'],
            line_dash="dot",
            line_color="purple",
            annotation_text=f"Gamma Flip: {gamma_levels['gamma_flip']}",
            annotation_position="bottom"
        )
    
    # Add zero line
    fig.add_hline(y=0, line_dash="solid", line_color="gray", line_width=1)
    
    fig.update_layout(
        title="Gamma Exposure (GEX) Profile",
        xaxis_title="Strike Price",
        yaxis_title="GEX",
        barmode='relative',
        hovermode='x unified',
        template='plotly_white',
        height=500,
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01
        )
    )
    
    return fig


def plot_spot_gex_levels(gex_df, spot_price, gamma_levels, price_range=500):
    """
    Plot how GEX changes as spot moves
    
    Args:
        gex_df (pd.DataFrame): GEX data
        spot_price (float): Current spot price
        gamma_levels (dict): Key gamma levels
        price_range (int): Range around spot to simulate
    
    Returns:
        plotly.graph_objects.Figure: Spot vs GEX chart
    """
    import numpy as np
    
    # Simulate spot prices
    spot_range = np.arange(spot_price - price_range, spot_price + price_range, 10)
    gex_at_spot = []
    
    for sim_spot in spot_range:
        # Calculate net GEX at this spot level
        net_gex = gex_df['total_gex'].sum()
        gex_at_spot.append(net_gex)
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=spot_range,
        y=gex_at_spot,
        mode='lines',
        name='Net GEX',
        line=dict(color='blue', width=2),
        fill='tozeroy',
        fillcolor='rgba(59, 130, 246, 0.2)'
    ))
    
    # Add current spot
    fig.add_vline(
        x=spot_price,
        line_dash="dash",
        line_color="red",
        annotation_text=f"Current: {spot_price}",
        annotation_position="top"
    )
    
    # Add zero line
    fig.add_hline(y=0, line_dash="solid", line_color="gray")
    
    fig.update_layout(
        title="Net GEX vs Spot Price",
        xaxis_title="Spot Price",
        yaxis_title="Net GEX",
        template='plotly_white',
        height=400,
        hovermode='x unified'
    )
    
    return fig


def plot_oi_analysis(df, spot_price):
    """
    Plot Open Interest analysis
    
    Args:
        df (pd.DataFrame): Options data
        spot_price (float): Current spot price
    
    Returns:
        plotly.graph_objects.Figure: OI analysis chart
    """
    # Aggregate OI by strike
    oi_data = df.groupby(['strike', 'type'])['oi'].sum().reset_index()
    
    call_oi = oi_data[oi_data['type'] == 'CE'].set_index('strike')['oi']
    put_oi = oi_data[oi_data['type'] == 'PE'].set_index('strike')['oi']
    
    strikes = sorted(df['strike'].unique())
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=strikes,
        y=[call_oi.get(s, 0) for s in strikes],
        name='Call OI',
        marker_color='rgba(239, 68, 68, 0.6)'
    ))
    
    fig.add_trace(go.Bar(
        x=strikes,
        y=[put_oi.get(s, 0) for s in strikes],
        name='Put OI',
        marker_color='rgba(34, 197, 94, 0.6)'
    ))
    
    # Add spot line
    fig.add_vline(
        x=spot_price,
        line_dash="dash",
        line_color="blue",
        annotation_text=f"Spot: {spot_price}"
    )
    
    fig.update_layout(
        title="Open Interest Distribution",
        xaxis_title="Strike Price",
        yaxis_title="Open Interest",
        barmode='group',
        template='plotly_white',
        height=400,
        hovermode='x unified'
    )
    
    return fig


def plot_pcr_analysis(df):
    """
    Plot Put-Call Ratio analysis
    
    Args:
        df (pd.DataFrame): Options data
    
    Returns:
        plotly.graph_objects.Figure: PCR chart
    """
    pcr_data = df.groupby(['strike', 'type'])['oi'].sum().reset_index()
    
    pcr_by_strike = []
    
    for strike in sorted(df['strike'].unique()):
        call_oi = pcr_data[(pcr_data['strike'] == strike) & (pcr_data['type'] == 'CE')]['oi'].sum()
        put_oi = pcr_data[(pcr_data['strike'] == strike) & (pcr_data['type'] == 'PE')]['oi'].sum()
        
        pcr = put_oi / call_oi if call_oi > 0 else 0
        
        pcr_by_strike.append({
            'strike': strike,
            'pcr': pcr,
            'call_oi': call_oi,
            'put_oi': put_oi
        })
    
    pcr_df = pd.DataFrame(pcr_by_strike)
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=pcr_df['strike'],
        y=pcr_df['pcr'],
        mode='lines+markers',
        name='PCR',
        line=dict(color='purple', width=2),
        marker=dict(size=6)
    ))
    
    # Add PCR = 1 line
    fig.add_hline(
        y=1,
        line_dash="dash",
        line_color="gray",
        annotation_text="PCR = 1"
    )
    
    fig.update_layout(
        title="Put-Call Ratio by Strike",
        xaxis_title="Strike Price",
        yaxis_title="PCR (Put OI / Call OI)",
        template='plotly_white',
        height=400,
        hovermode='x unified'
    )
    
    return fig


def create_summary_metrics(gex_df, gamma_levels, spot_price):
    """
    Create summary metrics display
    
    Args:
        gex_df (pd.DataFrame): GEX data
        gamma_levels (dict): Key gamma levels
        spot_price (float): Current spot price
    
    Returns:
        dict: Summary metrics
    """
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
        'Market Regime': 'Positive Gamma' if net_gex > 0 else 'Negative Gamma'
    }
