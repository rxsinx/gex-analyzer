"""
GEX Analyzer - Streamlit Application
Gamma Exposure Analysis for NSE Options
"""

import streamlit as st
import pandas as pd
from datetime import datetime

# Import custom modules
from modules.data_fetcher import (
    fetch_option_chain, 
    generate_sample_data, 
    get_live_spot_price,
    get_index_quote,
    get_market_status
)

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
    page_title="GEX Analyzer - Live NSE Data",
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
    .live-indicator {
        display: inline-block;
        width: 10px;
        height: 10px;
        background-color: #22c55e;
        border-radius: 50%;
        margin-right: 5px;
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
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
if 'last_update' not in st.session_state:
    st.session_state.last_update = None

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
        with st.spinner("Fetching data from NSE..."):
            try:
                if data_source == "Live (NSE)":
                    # Try to fetch live NSE option chain
                    st.info("🌐 Connecting to NSE...")
                    df, spot = fetch_option_chain(symbol, expiry_date)
                    
                    if df is not None and not df.empty and spot is not None:
                        st.session_state.options_df = df
                        st.session_state.spot_price = spot
                        st.session_state.data_loaded = True
                        st.session_state.last_update = datetime.now()
                        st.success(f"✅ Live data loaded! Spot: ₹{spot:,.2f}")
                    else:
                        # Fallback: Get live spot and use sample data
                        st.warning("⚠️ NSE option chain unavailable. Fetching live spot price...")
                        live_spot = get_live_spot_price(symbol)
                        
                        if live_spot:
                            df, spot = generate_sample_data(symbol, live_spot)
                            st.session_state.options_df = df
                            st.session_state.spot_price = spot
                            st.session_state.data_loaded = True
                            st.session_state.last_update = datetime.now()
                            st.info(f"📊 Using sample data with live spot: ₹{spot:,.2f}")
                        else:
                            # Last resort fallback
                            default_spot = 23500 if symbol == "NIFTY" else 48000
                            df, spot = generate_sample_data(symbol, default_spot)
                            st.session_state.options_df = df
                            st.session_state.spot_price = spot
                            st.session_state.data_loaded = True
                            st.session_state.last_update = datetime.now()
                            st.warning(f"⚠️ Using fallback spot: ₹{spot:,.2f}")
                else:
                    # Sample data mode - always fetch live spot
                    st.info("📡 Fetching live spot price from NSE...")
                    live_spot = get_live_spot_price(symbol)
                    
                    if live_spot:
                        df, spot = generate_sample_data(symbol, live_spot)
                        st.session_state.options_df = df
                        st.session_state.spot_price = spot
                        st.session_state.data_loaded = True
                        st.session_state.last_update = datetime.now()
                        st.success(f"✅ Sample data with live spot: ₹{spot:,.2f}")
                    else:
                        # Fallback if live spot unavailable
                        default_spot = 23500 if symbol == "NIFTY" else 48000
                        df, spot = generate_sample_data(symbol, default_spot)
                        st.session_state.options_df = df
                        st.session_state.spot_price = spot
                        st.session_state.data_loaded = True
                        st.session_state.last_update = datetime.now()
                        st.warning(f"⚠️ Using default spot: ₹{spot:,.2f}")
                    
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.info("Using fallback data...")
                
                # Last resort
                try:
                    live_spot = get_live_spot_price(symbol)
                    if live_spot:
                        df, spot = generate_sample_data(symbol, live_spot)
                    else:
                        default_spot = 23500 if symbol == "NIFTY" else 48000
                        df, spot = generate_sample_data(symbol, default_spot)
                    
                    st.session_state.options_df = df
                    st.session_state.spot_price = spot
                    st.session_state.data_loaded = True
                    st.session_state.last_update = datetime.now()
                    st.info(f"📊 Loaded with spot: ₹{spot:,.2f}")
                except Exception as fallback_error:
                    st.error(f"Critical error: {str(fallback_error)}")
    
    # Risk-free rate
    st.subheader("🔧 Parameters")
    risk_free_rate = st.number_input(
        "Risk-Free Rate (%)",
        min_value=0.0,
        max_value=15.0,
        value=7.0,
        step=0.1
    ) / 100
    
    # Show last update time
    if st.session_state.data_loaded and st.session_state.last_update:
        st.markdown("---")
        st.markdown('<span class="live-indicator"></span> Live Data', unsafe_allow_html=True)
        st.caption(f"🕐 Updated: {st.session_state.last_update.strftime('%H:%M:%S')}")
        st.caption(f"📊 {symbol} Spot: ₹{st.session_state.spot_price:,.2f}")

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
        delta_color = "normal"
        st.metric(
            "💰 Spot Price",
            f"₹{spot_price:,.2f}",
            delta=None
        )
    
    with col2:
        flip_diff = gamma_levels['gamma_flip'] - spot_price
        st.metric(
            "🔄 Gamma Flip",
            f"₹{gamma_levels['gamma_flip']:,.0f}",
            delta=f"{flip_diff:+.0f}",
            delta_color="off"
        )
    
    with col3:
        regime = "Positive Gamma" if gamma_levels['total_gex'] > 0 else "Negative Gamma"
        regime_color = "🟢" if gamma_levels['total_gex'] > 0 else "🔴"
        st.metric(
            "📊 Market Regime",
            f"{regime_color} {regime}",
            delta=None
        )
    
    with col4:
        st.metric(
            "💹 Net GEX",
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
            st.write(f"**Support Level:** ₹{gamma_levels.get('support', 'N/A'):,}")
            st.write(f"**Resistance Level:** ₹{gamma_levels.get('resistance', 'N/A'):,}")
            st.write(f"**ATM Strike:** ₹{get_atm_strike(spot_price):,}")
        
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
            file_name=f"gex_data_{symbol}_{expiry_date}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
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
        
        **Data Source:**
        - This tool fetches **live spot prices** from NSE India
        - Option chain data from NSE (when available)
        - Sample data uses realistic simulated OI with live spot prices
        """)
        
        st.info("💡 **Tip**: Combine GEX analysis with price action, volume, and other indicators for best results.")
        st.warning("⚠️ **Disclaimer**: For educational purposes only. Not financial advice.")

else:
    # Welcome screen with live prices
    st.info("👈 Configure settings in the sidebar and click 'Fetch Data' to begin analysis")
    
    st.markdown("""
    ### Welcome to GEX Analyzer! 📊
    
    This tool analyzes **Gamma Exposure (GEX)** in NSE options with **LIVE data** using nselib.
    
    **Features:**
    - 🔴 **Live Spot Prices** from NSE (NIFTY & BANKNIFTY)
    - 📊 Real-time GEX calculations
    - 📈 Interactive visualizations
    - 🎯 Key support/resistance levels
    - 💹 Put-Call Ratio analysis
    - 📥 Downloadable data
    - 🔄 Market regime identification
    
    **Get Started:**
    1. Select an index (NIFTY or BANKNIFTY)
    2. Choose expiry type (Weekly or Monthly)
    3. Select data source
    4. Click "Fetch Data"
    """)
    
    st.markdown("---")
    
    # Fetch and display live market data
    st.subheader("📈 Current Market Levels")
    
    col1, col2 = st.columns(2)
    
    with col1:
        with st.spinner("Fetching NIFTY..."):
            try:
                nifty_quote = get_index_quote('NIFTY')
                if nifty_quote:
                    change_color = "🟢" if nifty_quote['change'] >= 0 else "🔴"
                    st.markdown(f"""
                    <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                padding: 1.5rem; 
                                border-radius: 10px; 
                                color: white;'>
                        <h4 style='margin: 0; color: white;'>NIFTY 50</h4>
                        <h2 style='margin: 0.5rem 0; color: white;'>₹{nifty_quote['last']:,.2f}</h2>
                        <p style='margin: 0;'>{change_color} {nifty_quote['change']:+.2f}%</p>
                        <hr style='margin: 0.5rem 0; border-color: rgba(255,255,255,0.3);'>
                        <small>High: ₹{nifty_quote['high']:,.2f} | Low: ₹{nifty_quote['low']:,.2f}</small>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.error("Unable to fetch NIFTY data")
            except Exception as e:
                st.error(f"Error: {str(e)}")
    
    with col2:
        with st.spinner("Fetching BANKNIFTY..."):
            try:
                banknifty_quote = get_index_quote('BANKNIFTY')
                if banknifty_quote:
                    change_color = "🟢" if banknifty_quote['change'] >= 0 else "🔴"
                    st.markdown(f"""
                    <div style='background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); 
                                padding: 1.5rem; 
                                border-radius: 10px; 
                                color: white;'>
                        <h4 style='margin: 0; color: white;'>BANK NIFTY</h4>
                        <h2 style='margin: 0.5rem 0; color: white;'>₹{banknifty_quote['last']:,.2f}</h2>
                        <p style='margin: 0;'>{change_color} {banknifty_quote['change']:+.2f}%</p>
                        <hr style='margin: 0.5rem 0; border-color: rgba(255,255,255,0.3);'>
                        <small>High: ₹{banknifty_quote['high']:,.2f} | Low: ₹{banknifty_quote['low']:,.2f}</small>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.error("Unable to fetch BANKNIFTY data")
            except Exception as e:
                st.error(f"Error: {str(e)}")
    
    # Market status
    try:
        market_status = get_market_status()
        status_color = "🟢" if market_status['market_state'] == 'Market Open' else "🔴"
        st.caption(f"{status_color} Market Status: {market_status['market_state']} | Updated: {market_status['timestamp']}")
    except:
        st.caption("Market status: Unknown")
    
    st.markdown("---")
    st.info("💡 **Tip**: These are live prices from NSE via nselib. Click 'Fetch Data' to start your analysis!")
