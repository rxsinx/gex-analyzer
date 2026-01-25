"""
GEX Analyzer - Streamlit Application
Gamma Exposure Analysis for NSE Options
"""

import streamlit as st
import pandas as pd
from datetime import datetime

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

# Page configuration
st.set_page_config(
    page_title="GEX Analyzer",
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
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .stAlert {
        margin-top: 1rem;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize session state
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'options_df' not in st.session_state:
    st.session_state.options_df = None
if 'spot_price' not in st.session_state:
    st.session_state.spot_price = None

# Header
st.markdown('<p class="main-header">📊 GEX Analyzer</p>', unsafe_allow_html=True)
st.markdown("### Gamma Exposure Analysis for NSE Options")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Symbol selection
    symbol = st.selectbox(
        "Select Index",
        ["NIFTY", "BANKNIFTY"],
        help="Choose the index for analysis"
    )
    
    # Expiry selection
    expiry_type = st.radio(
        "Expiry Type",
        ["Weekly", "Monthly"],
        help="Select weekly or monthly expiry"
    )
    
    expiry_date = get_next_expiry('weekly' if expiry_type == "Weekly" else 'monthly')
    st.info(f"📅 Next Expiry: {expiry_date}")
    
    # Data source
    data_source = st.radio(
        "Data Source",
        ["Live (NSE)", "Sample Data"],
        help="Choose between live NSE data or sample data for testing"
    )
    
    # Strike range filter
    st.subheader("📍 Strike Range")
    strike_range = st.slider(
        "Range around spot (%)",
        min_value=5,
        max_value=20,
        value=10,
        step=1,
        help="Filter strikes within this percentage of spot price"
    )
    
    # Fetch data button
    if st.button("🔄 Fetch Data", type="primary", use_container_width=True):
        with st.spinner("Fetching option chain data..."):
            try:
                if data_source == "Live (NSE)":
                    df, spot = fetch_option_chain(symbol, expiry_date)
                else:
                    # Generate sample data
                    base_spot = 21500 if symbol == "NIFTY" else 45000
                    df, spot = generate_sample_data(symbol, base_spot)
                
                if df is not None and not df.empty:
                    st.session_state.options_df = df
                    st.session_state.spot_price = spot
                    st.session_state.data_loaded = True
                    st.success("✅ Data loaded successfully!")
                else:
                    st.error("❌ Failed to fetch data. Using sample data.")
                    df, spot = generate_sample_data(symbol, 21500)
                    st.session_state.options_df = df
                    st.session_state.spot_price = spot
                    st.session_state.data_loaded = True
                    
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.info("Loading sample data instead...")
                df, spot = generate_sample_data(symbol, 21500)
                st.session_state.options_df = df
                st.session_state.spot_price = spot
                st.session_state.data_loaded = True
    
    # Risk-free rate
    st.subheader("🔧 Parameters")
    risk_free_rate = st.number_input(
        "Risk-Free Rate (%)",
        min_value=0.0,
        max_value=15.0,
        value=7.0,
        step=0.1
    ) / 100

# Main content
if st.session_state.data_loaded:
    df = st.session_state.options_df
    spot_price = st.session_state.spot_price
    
    # Filter strikes
    df_filtered = filter_strikes(df, spot_price, strike_range)
    
    # Calculate GEX
    with st.spinner("Calculating GEX..."):
        gex_df = calculate_gex(df_filtered, spot_price, expiry_date, risk_free_rate)
        gamma_levels = find_gamma_levels(gex_df, spot_price)
    
    # Display key metrics
    st.markdown("---")
    st.subheader("📈 Key Metrics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Spot Price",
            f"₹{spot_price:,.2f}",
            delta=None
        )
    
    with col2:
        st.metric(
            "Gamma Flip",
            f"₹{gamma_levels['gamma_flip']:,.0f}",
            delta=f"{gamma_levels['gamma_flip'] - spot_price:+.0f}"
        )
    
    with col3:
        regime = "Positive Gamma" if gamma_levels['total_gex'] > 0 else "Negative Gamma"
        regime_color = "🟢" if gamma_levels['total_gex'] > 0 else "🔴"
        st.metric(
            "Market Regime",
            f"{regime_color} {regime}",
            delta=None
        )
    
    with col4:
        st.metric(
            "Net GEX",
            format_number(gamma_levels['total_gex']),
            delta=None
        )
    
    # Tabs for different views
    st.markdown("---")
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 GEX Profile",
        "📉 OI Analysis",
        "📋 Data Table",
        "ℹ️ Information"
    ])
    
    with tab1:
        st.subheader("Gamma Exposure Profile")
        
        # GEX profile chart
        fig_gex = plot_gex_profile(gex_df, spot_price, gamma_levels)
        st.plotly_chart(fig_gex, use_container_width=True)
        
        # Additional metrics
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("##### 🎯 Key Levels")
            st.write(f"**Support Level:** {gamma_levels.get('support', 'N/A')}")
            st.write(f"**Resistance Level:** {gamma_levels.get('resistance', 'N/A')}")
            st.write(f"**ATM Strike:** {get_atm_strike(spot_price)}")
        
        with col2:
            st.markdown("##### 📊 GEX Summary")
            st.write(f"**Total Call GEX:** {format_number(gex_df['call_gex'].sum())}")
            st.write(f"**Total Put GEX:** {format_number(gex_df['put_gex'].sum())}")
            st.write(f"**Net GEX:** {format_number(gex_df['total_gex'].sum())}")
        
        # Spot vs GEX
        st.markdown("---")
        st.subheader("Net GEX vs Spot Movement")
        fig_spot_gex = plot_spot_gex_levels(gex_df, spot_price, gamma_levels, price_range=500)
        st.plotly_chart(fig_spot_gex, use_container_width=True)
    
    with tab2:
        st.subheader("Open Interest Analysis")
        
        # OI Distribution
        fig_oi = plot_oi_analysis(df_filtered, spot_price)
        st.plotly_chart(fig_oi, use_container_width=True)
        
        # PCR Analysis
        st.markdown("---")
        st.subheader("Put-Call Ratio (PCR) Analysis")
        fig_pcr = plot_pcr_analysis(df_filtered)
        st.plotly_chart(fig_pcr, use_container_width=True)
        
        # Overall PCR
        total_call_oi = df_filtered[df_filtered['type'] == 'CE']['oi'].sum()
        total_put_oi = df_filtered[df_filtered['type'] == 'PE']['oi'].sum()
        overall_pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Call OI", f"{total_call_oi:,.0f}")
        col2.metric("Total Put OI", f"{total_put_oi:,.0f}")
        col3.metric("Overall PCR", f"{overall_pcr:.2f}")
    
    with tab3:
        st.subheader("GEX Data Table")
        
        # Format the dataframe for display
        display_df = gex_df.copy()
        display_df['call_gex'] = display_df['call_gex'].apply(lambda x: f"{x:,.0f}")
        display_df['put_gex'] = display_df['put_gex'].apply(lambda x: f"{x:,.0f}")
        display_df['total_gex'] = display_df['total_gex'].apply(lambda x: f"{x:,.0f}")
        
        st.dataframe(
            display_df,
            use_container_width=True,
            height=400
        )
        
        # Download button
        csv = gex_df.to_csv(index=False)
        st.download_button(
            label="📥 Download GEX Data (CSV)",
            data=csv,
            file_name=f"gex_data_{symbol}_{expiry_date}.csv",
            mime="text/csv"
        )
    
    with tab4:
        st.subheader("ℹ️ Understanding GEX")
        
        st.markdown("""
        **What is Gamma Exposure (GEX)?**
        
        Gamma Exposure represents the risk that market makers face due to their options positions. 
        It indicates how much dealers need to hedge their positions as the underlying price moves.
        
        **Key Concepts:**
        
        - **Positive GEX (Put-heavy)**: Market makers are long gamma. They sell when price rises and buy when it falls, 
          creating a stabilizing effect. Markets tend to be less volatile.
        
        - **Negative GEX (Call-heavy)**: Market makers are short gamma. They buy when price rises and sell when it falls,
          creating a destabilizing effect. Markets tend to be more volatile.
        
        - **Gamma Flip Point**: The price level where GEX changes from positive to negative (or vice versa).
          This level often acts as a pivot point for market behavior.
        
        **How to Use This Tool:**
        
        1. **Check Market Regime**: Positive or Negative Gamma environment
        2. **Identify Key Levels**: Support, Resistance, and Gamma Flip points
        3. **Analyze GEX Distribution**: Where is gamma concentrated?
        4. **Monitor Changes**: Track how GEX evolves throughout the day
        
        **Interpretation:**
        
        - Large positive GEX at a strike = Strong support level
        - Large negative GEX at a strike = Potential resistance level
        - Price tends to gravitate toward areas of high gamma
        - Crossing the gamma flip point can lead to regime change in volatility
        """)
        
        st.info("💡 **Tip**: Combine GEX analysis with price action, volume, and other indicators for best results.")

else:
    # Welcome screen
    st.info("👈 Configure settings in the sidebar and click 'Fetch Data' to begin analysis")
    
    st.markdown("""
    ### Welcome to GEX Analyzer! 📊
    
    This tool helps you analyze **Gamma Exposure (GEX)** in NSE options to:
    
    - 🎯 Identify key support and resistance levels
    - 📈 Understand market maker positioning
    - 🔄 Detect gamma flip points
    - 📊 Analyze option open interest distribution
    - 💹 Make informed trading decisions
    
    **Get Started:**
    1. Select an index (NIFTY or BANKNIFTY)
    2. Choose expiry type (Weekly or Monthly)
    3. Select data source
    4. Click "Fetch Data"
    
    ---
    
    **Features:**
    - Real-time GEX calculations
    - Interactive visualizations
    - Put-Call Ratio analysis
    - Downloadable data
    - Market regime identification
    """)

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666; padding: 1rem;'>
        <p>GEX Analyzer v1.0 | Built with Streamlit | Data from NSE</p>
        <p style='font-size: 0.8rem;'>⚠️ For educational purposes only. Not financial advice.</p>
    </div>
    """,
    unsafe_allow_html=True
)
