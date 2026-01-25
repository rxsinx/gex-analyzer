# app.py

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import custom modules
from modules.data_fetcher import fetch_option_chain, generate_sample_data
from modules.gex_calculator import calculate_gex, calculate_dex, find_gamma_levels
from modules.visualizations import (
    plot_gex_profile, 
    plot_spot_gex_levels, 
    plot_oi_analysis,
    plot_pcr_analysis,
    create_summary_metrics
)
from modules.utils import (
    get_next_expiry, 
    get_atm_strike, 
    format_number,
    filter_strikes,
    get_available_expiries
)

# Page Configuration
st.set_page_config(
    page_title="NIFTY & BANKNIFTY GEX Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E3A8A;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #374151;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .warning-card {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .success-card {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #F3F4F6;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1E3A8A;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Title
st.markdown('<p class="main-header">📈 NIFTY & BANKNIFTY GEX ANALYZER</p>', unsafe_allow_html=True)
st.markdown("### Real-time Gamma Exposure Analysis for Indian Indices")

# Sidebar Configuration
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/india.png", width=80)
    st.markdown("## 📊 Configuration")
    
    selected_index = st.radio(
        "Select Index:",
        ["NIFTY", "BANKNIFTY"],
        index=0
    )
    
    analysis_type = st.selectbox(
        "Analysis Type:",
        ["Weekly Expiry", "Monthly Expiry", "All Expiries"],
        index=0
    )
    
    st.markdown("---")
    st.markdown("### 📅 Date Range")
    
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start", datetime.now())
    with col2:
        end_date = st.date_input("End", datetime.now() + timedelta(days=30))
    
    st.markdown("---")
    st.markdown("### ⚙️ Settings")
    
    refresh_rate = st.slider("Refresh Rate (seconds)", 10, 300, 60)
    auto_refresh = st.checkbox("Auto Refresh", True)
    
    st.markdown("---")
    st.markdown("#### 🔗 Data Sources")
    st.markdown("- NSE Option Chain")
    st.markdown("- Yahoo Finance")
    st.markdown("- India VIX")
    
    st.markdown("---")
    st.markdown("#### 📈 Market Status")
    
    market_status = MarketData.get_market_status()
    st.selectbox(
        "Market Status:",
        [market_status],
        index=0
    )
    
    if market_status == "Open":
        st.success("✅ Market Open")
    elif market_status == "Closed":
        st.error("❌ Market Closed")
    
    st.markdown(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Initialize session state
if 'nifty_data' not in st.session_state:
    st.session_state.nifty_data = None
if 'banknifty_data' not in st.session_state:
    st.session_state.banknifty_data = None
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()

# Refresh button
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if st.button("🔄 Refresh Data", type="primary", use_container_width=True):
        st.session_state.last_refresh = datetime.now()
        # In a real app, we would fetch fresh data here
        st.rerun()

# Main tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Dashboard", 
    "📈 GEX Analysis", 
    "📉 Risk Metrics", 
    "⚙️ Configuration"
])

