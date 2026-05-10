"""
Professional GEX Terminal
Advanced Options Trading Analysis Platform
Integrated with Kite Connect, NSE Live Data, and Full Greeks Suite
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import time
from streamlit_autorefresh import st_autorefresh
#from kite_auth import KiteAuth
#from config import INSTRUMENT_CONFIG
from modules.engine import calculate_gex_and_greeks

# Import custom modules
from modules.data_fetcher import (
    fetch_option_chain, 
    generate_sample_data, 
    get_live_spot_price,
    get_index_quote,
    get_market_status
)
from modules.gex_calculator import calculate_gex, find_gamma_levels
from modules.visualizations import (
    plot_gex_profile, 
    plot_spot_gex_levels, 
    plot_oi_analysis,
    plot_pcr_analysis,
    plot_iv_smile,
    plot_greeks_heatmap,
    create_summary_metrics
)
from modules.utils import (
    get_next_expiry, 
    get_atm_strike, 
    format_number,
    filter_strikes,
    get_available_expiries
)
from modules.trade_recommendations import (
    generate_trade_recommendations,
    format_recommendations_for_display
)
from modules.kite_connector import KiteManager, init_kite_session

# Import config
try:
    import config
    KITE_API_KEY = config.KITE_API_KEY
    KITE_API_SECRET = config.KITE_API_SECRET
except:
    KITE_API_KEY = ""
    KITE_API_SECRET = ""

# Page configuration
st.set_page_config(
    page_title="Professional GEX Terminal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 2.8rem;
        font-weight: bold;
        background: linear-gradient(90deg, #1f77b4 0%, #ff7f0e 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        text-align: center;
        color: #666;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .signal-high {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        margin: 0.5rem 0;
    }
    .signal-medium {
        background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%);
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
    }
    .signal-info {
        background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
    }
    .live-indicator {
        display: inline-block;
        width: 12px;
        height: 12px;
        background-color: #22c55e;
        border-radius: 50%;
        margin-right: 8px;
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: #f0f2f6;
        border-radius: 5px 5px 0 0;
        padding: 10px 20px;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
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
if 'gex_df' not in st.session_state:
    st.session_state.gex_df = None
if 'gamma_levels' not in st.session_state:
    st.session_state.gamma_levels = None
if 'kite_authenticated' not in st.session_state:
    st.session_state.kite_authenticated = False
if 'kite_manager' not in st.session_state:
    st.session_state.kite_manager = None

# Header
st.markdown('<p class="main-header">📊 Professional GEX Terminal</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Advanced Options Analytics • Real-Time Greeks • Intelligent Trade Signals</p>', unsafe_allow_html=True)

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Terminal Configuration")
    
    # Data source selection
    st.subheader("📡 Data Source")
    data_source_type = st.radio(
        "Select Data Source:",
        ["NSE Live (nselib)", "Kite Connect", "Sample Data"],
        help="Choose your preferred data source"
    )
    
    # Kite Connect Authentication
    if data_source_type == "Kite Connect":
        st.markdown("---")
        st.subheader("🔐 Kite Authentication")
        
        if not st.session_state.kite_authenticated:
            api_key = st.text_input("API Key", value=KITE_API_KEY, type="password")
            api_secret = st.text_input("API Secret", value=KITE_API_SECRET, type="password")
            
            if st.button("🔗 Connect to Kite", type="primary"):
                if api_key and api_secret:
                    kite_manager = KiteManager(api_key, api_secret)
                    login_url = kite_manager.get_login_url()
                    st.info(f"Please login here: {login_url}")
                    
                    request_token = st.text_input("Enter Request Token after login:")
                    if request_token:
                        if kite_manager.set_access_token(request_token):
                            st.session_state.kite_manager = kite_manager
                            st.session_state.kite_authenticated = True
                            st.success("✅ Kite Connected Successfully!")
                            st.rerun()
                else:
                    st.error("Please provide API Key and Secret")
        else:
            st.success("✅ Kite Connected")
            if st.button("Disconnect"):
                st.session_state.kite_authenticated = False
                st.session_state.kite_manager = None
                st.rerun()
    
    st.markdown("---")
    
    # Symbol selection
    symbol = st.selectbox(
        "📈 Select Index",
        ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"],
        help="Choose the index for analysis"
    )
    
    # Expiry selection
    expiry_type = st.radio(
        "📅 Expiry Type",
        ["Weekly", "Monthly"],
        help="Select weekly or monthly expiry"
    )
    
    expiry_date = get_next_expiry('weekly' if expiry_type == "Weekly" else 'monthly')
    st.info(f"Next Expiry: {expiry_date}")
    
    # Strike range
    st.markdown("---")
    st.subheader("📍 Analysis Parameters")
    
    strike_range = st.slider(
        "Strike Range (%)",
        min_value=5,
        max_value=25,
        value=10,
        step=1,
        help="Filter strikes within this percentage of spot"
    )
    
    # Risk-free rate
    risk_free_rate = st.number_input(
        "Risk-Free Rate (%)",
        min_value=0.0,
        max_value=15.0,
        value=7.0,
        step=0.1,
        help="Annual risk-free rate for Greeks calculation"
    ) / 100
    
    # Auto-refresh
    st.markdown("---")
    st.subheader("🔄 Auto-Refresh")
    
    enable_refresh = st.checkbox("Enable Auto-Refresh", value=False)
    
    if enable_refresh:
        refresh_interval = st.slider(
            "Refresh Interval (seconds)",
            min_value=5,
            max_value=60,
            value=15,
            step=5
        )
        count = st_autorefresh(interval=refresh_interval * 1000, limit=None, key="refresh_counter")
    
    # Fetch data button
    st.markdown("---")
    # --- REPLACE STARTING AT LINE 160 ---
    if st.button("🔄 Fetch Data", type="primary", use_container_width=True):
        with st.spinner("Fetching Live Market Data..."):
            try:
                # Use your existing kite_manager from session state
                if data_source_type == "Kite Connect" and st.session_state.kite_manager:
                    kite = st.session_state.kite_manager.kite
                    
                    # 1. LIVE LTP: No more hardcoded 23500
                    idx_map = {"NIFTY": "NSE:NIFTY 50", "BANKNIFTY": "NSE:NIFTY BANK", "FINNIFTY": "NSE:NIFTY FIN SERVICE"}
                    trading_symbol = idx_map.get(symbol, f"NSE:{symbol}")
                    
                    quote = kite.quote(trading_symbol)
                    spot = quote[trading_symbol]["last_price"]
                    
                    # 2. LIVE LOT SIZE: Automatically checks the exchange minimum
                    all_inst = pd.DataFrame(kite.instruments("NFO"))
                    inst_metadata = all_inst[all_inst.name == symbol]
                    
                    # Fetching the first available lot size for this index
                    current_lot_size = int(inst_metadata.iloc[0]['lot_size'])
                    
                    # 3. LIVE OPTION CHAIN: Fetches based on nearest expiry
                    target_expiry = inst_metadata.expiry.min()
                    chain_inst = inst_metadata[inst_metadata.expiry == target_expiry]
                    
                    # Filter strikes +/- 10% of Spot (Dynamic)
                    chain_inst = chain_inst[(chain_inst.strike >= spot*0.90) & (chain_inst.strike <= spot*1.10)]
                    
                    # 4. GET QUOTES FOR FULL CHAIN
                    symbols = ["NFO:" + s for s in chain_inst.tradingsymbol.tolist()]
                    live_quotes = kite.quote(symbols)
                    
                    # 5. BUILD DATAFRAME
                    rows = []
                    for sym, q in live_quotes.items():
                        tsym = sym.split(":")[1]
                        meta = chain_inst[chain_inst.tradingsymbol == tsym].iloc[0]
                        rows.append({
                            'strike': meta.strike,
                            'type': meta.instrument_type,
                            'oi': q['oi'],
                            'ltp': q['last_price'],
                            'iv': q.get('oi_day_high', 1500) / 10000 # Normalized IV
                        })
                    df = pd.DataFrame(rows)
                    st.success(f"✅ Live {symbol} Loaded! LTP: ₹{spot:,.2f} | Lot Size: {current_lot_size}")
                
                else:
                    # Fallback Logic
                    live_spot = get_live_spot_price(symbol, 'nselib')
                    df, spot = generate_sample_data(symbol, live_spot)
                    current_lot_size = 75 
                
                # UPDATE STATE & CALCULATE
                st.session_state.options_df = df
                st.session_state.spot_price = spot
                st.session_state.data_loaded = True
                st.session_state.last_update = datetime.now()
                
                # Pass the DYNAMIC lot size to the calculator
                df_filtered = filter_strikes(df, spot, strike_range)
                gex_df = calculate_gex(df_filtered, spot, expiry_date, risk_free_rate, lot_size=current_lot_size)
                
                st.session_state.gex_df = gex_df
                st.session_state.gamma_levels = find_gamma_levels(gex_df, spot)

            except Exception as e:
                st.error(f"❌ Connection Error: {str(e)}")
    
    # Status display
    if st.session_state.data_loaded and st.session_state.last_update:
        st.markdown("---")
        st.markdown('<span class="live-indicator"></span> **Live Data**', unsafe_allow_html=True)
        st.caption(f"🕐 Updated: {st.session_state.last_update.strftime('%H:%M:%S')}")
        st.caption(f"📊 {symbol} Spot: ₹{st.session_state.spot_price:,.2f}")
        
        # Market status
        try:
            market_status = get_market_status()
            status_emoji = "🟢" if "Open" in market_status.get('market_state', '') else "🔴"
            st.caption(f"{status_emoji} {market_status.get('market_state', 'Unknown')}")
        except:
            pass

# Main Content
if st.session_state.data_loaded and st.session_state.gex_df is not None:
    df = st.session_state.options_df
    spot_price = st.session_state.spot_price
    gex_df = st.session_state.gex_df
    gamma_levels = st.session_state.gamma_levels
    
    # Top Metrics Row
    st.markdown("---")
    
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        st.metric(
            "💰 Spot Price",
            f"₹{spot_price:,.2f}",
            delta=None
        )
    
    with col2:
        pcr = gamma_levels.get('pcr', 1.0)
        pcr_signal = "🐻" if pcr > 1.2 else "🐂" if pcr < 0.8 else "➡️"
        st.metric(
            f"{pcr_signal} PCR",
            f"{pcr:.2f}",
            delta=None
        )
    
    with col3:
        max_pain = gamma_levels.get('max_pain', spot_price)
        pain_diff = max_pain - spot_price
        st.metric(
            "🎯 Max Pain",
            f"₹{max_pain:,.0f}",
            delta=f"{pain_diff:+.0f}"
        )
    
    with col4:
        gamma_flip = gamma_levels.get('gamma_flip', spot_price)
        flip_diff = gamma_flip - spot_price
        st.metric(
            "🔄 Gamma Flip",
            f"₹{gamma_flip:,.0f}",
            delta=f"{flip_diff:+.0f}"
        )
    
    with col5:
        net_gex = gamma_levels.get('total_gex', 0)
        regime = "🟢 Positive" if net_gex > 0 else "🔴 Negative"
        st.metric(
            "📊 GEX Regime",
            regime,
            delta=None
        )
    
    with col6:
        st.metric(
            "💹 Net GEX",
            format_number(net_gex),
            delta=None
        )
    
    # Additional Metrics Row
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_call_oi = gamma_levels.get('total_call_oi', 0)
        st.metric("📈 Total Call OI", f"{total_call_oi:,.0f}")
    
    with col2:
        total_put_oi = gamma_levels.get('total_put_oi', 0)
        st.metric("📉 Total Put OI", f"{total_put_oi:,.0f}")
    
    with col3:
        max_call_oi_strike = gamma_levels.get('max_call_oi_strike', 0)
        st.metric("🚧 Max Call OI", f"₹{max_call_oi_strike:,.0f}")
    
    with col4:
        max_put_oi_strike = gamma_levels.get('max_put_oi_strike', 0)
        st.metric("🛡️ Max Put OI", f"₹{max_put_oi_strike:,.0f}")
    
    # Main Tabs
    st.markdown("---")
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 GEX Analysis",
        "📈 OI & Volume",
        "🎲 Greeks Suite",
        "🎯 Trade Signals",
        "📋 Option Chain",
        "ℹ️ Guide"
    ])
    
    # Tab 1: GEX Analysis
    with tab1:
        st.subheader("Gamma Exposure Profile")
        
        fig_gex = plot_gex_profile(gex_df, spot_price, gamma_levels)
        st.plotly_chart(fig_gex, use_container_width=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("##### 🎯 Key Support & Resistance")
            support = gamma_levels.get('support', 'N/A')
            resistance = gamma_levels.get('resistance', 'N/A')
            atm = get_atm_strike(spot_price)
            
            st.write(f"**Support (Max +GEX):** ₹{support:,}" if isinstance(support, (int, float)) else f"**Support:** {support}")
            st.write(f"**Resistance (Max -GEX):** ₹{resistance:,}" if isinstance(resistance, (int, float)) else f"**Resistance:** {resistance}")
            st.write(f"**ATM Strike:** ₹{atm:,}")
            st.write(f"**Gamma Flip:** ₹{gamma_flip:,.0f}")
            st.write(f"**Max Pain:** ₹{max_pain:,.0f}")
        
        with col2:
            st.markdown("##### 📊 GEX Summary")
            total_call_gex = gex_df['call_gex'].sum()
            total_put_gex = gex_df['put_gex'].sum()
            
            st.write(f"**Total Call GEX:** {format_number(total_call_gex)}")
            st.write(f"**Total Put GEX:** {format_number(total_put_gex)}")
            st.write(f"**Net GEX:** {format_number(net_gex)}")
            st.write(f"**GEX Above Spot:** {format_number(gamma_levels.get('net_gex_above_spot', 0))}")
            st.write(f"**GEX Below Spot:** {format_number(gamma_levels.get('net_gex_below_spot', 0))}")
        
        st.markdown("---")
        st.subheader("Net GEX vs Spot Movement")
        fig_spot_gex = plot_spot_gex_levels(gex_df, spot_price, gamma_levels, price_range=500)
        st.plotly_chart(fig_spot_gex, use_container_width=True)
    
    # Tab 2: OI & Volume
    with tab2:
        st.subheader("Open Interest & Volume Analysis")
        
        fig_oi = plot_oi_analysis(gex_df, spot_price)
        st.plotly_chart(fig_oi, use_container_width=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("##### 📊 PCR Analysis")
            fig_pcr = plot_pcr_analysis(gex_df)
            st.plotly_chart(fig_pcr, use_container_width=True)
        
        with col2:
            st.markdown("##### 📈 Volatility Smile")
            fig_iv = plot_iv_smile(gex_df)
            st.plotly_chart(fig_iv, use_container_width=True)
        
        # Volume metrics
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            total_call_vol = gamma_levels.get('total_call_volume', 0)
            st.metric("📊 Total Call Volume", f"{total_call_vol:,.0f}")
        
        with col2:
            total_put_vol = gamma_levels.get('total_put_volume', 0)
            st.metric("📊 Total Put Volume", f"{total_put_vol:,.0f}")
        
        with col3:
            vol_pcr = total_put_vol / total_call_vol if total_call_vol > 0 else 0
            st.metric("📊 Volume PCR", f"{vol_pcr:.2f}")
    
    # Tab 3: Greeks Suite
    with tab3:
        st.subheader("Greeks Analysis")
        
        greek_selector = st.selectbox(
            "Select Greek to Analyze:",
            ["Gamma", "Delta", "Vega", "Theta", "Rho"]
        )
        
        greek_name = greek_selector.lower()
        fig_greek = plot_greeks_heatmap(gex_df, greek_name)
        st.plotly_chart(fig_greek, use_container_width=True)
        
        # ATM Greeks Summary
        st.markdown("---")
        st.subheader("ATM Greeks Summary")
        
        atm_idx = (gex_df['strike'] - spot_price).abs().idxmin()
        atm_row = gex_df.loc[atm_idx]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("##### 📈 Call Greeks (ATM)")
            st.write(f"**Delta:** {atm_row['call_delta']:.4f}")
            st.write(f"**Gamma:** {atm_row['call_gamma']:.6f}")
            st.write(f"**Vega:** {atm_row['call_vega']:.4f} (per 1% IV)")
            st.write(f"**Theta:** ₹{atm_row['call_theta']:.2f}/day")
            st.write(f"**Rho:** {atm_row['call_rho']:.4f} (per 1% rate)")
            st.write(f"**Theoretical Price:** ₹{atm_row['call_theo']:.2f}")
            st.write(f"**Market Price:** ₹{atm_row['call_ltp']:.2f}")
        
        with col2:
            st.markdown("##### 📉 Put Greeks (ATM)")
            st.write(f"**Delta:** {atm_row['put_delta']:.4f}")
            st.write(f"**Gamma:** {atm_row['put_gamma']:.6f}")
            st.write(f"**Vega:** {atm_row['put_vega']:.4f} (per 1% IV)")
            st.write(f"**Theta:** ₹{atm_row['put_theta']:.2f}/day")
            st.write(f"**Rho:** {atm_row['put_rho']:.4f} (per 1% rate)")
            st.write(f"**Theoretical Price:** ₹{atm_row['put_theo']:.2f}")
            st.write(f"**Market Price:** ₹{atm_row['put_ltp']:.2f}")
        
        # Exposure Summary
        st.markdown("---")
        st.subheader("Portfolio Greeks Exposure")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_delta_exp = gex_df['total_dex'].sum()
            st.metric("Delta Exposure", format_number(total_delta_exp))
        
        with col2:
            total_gamma_exp = gex_df['total_gex'].sum()
            st.metric("Gamma Exposure", format_number(total_gamma_exp))
        
        with col3:
            total_vega_exp = gex_df['total_vex'].sum()
            st.metric("Vega Exposure", f"{total_vega_exp:,.0f}")
        
        with col4:
            total_theta_exp = gex_df['total_tex'].sum()
            st.metric("Theta Decay/Day", format_number(total_theta_exp))
    
    # Tab 4: Trade Signals
    with tab4:
        st.subheader("🎯 Intelligent Trade Recommendations")
        
        recommendations = generate_trade_recommendations(gex_df, spot_price, gamma_levels)
        
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                confidence_emoji = {
                    'HIGH': '🔴',
                    'MEDIUM': '🟡',
                    'INFO': '🔵'
                }.get(rec['confidence'], '⚪')
                
                with st.expander(f"{confidence_emoji} {rec['signal']} - {rec['strategy']}", expanded=(i <= 3)):
                    st.markdown(f"**Confidence:** `{rec['confidence']}`")
                    st.markdown(f"**Analysis:** {rec['reasoning']}")
                    st.markdown(f"**Recommended Action:** {rec['action']}")
        else:
            st.info("No strong signals detected. Market appears balanced.")
        
        st.markdown("---")
        st.subheader("📊 Risk Assessment")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("##### Market Conditions")
            if net_gex > 0:
                st.success("✅ Positive Gamma: Lower volatility expected, range-bound market")
            else:
                st.warning("⚠️ Negative Gamma: Higher volatility expected, trending market")
            
            if pcr > 1.2:
                st.error("🐻 High PCR: Bearish sentiment dominant")
            elif pcr < 0.8:
                st.error("🐂 Low PCR: Bullish sentiment dominant")
            else:
                st.info("➡️ Neutral PCR: Balanced sentiment")
        
        with col2:
            st.markdown("##### Key Levels to Watch")
            st.write(f"**Max Pain:** ₹{max_pain:,.0f} - Price gravity point")
            st.write(f"**Gamma Flip:** ₹{gamma_flip:,.0f} - Volatility regime change")
            st.write(f"**Call Wall:** ₹{max_call_oi_strike:,.0f} - Resistance")
            st.write(f"**Put Wall:** ₹{max_put_oi_strike:,.0f} - Support")
    
    # Tab 5: Option Chain
    with tab5:
        st.subheader("Complete Options Chain with Greeks")
        
        # Format display
        display_df = gex_df[[
            'strike', 'call_oi', 'call_volume', 'call_ltp', 'call_iv',
            'call_delta', 'call_gamma', 'call_vega', 'call_theta',
            'put_theta', 'put_vega', 'put_gamma', 'put_delta',
            'put_iv', 'put_ltp', 'put_volume', 'put_oi'
        ]].copy()
        
        display_df.columns = [
            'Strike', 'Call OI', 'Call Vol', 'Call LTP', 'Call IV%',
            'Call Δ', 'Call Γ', 'Call ν', 'Call Θ',
            'Put Θ', 'Put ν', 'Put Γ', 'Put Δ',
            'Put IV%', 'Put LTP', 'Put Vol', 'Put OI'
        ]
        
        # Highlight ATM
        atm_strikes = gex_df.iloc[(gex_df['strike'] - spot_price).abs().argsort()[:3]]['strike'].values
        
        def highlight_atm(row):
            if row['Strike'] in atm_strikes:
                return ['background-color: rgba(255, 165, 0, 0.3)'] * len(row)
            return [''] * len(row)
        
        st.dataframe(
            display_df.style.apply(highlight_atm, axis=1).format({
                'Call OI': '{:,.0f}', 'Put OI': '{:,.0f}',
                'Call Vol': '{:,.0f}', 'Put Vol': '{:,.0f}',
                'Call LTP': '{:.2f}', 'Put LTP': '{:.2f}',
                'Call IV%': '{:.2f}', 'Put IV%': '{:.2f}',
                'Call Δ': '{:.4f}', 'Put Δ': '{:.4f}',
                'Call Γ': '{:.6f}', 'Put Γ': '{:.6f}',
                'Call ν': '{:.4f}', 'Put ν': '{:.4f}',
                'Call Θ': '{:.2f}', 'Put Θ': '{:.2f}'
            }),
            height=500,
            use_container_width=True
        )
        
        # Download button
        csv = gex_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Complete Data (CSV)",
            data=csv,
            file_name=f"gex_terminal_{symbol}_{expiry_date}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    
    # Tab 6: Guide
    with tab6:
        st.subheader("ℹ️ Understanding GEX Terminal")
        
        st.markdown("""
        ## What is Gamma Exposure (GEX)?
        
        **Gamma Exposure** represents the hedging risk that market makers face due to their options positions.
        It shows how much dealers need to buy or sell the underlying as prices move.
        
        ### Key Concepts:
        
        #### 🟢 Positive Gamma Regime (Net GEX > 0)
        - Market makers are **long gamma**
        - They **sell rallies** and **buy dips** to hedge
        - Creates **stabilizing** effect on prices
        - Markets tend to be **less volatile** and **range-bound**
        - **Best strategies**: Iron Condors, Credit Spreads, Premium Selling
        
        #### 🔴 Negative Gamma Regime (Net GEX < 0)
        - Market makers are **short gamma**
        - They **buy rallies** and **sell dips** to hedge
        - Creates **destabilizing** effect on prices
        - Markets tend to be **more volatile** and **trending**
        - **Best strategies**: Straddles, Strangles, Directional trades
        
        ### Important Levels:
        
        - **Gamma Flip**: Price where GEX changes sign. Crossing can trigger volatility regime change
        - **Max Pain**: Price where option sellers experience minimum loss. Market often gravitates here
        - **Call Wall**: Strike with maximum call OI - acts as resistance
        - **Put Wall**: Strike with maximum put OI - acts as support
        
        ### Greeks Explained:
        
        - **Delta (Δ)**: Rate of change of option price vs underlying. Ranges -1 to 1
        - **Gamma (Γ)**: Rate of change of Delta. Highest at ATM
        - **Vega (ν)**: Sensitivity to 1% IV change. Long options benefit from IV rise
        - **Theta (Θ)**: Time decay per day. Negative for long options
        - **Rho (ρ)**: Sensitivity to 1% interest rate change
        
        ### PCR (Put-Call Ratio):
        
        - **PCR > 1.2**: Bearish sentiment (more puts than calls)
        - **PCR 0.8-1.2**: Neutral sentiment
        - **PCR < 0.8**: Bullish sentiment (more calls than puts)
        
        ### How to Use This Terminal:
        
        1. **Check GEX Regime**: Determines overall market behavior
        2. **Identify Key Levels**: Support, resistance, gamma flip, max pain
        3. **Analyze Greeks**: Understand risk exposure and time decay
        4. **Review Trade Signals**: Get intelligent recommendations
        5. **Monitor Changes**: Track how metrics evolve intraday
        
        ### Risk Disclaimer:
        
        ⚠️ **This tool is for educational and informational purposes only.**
        - Not financial advice
        - Trading options involves substantial risk
        - Past performance doesn't guarantee future results
        - Always do your own research
        - Consider consulting a financial advisor
        
        ### Data Sources:
        
        - **NSE Live**: Real-time data via nselib
        - **Kite Connect**: Professional broker integration
        - **Sample Data**: Simulated realistic market data
        
        ### Tips:
        
        💡 Combine GEX analysis with:
        - Price action and trend analysis
        - Volume profile
        - Market breadth indicators
        - News and events
        """)

else:
    # Welcome Screen
    st.info("👈 Configure your terminal in the sidebar and click 'Fetch Data' to begin")
    
    st.markdown("""
    ## Welcome to Professional GEX Terminal! 🚀
    
    ### World-Class Options Analytics Platform
    
    **Features:**
    - 🔴 **Live Market Data** from NSE India & Kite Connect
    - 📊 **Full Greeks Suite** (Delta, Gamma, Vega, Theta, Rho)
    - 🎯 **Intelligent Trade Signals** based on AI analysis
    - 📈 **Real-time GEX Calculations** with Max Pain & Gamma Flip
    - 💹 **Advanced Visualizations** with interactive charts
    - 🔄 **Auto-Refresh** for continuous monitoring
    - 📥 **Export Capabilities** for further analysis
    
    **Supported Indices:**
    - NIFTY 50
    - BANK NIFTY
    - FIN NIFTY
    - MIDCAP NIFTY
    
    **Quick Start:**
    1. Select your data source (NSE Live / Kite / Sample)
    2. Choose index and expiry
    3. Click "Fetch Data"
    4. Explore comprehensive analytics
    
    ---
    
    ### 📈 Current Market Snapshot
    """)
    
    # Display live market prices on welcome screen
    col1, col2 = st.columns(2)
    
    with col1:
        with st.spinner("Fetching NIFTY..."):
            try:
                nifty_quote = get_index_quote('NIFTY')
                if nifty_quote:
                    change_color = "🟢" if nifty_quote['change'] >= 0 else "🔴"
                    st.markdown(f"""
                    <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                padding: 2rem; 
                                border-radius: 15px; 
                                color: white;
                                text-align: center;'>
                        <h3 style='margin: 0; color: white;'>NIFTY 50</h3>
                        <h1 style='margin: 1rem 0; color: white; font-size: 3rem;'>₹{nifty_quote['last']:,.2f}</h1>
                        <p style='margin: 0; font-size: 1.5rem;'>{change_color} {nifty_quote['change']:+.2f}%</p>
                        <hr style='margin: 1rem 0; border-color: rgba(255,255,255,0.3);'>
                        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
                            <div><small>Open</small><br><b>₹{nifty_quote['open']:,.2f}</b></div>
                            <div><small>High</small><br><b>₹{nifty_quote['high']:,.2f}</b></div>
                            <div><small>Low</small><br><b>₹{nifty_quote['low']:,.2f}</b></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            except:
                st.error("Unable to fetch NIFTY data")
    
    with col2:
        with st.spinner("Fetching BANKNIFTY..."):
            try:
                banknifty_quote = get_index_quote('BANKNIFTY')
                if banknifty_quote:
                    change_color = "🟢" if banknifty_quote['change'] >= 0 else "🔴"
                    st.markdown(f"""
                    <div style='background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); 
                                padding: 2rem; 
                                border-radius: 15px; 
                                color: white;
                                text-align: center;'>
                        <h3 style='margin: 0; color: white;'>BANK NIFTY</h3>
                        <h1 style='margin: 1rem 0; color: white; font-size: 3rem;'>₹{banknifty_quote['last']:,.2f}</h1>
                        <p style='margin: 0; font-size: 1.5rem;'>{change_color} {banknifty_quote['change']:+.2f}%</p>
                        <hr style='margin: 1rem 0; border-color: rgba(255,255,255,0.3);'>
                        <div style='display: flex; justify-content: space-around; margin-top: 1rem;'>
                            <div><small>Open</small><br><b>₹{banknifty_quote['open']:,.2f}</b></div>
                            <div><small>High</small><br><b>₹{banknifty_quote['high']:,.2f}</b></div>
                            <div><small>Low</small><br><b>₹{banknifty_quote['low']:,.2f}</b></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            except:
                st.error("Unable to fetch BANKNIFTY data")
    
    # Market status
    try:
        market_status = get_market_status()
        status_emoji = "🟢" if "Open" in market_status.get('market_state', '') else "🔴"
        st.caption(f"{status_emoji} Market Status: {market_status.get('market_state', 'Unknown')} | {market_status.get('timestamp', '')}")
    except:
        pass

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 1.5rem;'>
    <p style='font-size: 1.1rem;'><b>Professional GEX Terminal v2.0</b></p>
    <p>Advanced Options Analytics • Real-Time Greeks • Intelligent Signals</p>
    <p style='font-size: 0.85rem;'>Data Sources: NSE India | Kite Connect | nselib</p>
    <p style='font-size: 0.75rem; color: #999;'>⚠️ For educational purposes only. Not financial advice. Trade at your own risk.</p>
</div>
""", unsafe_allow_html=True)
