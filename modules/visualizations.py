# modules/visualizations.py

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np

class GEXVisualizations:
    """Create interactive visualizations for GEX analysis"""
    
    @staticmethod
    def create_gex_dashboard(gex_data: dict, symbol: str, spot_price: float) -> go.Figure:
        """
        Create comprehensive GEX dashboard with multiple plots
        """
        results_df = gex_data['results_df']
        
        # Create subplots
        fig = make_subplots(
            rows=3, cols=2,
            subplot_titles=(
                f'{symbol} GEX by Strike',
                f'{symbol} Implied Volatility Smile',
                f'{symbol} Open Interest Distribution',
                f'{symbol} Call vs Put GEX',
                f'{symbol} PCR by Strike',
                f'{symbol} Gamma Profile'
            ),
            vertical_spacing=0.12,
            horizontal_spacing=0.15
        )
        
        # Prepare data
        calls_df = results_df[results_df['option_type'] == 'CE']
        puts_df = results_df[results_df['option_type'] == 'PE']
        
        # 1. GEX by Strike
        fig.add_trace(
            go.Bar(
                x=results_df['strike'],
                y=results_df['dealer_gex_crores'],
                name='Dealer GEX',
                marker_color='rgba(55, 128, 191, 0.7)',
                hovertemplate='Strike: %{x}<br>GEX: ₹%{y:.2f}Cr<extra></extra>'
            ),
            row=1, col=1
        )
        
        # Add spot price line
        fig.add_vline(x=spot_price, line_dash="dash", line_color="red", 
                     annotation_text="Spot", annotation_position="top right",
                     row=1, col=1)
        
        # 2. IV Smile
        if not calls_df.empty:
            fig.add_trace(
                go.Scatter(
                    x=calls_df['strike'],
                    y=calls_df['iv'] * 100,
                    mode='lines+markers',
                    name='Call IV',
                    line=dict(color='green'),
                    hovertemplate='Strike: %{x}<br>IV: %{y:.2f}%<extra></extra>'
                ),
                row=1, col=2
            )
        
        if not puts_df.empty:
            fig.add_trace(
                go.Scatter(
                    x=puts_df['strike'],
                    y=puts_df['iv'] * 100,
                    mode='lines+markers',
                    name='Put IV',
                    line=dict(color='red'),
                    hovertemplate='Strike: %{x}<br>IV: %{y:.2f}%<extra></extra>'
                ),
                row=1, col=2
            )
        
        # 3. Open Interest Distribution
        fig.add_trace(
            go.Bar(
                x=calls_df['strike'],
                y=calls_df['open_interest'],
                name='Call OI',
                marker_color='green',
                hovertemplate='Strike: %{x}<br>OI: %{y:,.0f}<extra></extra>'
            ),
            row=2, col=1
        )
        
        fig.add_trace(
            go.Bar(
                x=puts_df['strike'],
                y=puts_df['open_interest'],
                name='Put OI',
                marker_color='red',
                hovertemplate='Strike: %{x}<br>OI: %{y:,.0f}<extra></extra>'
            ),
            row=2, col=1
        )
        
        # 4. Call vs Put GEX
        fig.add_trace(
            go.Bar(
                x=calls_df['strike'],
                y=calls_df['dealer_gex_crores'],
                name='Call GEX',
                marker_color='rgba(0, 128, 0, 0.6)',
                hovertemplate='Strike: %{x}<br>Call GEX: ₹%{y:.2f}Cr<extra></extra>'
            ),
            row=2, col=2
        )
        
        fig.add_trace(
            go.Bar(
                x=puts_df['strike'],
                y=puts_df['dealer_gex_crores'],
                name='Put GEX',
                marker_color='rgba(255, 0, 0, 0.6)',
                hovertemplate='Strike: %{x}<br>Put GEX: ₹%{y:.2f}Cr<extra></extra>'
            ),
            row=2, col=2
        )
        
        # 5. PCR by Strike
        # Merge calls and puts by strike
        merged_df = pd.merge(
            calls_df[['strike', 'open_interest']].rename(columns={'open_interest': 'call_oi'}),
            puts_df[['strike', 'open_interest']].rename(columns={'open_interest': 'put_oi'}),
            on='strike',
            how='outer'
        ).fillna(0)
        
        merged_df['pcr'] = merged_df['put_oi'] / merged_df['call_oi'].replace(0, np.nan)
        
        fig.add_trace(
            go.Scatter(
                x=merged_df['strike'],
                y=merged_df['pcr'],
                mode='lines+markers',
                name='PCR',
                line=dict(color='purple'),
                hovertemplate='Strike: %{x}<br>PCR: %{y:.2f}<extra></extra>'
            ),
            row=3, col=1
        )
        
        # Add PCR=1 reference line
        fig.add_hline(y=1, line_dash="dot", line_color="gray", 
                     annotation_text="PCR=1", row=3, col=1)
        
        # 6. Gamma Profile
        fig.add_trace(
            go.Scatter(
                x=results_df['strike'],
                y=results_df['gamma'] * 10000,  # Scale for better visualization
                mode='lines',
                name='Gamma',
                line=dict(color='orange', width=2),
                hovertemplate='Strike: %{x}<br>Gamma: %{y:.4f}<extra></extra>'
            ),
            row=3, col=2
        )
        
        # Update layout
        fig.update_layout(
            height=1000,
            showlegend=True,
            template='plotly_white',
            title=f"{symbol} Gamma Exposure Analysis",
            title_x=0.5
        )
        
        # Update axes labels
        fig.update_xaxes(title_text="Strike Price", row=3, col=1)
        fig.update_xaxes(title_text="Strike Price", row=3, col=2)
        fig.update_yaxes(title_text="GEX (₹ Crores)", row=1, col=1)
        fig.update_yaxes(title_text="Implied Volatility %", row=1, col=2)
        fig.update_yaxes(title_text="Open Interest", row=2, col=1)
        fig.update_yaxes(title_text="GEX (₹ Crores)", row=2, col=2)
        fig.update_yaxes(title_text="Put-Call Ratio", row=3, col=1)
        fig.update_yaxes(title_text="Gamma (scaled)", row=3, col=2)
        
        return fig
    
    @staticmethod
    def create_gex_summary_metrics(gex_data: dict, symbol: str, spot_price: float) -> go.Figure:
        """
        Create summary metrics visualization
        """
        metrics = [
            ('Total GEX', f'₹{gex_data["total_gex_crores"]:.2f} Cr', '#4CAF50'),
            ('Net Dealer GEX', f'₹{gex_data["net_gex_crores"]:.2f} Cr', 
             '#F44336' if gex_data["net_gex_crores"] < 0 else '#4CAF50'),
            ('Gamma Flip', f'{gex_data["gamma_flip"]:,.0f}', '#2196F3'),
            ('PCR (OI)', f'{gex_data["pcr_oi"]:.2f}', 
             '#FF9800' if gex_data["pcr_oi"] > 1.5 else '#4CAF50'),
            ('Call OI', f'{gex_data["call_oi"]:,.0f}', '#4CAF50'),
            ('Put OI', f'{gex_data["put_oi"]:,.0f}', '#F44336'),
        ]
        
        fig = go.Figure()
        
        for i, (name, value, color) in enumerate(metrics):
            fig.add_trace(
                go.Indicator(
                    mode="number+delta",
                    value=float(value.split()[0].replace('₹', '').replace(',', '') 
                               if 'Cr' in value else float(value.replace(',', ''))),
                    title={"text": f"<b>{name}</b><br>{value}"},
                    number={"font": {"size": 24}},
                    delta={"reference": 0},
                    domain={"row": i // 3, "column": i % 3}
                )
            )
        
        fig.update_layout(
            grid={"rows": 2, "columns": 3, "pattern": "independent"},
            height=400,
            template="plotly_white",
            title=f"{symbol} Key Metrics",
            title_x=0.5
        )
        
        return fig