with tab1:
    st.markdown('<p class="sub-header">📈 Live Market Overview</p>', unsafe_allow_html=True)
    
    # Create columns for metrics
    col1, col2, col3, col4 = st.columns(4)
    
    # Get market data
    nifty_spot = MarketData.get_spot_price("NIFTY")
    banknifty_spot = MarketData.get_spot_price("BANKNIFTY")
    india_vix = MarketData.get_vix()
    
    with col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("NIFTY Spot", f"{nifty_spot:,.2f}", "▲ 125.50 (0.57%)")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("BANKNIFTY Spot", f"{banknifty_spot:,.2f}", "▲ 325.75 (0.68%)")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col3:
        st.markdown('<div class="warning-card">', unsafe_allow_html=True)
        st.metric("India VIX", f"{india_vix:.2f}", "▲ 0.75 (5.56%)")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col4:
        market_status = MarketData.get_market_status()
        if market_status == "Open":
            st.markdown('<div class="success-card">', unsafe_allow_html=True)
            st.metric("Market Status", "OPEN", "Live")
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="warning-card">', unsafe_allow_html=True)
            st.metric("Market Status", "CLOSED", "Offline")
            st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Index-specific analysis
    if selected_index == "NIFTY":
        st.markdown('<p class="sub-header">📊 NIFTY GEX Analysis</p>', unsafe_allow_html=True)
        
        # For demo, create sample data
        # In production, fetch real data using NSEDataFetcher
        sample_data = pd.DataFrame({
            'strike': [21700, 21800, 21900, 22000, 22100, 22200, 22300, 22400],
            'option_type': ['CE'] * 8,
            'open_interest': [50000, 75000, 100000, 125000, 150000, 125000, 100000, 75000],
            'iv': [0.14, 0.135, 0.13, 0.125, 0.12, 0.125, 0.13, 0.135],
            'spot_price': [nifty_spot] * 8,
            'days_to_expiry': [3] * 8
        })
        
        # Add some put data for demonstration
        put_data = pd.DataFrame({
            'strike': [21700, 21800, 21900, 22000, 22100, 22200, 22300, 22400],
            'option_type': ['PE'] * 8,
            'open_interest': [75000, 100000, 125000, 150000, 125000, 100000, 75000, 50000],
            'iv': [0.16, 0.155, 0.15, 0.145, 0.15, 0.155, 0.16, 0.165],
            'spot_price': [nifty_spot] * 8,
            'days_to_expiry': [3] * 8
        })
        
        sample_data = pd.concat([sample_data, put_data], ignore_index=True)
        
        # Calculate GEX
        gex_results = GEXCalculator.calculate_total_gex(sample_data, "NIFTY")
        
        # Display metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total GEX", f"₹{gex_results['total_gex_crores']:.2f} Cr")
        
        with col2:
            dealer_position = gex_results['dealer_position']
            color = "red" if dealer_position == "SHORT GAMMA" else "green"
            st.metric("Dealer Position", dealer_position, delta_color="off")
        
        with col3:
            st.metric("Gamma Flip", f"{gex_results['gamma_flip']:,.0f}")
        
        with col4:
            pcr_oi = gex_results['pcr_oi']
            pcr_color = "normal" if 0.7 <= pcr_oi <= 1.3 else "inverse"
            st.metric("PCR (OI)", f"{pcr_oi:.2f}", delta_color=pcr_color)
        
        # Create visualizations
        fig1 = GEXVisualizations.create_gex_summary_metrics(gex_results, "NIFTY", nifty_spot)
        st.plotly_chart(fig1, use_container_width=True)
        
        fig_gex = plot_gex_profile(gex_df, spot_price, gamma_levels)
        st.plotly_chart(fig_gex, use_container_width=True)
        
    else:  # BANKNIFTY
        st.markdown('<p class="sub-header">📊 BANKNIFTY GEX Analysis</p>', unsafe_allow_html=True)
        
        # For demo, create sample data
        sample_data = pd.DataFrame({
            'strike': [47000, 47500, 48000, 48500, 49000, 49500, 50000],
            'option_type': ['CE'] * 7,
            'open_interest': [40000, 60000, 80000, 100000, 80000, 60000, 40000],
            'iv': [0.16, 0.155, 0.15, 0.145, 0.15, 0.155, 0.16],
            'spot_price': [banknifty_spot] * 7,
            'days_to_expiry': [2] * 7
        })
        
        # Add some put data for demonstration
        put_data = pd.DataFrame({
            'strike': [47000, 47500, 48000, 48500, 49000, 49500, 50000],
            'option_type': ['PE'] * 7,
            'open_interest': [60000, 80000, 100000, 120000, 100000, 80000, 60000],
            'iv': [0.18, 0.175, 0.17, 0.165, 0.17, 0.175, 0.18],
            'spot_price': [banknifty_spot] * 7,
            'days_to_expiry': [2] * 7
        })
        
        sample_data = pd.concat([sample_data, put_data], ignore_index=True)
        
        # Calculate GEX
        gex_results = GEXCalculator.calculate_total_gex(sample_data, "BANKNIFTY")
        
        # Display metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total GEX", f"₹{gex_results['total_gex_crores']:.2f} Cr")
        
        with col2:
            dealer_position = gex_results['dealer_position']
            st.metric("Dealer Position", dealer_position, delta_color="off")
        
        with col3:
            st.metric("Gamma Flip", f"{gex_results['gamma_flip']:,.0f}")
        
        with col4:
            pcr_oi = gex_results['pcr_oi']
            pcr_color = "normal" if 0.7 <= pcr_oi <= 1.3 else "inverse"
            st.metric("PCR (OI)", f"{pcr_oi:.2f}", delta_color=pcr_color)
        
        # Create visualizations
        fig1 = GEXVisualizations.create_gex_summary_metrics(gex_results, "BANKNIFTY", banknifty_spot)
        st.plotly_chart(fig1, use_container_width=True)
        
        fig2 = GEXVisualizations.create_gex_dashboard(gex_results, "BANKNIFTY", banknifty_spot)
        st.plotly_chart(fig2, use_container_width=True)

with tab2:
    st.markdown('<p class="sub-header">📈 Detailed GEX Analysis</p>', unsafe_allow_html=True)
    
    # Create two columns for detailed analysis
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Strike-wise GEX Analysis")
        
        # Display the results dataframe if available
        if selected_index == "NIFTY":
            # Use the same sample data as above
            gex_results = GEXCalculator.calculate_total_gex(sample_data, selected_index)
            results_df = gex_results['results_df']
        else:
            gex_results = GEXCalculator.calculate_total_gex(sample_data, selected_index)
            results_df = gex_results['results_df']
        
        # Show a subset of columns
        display_df = results_df[['strike', 'option_type', 'open_interest', 'dealer_gex_crores', 'gamma']].copy()
        display_df.columns = ['Strike', 'Type', 'OI', 'Dealer GEX (Cr)', 'Gamma']
        
        st.dataframe(
            display_df.style.format({
                'Dealer GEX (Cr)': '{:.2f}',
                'Gamma': '{:.6f}'
            }).background_gradient(subset=['Dealer GEX (Cr)'], cmap='RdYlGn'),
            use_container_width=True,
            height=400
        )
    
    with col2:
        st.markdown("#### GEX Concentration")
        
        # Create pie chart for top strikes
        if not results_df.empty:
            top_gex = results_df.nlargest(10, 'dealer_gex_crores')
            labels = [f"{row['strike']} {row['option_type']}" for _, row in top_gex.iterrows()]
            values = top_gex['dealer_gex_crores'].abs()
            
            fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.3)])
            fig.update_layout(
                title="Top 10 GEX Contributions",
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Advanced metrics
    st.markdown("#### Advanced GEX Metrics")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Calculate total vanna and charm (simplified)
        if not results_df.empty:
            total_vanna = (results_df['vega'] * results_df['open_interest'] * 
                          GEXCalculator.MARKET_PARAMS[selected_index]['lot_size']).sum() / 10000000
            total_charm = (results_df['charm'] * results_df['open_interest'] * 
                          GEXCalculator.MARKET_PARAMS[selected_index]['lot_size']).sum() / 10000000
            
            st.metric("Vanna Exposure", f"₹{total_vanna:.2f} Cr")
            st.metric("Charm Exposure", f"₹{total_charm:.2f} Cr")
    
    with col2:
        # Calculate theta decay
        if not results_df.empty:
            total_theta = (results_df['theta'] * results_df['open_interest'] * 
                          GEXCalculator.MARKET_PARAMS[selected_index]['lot_size']).sum() / 10000000
            st.metric("Theta Decay/Day", f"₹{total_theta:.2f} Cr")
            
            # Delta hedge notional
            total_delta = (results_df['delta'] * results_df['open_interest'] * 
                          GEXCalculator.MARKET_PARAMS[selected_index]['lot_size'] * 
                          results_df['spot_price'].mean()).sum() / 10000000
            st.metric("Delta Hedge", f"₹{total_delta:.2f} Cr")
    
    with col3:
        # Max pain calculation (simplified)
        strikes = results_df['strike'].unique()
        pain_values = []
        
        for strike in strikes:
            pain = 0
            for _, row in results_df.iterrows():
                if row['option_type'] == 'CE' and row['strike'] < strike:
                    pain += row['open_interest'] * (strike - row['strike'])
                elif row['option_type'] == 'PE' and row['strike'] > strike:
                    pain += row['open_interest'] * (row['strike'] - strike)
            pain_values.append(pain)
        
        if pain_values:
            max_pain_strike = strikes[np.argmin(pain_values)]
            st.metric("Max Pain", f"{max_pain_strike:,.0f}")
        
        # Expected move (simplified)
        expected_move = india_vix * np.sqrt(3/365) * nifty_spot if selected_index == "NIFTY" else india_vix * np.sqrt(3/365) * banknifty_spot
        st.metric("Expected Move (3D)", f"±{expected_move:.0f}")

# ... (rest of the app.py remains the same for tabs 3 and 4, but adjust as needed)

# Note: The rest of the app.py (for tabs 3 and 4) can be similar to what we had earlier, 
# but we are not including it here to keep the response concise.
