"""
Professional GEX Terminal
Advanced Options Trading Analysis Platform
Integrated with Kite Connect, NSE Live Data, and Full Greeks Suite

Changes vs original
--------------------
* Expiry list is fetched from Kite instruments when connected (actual calendar)
  or computed using the correct weekday for each index as fallback
* Lot size is shown in sidebar and fetched dynamically from Kite
* Sidebar shows lot-size source (Kite / fallback)
* All hardcoded expiry / lot-size references removed from data pipeline
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import time
from streamlit_autorefresh import st_autorefresh

# Import custom modules
from modules.data_fetcher import (
    fetch_option_chain,
    generate_sample_data,
    get_live_spot_price,
    get_index_quote,
    get_market_status,
)
from modules.gex_calculator import calculate_gex, find_gamma_levels
from modules.visualizations import (
    plot_gex_profile,
    plot_spot_gex_levels,
    plot_oi_analysis,
    plot_pcr_analysis,
    plot_iv_smile,
    plot_greeks_heatmap,
    create_summary_metrics,
)
from modules.utils import (
    get_next_expiry_for_symbol,
    get_expiries_for_symbol,
    get_atm_strike,
    format_number,
    filter_strikes,
    get_lot_size,
)
from modules.trade_recommendations import (
    generate_trade_recommendations,
    format_recommendations_for_display,
)
from modules.kite_connector import KiteManager, init_kite_session

# Config
try:
    import config
    KITE_API_KEY    = config.KITE_API_KEY
    KITE_API_SECRET = config.KITE_API_SECRET
except Exception:
    KITE_API_KEY    = ""
    KITE_API_SECRET = ""

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Professional GEX Terminal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
    <style>
    .main-header {
        font-size: 2.8rem; font-weight: bold;
        background: linear-gradient(90deg, #1f77b4 0%, #ff7f0e 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        text-align: center; margin-bottom: 0.5rem;
    }
    .sub-header { text-align: center; color: #666; font-size: 1.1rem; margin-bottom: 2rem; }
    .live-indicator {
        display: inline-block; width: 12px; height: 12px;
        background-color: #22c55e; border-radius: 50%; margin-right: 8px;
        animation: pulse 2s infinite;
    }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px; background-color: #f0f2f6;
        border-radius: 5px 5px 0 0; padding: 10px 20px; font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
for key, default in [
    ('data_loaded',         False),
    ('options_df',          None),
    ('spot_price',          None),
    ('last_update',         None),
    ('gex_df',              None),
    ('gamma_levels',        None),
    ('kite_authenticated',  False),
    ('kite_manager',        None),
    ('lot_size',            None),
    ('selected_expiry',     None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown('<p class="main-header">📊 Professional GEX Terminal</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Advanced Options Analytics • Real-Time Greeks • Intelligent Trade Signals</p>',
            unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Terminal Configuration")

    # ── Data source ──────────────────────────────────────────────────────────
    st.subheader("📡 Data Source")
    data_source_type = st.radio(
        "Select Data Source:",
        ["NSE Live (nselib)", "Kite Connect", "Sample Data"],
        help="Choose your preferred data source",
    )

    # ── Kite authentication ──────────────────────────────────────────────────
    if data_source_type == "Kite Connect":
        st.markdown("---")
        st.subheader("🔐 Kite Authentication")

        if not st.session_state.kite_authenticated:
            api_key    = st.text_input("API Key",    value=KITE_API_KEY,    type="password")
            api_secret = st.text_input("API Secret", value=KITE_API_SECRET, type="password")

            if st.button("🔗 Connect to Kite", type="primary"):
                if api_key and api_secret:
                    kite_manager = KiteManager(api_key, api_secret)
                    login_url = kite_manager.get_login_url()
                    st.info(f"Please login here: {login_url}")

                    request_token = st.text_input("Enter Request Token after login:")
                    if request_token:
                        if kite_manager.set_access_token(request_token):
                            st.session_state.kite_manager        = kite_manager
                            st.session_state.kite_authenticated  = True
                            st.success("✅ Kite Connected Successfully!")
                            st.rerun()
                else:
                    st.error("Please provide API Key and Secret")
        else:
            st.success("✅ Kite Connected")
            if st.button("Disconnect"):
                st.session_state.kite_authenticated = False
                st.session_state.kite_manager       = None
                st.rerun()

    st.markdown("---")

    # ── Symbol selection ─────────────────────────────────────────────────────
    symbol = st.selectbox(
        "📈 Select Index",
        ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"],
        help="Choose the index for analysis",
    )

    # ── Lot size (dynamic) ───────────────────────────────────────────────────
    kite_mgr = st.session_state.kite_manager if data_source_type == "Kite Connect" else None
    current_lot_size = get_lot_size(symbol, kite_mgr)
    st.session_state.lot_size = current_lot_size

    lot_src = "🔗 Kite" if (kite_mgr is not None) else "📋 Fallback"
    st.info(f"📦 Lot Size ({lot_src}): **{current_lot_size}**")

    # ── Expiry selection ─────────────────────────────────────────────────────
    expiry_type = st.radio(
        "📅 Expiry Type",
        ["Weekly", "Monthly"],
        help="Select weekly or monthly expiry",
    )
    et_key = 'weekly' if expiry_type == "Weekly" else 'monthly'

    # Fetch actual expiries from Kite when connected
    available_expiries = get_expiries_for_symbol(symbol, kite_mgr, et_key)

    if available_expiries:
        expiry_date = st.selectbox(
            "📅 Select Expiry",
            available_expiries,
            index=0,
            help="Expiries fetched from Kite instruments" if kite_mgr else "Computed from NSE calendar rules",
        )
        expiry_src = "🔗 Kite instruments" if kite_mgr else "📋 Computed"
        st.caption(f"Source: {expiry_src}")
    else:
        expiry_date = get_next_expiry_for_symbol(symbol, et_key)
        st.info(f"Next Expiry: {expiry_date}")

    st.session_state.selected_expiry = expiry_date

    # ── Analysis parameters ──────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📍 Analysis Parameters")

    strike_range = st.slider(
        "Strike Range (%)",
        min_value=5, max_value=25, value=10, step=1,
        help="Filter strikes within this percentage of spot",
    )

    risk_free_rate = st.number_input(
        "Risk-Free Rate (%)",
        min_value=0.0, max_value=15.0, value=7.0, step=0.1,
        help="Annual risk-free rate for Greeks calculation",
    ) / 100

    # ── Auto-refresh ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🔄 Auto-Refresh")
    enable_refresh = st.checkbox("Enable Auto-Refresh", value=False)
    if enable_refresh:
        refresh_interval = st.slider(
            "Refresh Interval (seconds)",
            min_value=5, max_value=60, value=15, step=5,
        )
        st_autorefresh(interval=refresh_interval * 1000, limit=None, key="refresh_counter")

    # ── Fetch button ─────────────────────────────────────────────────────────
    st.markdown("---")
    if st.button("🔄 Fetch Data", type="primary", use_container_width=True):
        with st.spinner("Fetching market data..."):
            try:
                source = ('kite'   if data_source_type == "Kite Connect"
                          else 'nselib' if data_source_type == "NSE Live (nselib)"
                          else 'sample')

                if source == 'sample':
                    live_spot = get_live_spot_price(symbol, 'nselib')
                    df, spot  = generate_sample_data(symbol, live_spot, expiry_date)
                    st.success(f"✅ Sample data loaded · Spot: ₹{spot:,.2f}")
                else:
                    df, spot = fetch_option_chain(
                        symbol, expiry_date, source, kite_mgr, risk_free_rate
                    )
                    if df is not None and not df.empty and spot:
                        st.success(f"✅ Live data · Spot: ₹{spot:,.2f} · {len(df)} rows")
                    else:
                        st.warning("⚠️ Live fetch failed – using sample data")
                        live_spot = get_live_spot_price(symbol, 'nselib')
                        df, spot  = generate_sample_data(symbol, live_spot, expiry_date)

                if df is not None and not df.empty:
                    st.session_state.options_df  = df
                    st.session_state.spot_price  = spot
                    st.session_state.data_loaded = True
                    st.session_state.last_update = datetime.now()

                    df_filtered  = filter_strikes(df, spot, strike_range)
                    gex_df       = calculate_gex(df_filtered, spot, expiry_date, risk_free_rate)
                    gamma_levels = find_gamma_levels(gex_df, spot)

                    st.session_state.gex_df       = gex_df
                    st.session_state.gamma_levels = gamma_levels

            except Exception as e:
                st.error(f"❌ Error: {e}")
                live_spot = get_live_spot_price(symbol, 'nselib')
                df, spot  = generate_sample_data(symbol, live_spot, expiry_date)
                if df is not None:
                    st.session_state.options_df  = df
                    st.session_state.spot_price  = spot
                    st.session_state.data_loaded = True
                    st.session_state.last_update = datetime.now()

    # ── Status ───────────────────────────────────────────────────────────────
    if st.session_state.data_loaded and st.session_state.last_update:
        st.markdown("---")
        st.markdown('<span class="live-indicator"></span> **Live Data**', unsafe_allow_html=True)
        st.caption(f"🕐 Updated: {st.session_state.last_update.strftime('%H:%M:%S')}")
        if st.session_state.spot_price:
            st.caption(f"📊 {symbol} Spot: ₹{st.session_state.spot_price:,.2f}")
        st.caption(f"📅 Expiry: {st.session_state.selected_expiry}")
        st.caption(f"📦 Lot Size: {st.session_state.lot_size}")
        try:
            mkt = get_market_status()
            emoji = "🟢" if "Open" in mkt.get('market_state', '') else "🔴"
            st.caption(f"{emoji} {mkt.get('market_state', 'Unknown')}")
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------
if st.session_state.data_loaded and st.session_state.gex_df is not None:
    df           = st.session_state.options_df
    spot_price   = st.session_state.spot_price
    gex_df       = st.session_state.gex_df
    gamma_levels = st.session_state.gamma_levels
    lot_size     = st.session_state.lot_size or current_lot_size

    # ── Top metrics ──────────────────────────────────────────────────────────
    st.markdown("---")
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    pcr        = gamma_levels.get('pcr', 1.0)
    max_pain   = gamma_levels.get('max_pain', spot_price)
    gamma_flip = gamma_levels.get('gamma_flip', spot_price)
    net_gex    = gamma_levels.get('total_gex', 0)
    max_call_oi_strike = gamma_levels.get('max_call_oi_strike', 0)
    max_put_oi_strike  = gamma_levels.get('max_put_oi_strike', 0)

    with c1:
        st.metric("💰 Spot Price", f"₹{spot_price:,.2f}")
    with c2:
        pcr_sig = "🐻" if pcr > 1.2 else "🐂" if pcr < 0.8 else "➡️"
        st.metric(f"{pcr_sig} PCR", f"{pcr:.2f}")
    with c3:
        st.metric("🎯 Max Pain", f"₹{max_pain:,.0f}", delta=f"{max_pain - spot_price:+.0f}")
    with c4:
        st.metric("🔄 Gamma Flip", f"₹{gamma_flip:,.0f}", delta=f"{gamma_flip - spot_price:+.0f}")
    with c5:
        regime = "🟢 Positive" if net_gex > 0 else "🔴 Negative"
        st.metric("📊 GEX Regime", regime)
    with c6:
        st.metric("💹 Net GEX", format_number(net_gex))

    # ── Secondary metrics ────────────────────────────────────────────────────
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("📈 Total Call OI", f"{gamma_levels.get('total_call_oi', 0):,.0f}")
    with c2:
        st.metric("📉 Total Put OI",  f"{gamma_levels.get('total_put_oi', 0):,.0f}")
    with c3:
        st.metric("🚧 Max Call OI Strike", f"₹{max_call_oi_strike:,.0f}")
    with c4:
        st.metric("🛡️ Max Put OI Strike",  f"₹{max_put_oi_strike:,.0f}")

    # ── Lot-size context row ─────────────────────────────────────────────────
    st.info(
        f"📦 **{symbol}** · Lot Size: **{lot_size}** · "
        f"Expiry: **{st.session_state.selected_expiry}** · "
        f"Spot: **₹{spot_price:,.2f}**",
    )

    # ── Tabs ─────────────────────────────────────────────────────────────────
    st.markdown("---")
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 GEX Analysis", "📈 OI & Volume", "🎲 Greeks Suite",
        "🎯 Trade Signals", "📋 Option Chain", "ℹ️ Guide",
    ])

    # ── Tab 1 ────────────────────────────────────────────────────────────────
    with tab1:
        st.subheader("Gamma Exposure Profile")
        st.plotly_chart(plot_gex_profile(gex_df, spot_price, gamma_levels),
                        use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🎯 Key Support & Resistance")
            support    = gamma_levels.get('support', 'N/A')
            resistance = gamma_levels.get('resistance', 'N/A')
            atm        = get_atm_strike(spot_price)
            st.write(f"**Support (Max +GEX):** ₹{support:,}"
                     if isinstance(support, (int, float)) else f"**Support:** {support}")
            st.write(f"**Resistance (Max -GEX):** ₹{resistance:,}"
                     if isinstance(resistance, (int, float)) else f"**Resistance:** {resistance}")
            st.write(f"**ATM Strike:** ₹{atm:,}")
            st.write(f"**Gamma Flip:** ₹{gamma_flip:,.0f}")
            st.write(f"**Max Pain:** ₹{max_pain:,.0f}")
        with c2:
            st.markdown("##### 📊 GEX Summary")
            st.write(f"**Total Call GEX:** {format_number(gex_df['call_gex'].sum())}")
            st.write(f"**Total Put GEX:**  {format_number(gex_df['put_gex'].sum())}")
            st.write(f"**Net GEX:**        {format_number(net_gex)}")
            st.write(f"**GEX Above Spot:** {format_number(gamma_levels.get('net_gex_above_spot', 0))}")
            st.write(f"**GEX Below Spot:** {format_number(gamma_levels.get('net_gex_below_spot', 0))}")

        st.markdown("---")
        st.subheader("Net GEX vs Spot Movement")
        st.plotly_chart(plot_spot_gex_levels(gex_df, spot_price, gamma_levels, 500),
                        use_container_width=True)

    # ── Tab 2 ────────────────────────────────────────────────────────────────
    with tab2:
        st.subheader("Open Interest & Volume Analysis")
        st.plotly_chart(plot_oi_analysis(gex_df, spot_price), use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 📊 PCR Analysis")
            st.plotly_chart(plot_pcr_analysis(gex_df), use_container_width=True)
        with c2:
            st.markdown("##### 📈 Volatility Smile")
            st.plotly_chart(plot_iv_smile(gex_df), use_container_width=True)

        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        total_call_vol = gamma_levels.get('total_call_volume', 0)
        total_put_vol  = gamma_levels.get('total_put_volume', 0)
        vol_pcr = total_put_vol / total_call_vol if total_call_vol > 0 else 0
        with c1: st.metric("📊 Total Call Volume", f"{total_call_vol:,.0f}")
        with c2: st.metric("📊 Total Put Volume",  f"{total_put_vol:,.0f}")
        with c3: st.metric("📊 Volume PCR",        f"{vol_pcr:.2f}")

    # ── Tab 3 ────────────────────────────────────────────────────────────────
    with tab3:
        st.subheader("Greeks Analysis")
        greek_selector = st.selectbox("Select Greek:", ["Gamma", "Delta", "Vega", "Theta", "Rho"])
        st.plotly_chart(plot_greeks_heatmap(gex_df, greek_selector.lower()),
                        use_container_width=True)

        st.markdown("---")
        st.subheader("ATM Greeks Summary")
        atm_idx = (gex_df['strike'] - spot_price).abs().idxmin()
        atm_row = gex_df.loc[atm_idx]

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 📈 Call Greeks (ATM)")
            st.write(f"**Delta:** {atm_row['call_delta']:.4f}")
            st.write(f"**Gamma:** {atm_row['call_gamma']:.6f}")
            st.write(f"**Vega:**  {atm_row['call_vega']:.4f} (per 1% IV)")
            st.write(f"**Theta:** ₹{atm_row['call_theta']:.2f}/day")
            st.write(f"**Rho:**   {atm_row['call_rho']:.4f} (per 1% rate)")
            st.write(f"**Theo Price:** ₹{atm_row['call_theo']:.2f}")
            st.write(f"**Market LTP:** ₹{atm_row['call_ltp']:.2f}")
        with c2:
            st.markdown("##### 📉 Put Greeks (ATM)")
            st.write(f"**Delta:** {atm_row['put_delta']:.4f}")
            st.write(f"**Gamma:** {atm_row['put_gamma']:.6f}")
            st.write(f"**Vega:**  {atm_row['put_vega']:.4f} (per 1% IV)")
            st.write(f"**Theta:** ₹{atm_row['put_theta']:.2f}/day")
            st.write(f"**Rho:**   {atm_row['put_rho']:.4f} (per 1% rate)")
            st.write(f"**Theo Price:** ₹{atm_row['put_theo']:.2f}")
            st.write(f"**Market LTP:** ₹{atm_row['put_ltp']:.2f}")

        st.markdown("---")
        st.subheader("Portfolio Greeks Exposure")
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("Delta Exposure", format_number(gex_df['total_dex'].sum()))
        with c2: st.metric("Gamma Exposure", format_number(gex_df['total_gex'].sum()))
        with c3: st.metric("Vega Exposure",  f"{gex_df['total_vex'].sum():,.0f}")
        with c4: st.metric("Theta Decay/Day", format_number(gex_df['total_tex'].sum()))

    # ── Tab 4 ────────────────────────────────────────────────────────────────
    with tab4:
        st.subheader("🎯 Intelligent Trade Recommendations")
        recommendations = generate_trade_recommendations(gex_df, spot_price, gamma_levels)

        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                emoji = {'HIGH': '🔴', 'MEDIUM': '🟡', 'INFO': '🔵'}.get(rec['confidence'], '⚪')
                with st.expander(f"{emoji} {rec['signal']} — {rec['strategy']}", expanded=(i <= 3)):
                    st.markdown(f"**Confidence:** `{rec['confidence']}`")
                    st.markdown(f"**Analysis:** {rec['reasoning']}")
                    st.markdown(f"**Action:** {rec['action']}")
        else:
            st.info("No strong signals detected. Market appears balanced.")

        st.markdown("---")
        st.subheader("📊 Risk Assessment")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### Market Conditions")
            if net_gex > 0:
                st.success("✅ Positive Gamma: Lower volatility, range-bound")
            else:
                st.warning("⚠️ Negative Gamma: Higher volatility, trending")
            if pcr > 1.2:
                st.error("🐻 High PCR: Bearish sentiment")
            elif pcr < 0.8:
                st.error("🐂 Low PCR: Bullish sentiment")
            else:
                st.info("➡️ Neutral PCR: Balanced")
        with c2:
            st.markdown("##### Key Levels")
            st.write(f"**Max Pain:** ₹{max_pain:,.0f}")
            st.write(f"**Gamma Flip:** ₹{gamma_flip:,.0f}")
            st.write(f"**Call Wall:** ₹{max_call_oi_strike:,.0f}")
            st.write(f"**Put Wall:** ₹{max_put_oi_strike:,.0f}")

    # ── Tab 5 ────────────────────────────────────────────────────────────────
    with tab5:
        st.subheader("Complete Options Chain with Greeks")

        display_df = gex_df[[
            'strike', 'call_oi', 'call_volume', 'call_ltp', 'call_iv',
            'call_delta', 'call_gamma', 'call_vega', 'call_theta',
            'put_theta', 'put_vega', 'put_gamma', 'put_delta',
            'put_iv', 'put_ltp', 'put_volume', 'put_oi',
        ]].copy()
        display_df.columns = [
            'Strike', 'Call OI', 'Call Vol', 'Call LTP', 'Call IV%',
            'Call Δ', 'Call Γ', 'Call ν', 'Call Θ',
            'Put Θ', 'Put ν', 'Put Γ', 'Put Δ',
            'Put IV%', 'Put LTP', 'Put Vol', 'Put OI',
        ]

        atm_strikes = gex_df.iloc[(gex_df['strike'] - spot_price).abs().argsort()[:3]]['strike'].values

        def highlight_atm(row):
            if row['Strike'] in atm_strikes:
                return ['background-color: rgba(255,165,0,0.3)'] * len(row)
            return [''] * len(row)

        st.dataframe(
            display_df.style.apply(highlight_atm, axis=1).format({
                'Call OI': '{:,.0f}', 'Put OI': '{:,.0f}',
                'Call Vol': '{:,.0f}', 'Put Vol': '{:,.0f}',
                'Call LTP': '{:.2f}',  'Put LTP': '{:.2f}',
                'Call IV%': '{:.2f}',  'Put IV%': '{:.2f}',
                'Call Δ': '{:.4f}',    'Put Δ': '{:.4f}',
                'Call Γ': '{:.6f}',    'Put Γ': '{:.6f}',
                'Call ν': '{:.4f}',    'Put ν': '{:.4f}',
                'Call Θ': '{:.2f}',    'Put Θ': '{:.2f}',
            }),
            height=500,
            use_container_width=True,
        )

        csv = gex_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Complete Data (CSV)",
            data=csv,
            file_name=(f"gex_terminal_{symbol}_{st.session_state.selected_expiry}_"
                       f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"),
            mime="text/csv",
        )

    # ── Tab 6 ────────────────────────────────────────────────────────────────
    with tab6:
        st.subheader("ℹ️ Understanding GEX Terminal")
        st.markdown("""
## What is Gamma Exposure (GEX)?

**Gamma Exposure** shows how much dealers need to buy or sell the underlying as prices move to stay delta-neutral.

### Expiry Calendar (NSE rules)

| Index | Weekly Expiry Day |
|-------|-------------------|
| NIFTY | Thursday |
| BANKNIFTY | Wednesday |
| FINNIFTY | Tuesday |
| MIDCPNIFTY | Monday |

When **Kite Connect is authenticated**, expiry dates are fetched directly from NFO instruments — so holiday substitutions and special expiries are captured automatically.

### Lot Sizes

| Index | Lot Size (May 2025) |
|-------|---------------------|
| NIFTY | 75 |
| BANKNIFTY | 35 |
| FINNIFTY | 65 |
| MIDCPNIFTY | 120 |

Lot sizes are fetched from Kite instruments when connected (dynamic), otherwise the table above is used as a fallback.

### IV Calculation

Kite does not provide Implied Volatility directly. This terminal **back-solves IV from the market LTP** using Brent's root-finding method on the Black-Scholes formula — the same approach used by Bloomberg terminals.

### GEX Regimes

**🟢 Positive Gamma** – Dealers sell rallies / buy dips → stabilising, range-bound markets → prefer credit spreads, iron condors.

**🔴 Negative Gamma** – Dealers buy rallies / sell dips → destabilising, trending markets → prefer straddles, directional trades.

### Disclaimer
⚠️ Educational purposes only. Not financial advice. Always manage risk.
        """)

# ---------------------------------------------------------------------------
# Welcome screen
# ---------------------------------------------------------------------------
else:
    st.info("👈 Configure your terminal in the sidebar and click **Fetch Data** to begin")

    st.markdown("""
## Welcome to Professional GEX Terminal 🚀

**Supported Indices:** NIFTY · BANKNIFTY · FINNIFTY · MIDCPNIFTY

**Data Sources:** NSE Live (nselib) · Kite Connect (live + dynamic lot/expiry) · Sample Data

**Quick Start:**
1. Select data source (NSE Live / Kite / Sample)
2. Connect Kite for dynamic lot sizes and actual expiry dates
3. Choose index + expiry → click **Fetch Data**
4. Explore GEX, Greeks, OI, and trade signals
    """)

    c1, c2 = st.columns(2)
    for col, sym, grad in [
        (c1, 'NIFTY',     'linear-gradient(135deg,#667eea,#764ba2)'),
        (c2, 'BANKNIFTY', 'linear-gradient(135deg,#f093fb,#f5576c)'),
    ]:
        with col:
            with st.spinner(f"Fetching {sym}..."):
                try:
                    q = get_index_quote(sym)
                    if q:
                        arrow = "🟢" if q['change'] >= 0 else "🔴"
                        name  = "NIFTY 50" if sym == "NIFTY" else "BANK NIFTY"
                        st.markdown(f"""
                        <div style='background:{grad};padding:2rem;border-radius:15px;
                                    color:white;text-align:center;'>
                            <h3 style='margin:0;color:white;'>{name}</h3>
                            <h1 style='margin:1rem 0;color:white;font-size:3rem;'>
                                ₹{q['last']:,.2f}</h1>
                            <p style='margin:0;font-size:1.5rem;'>
                                {arrow} {q['change']:+.2f}%</p>
                            <hr style='margin:1rem 0;border-color:rgba(255,255,255,0.3);'>
                            <div style='display:flex;justify-content:space-around;'>
                                <div><small>Open</small><br><b>₹{q['open']:,.2f}</b></div>
                                <div><small>High</small><br><b>₹{q['high']:,.2f}</b></div>
                                <div><small>Low</small><br><b>₹{q['low']:,.2f}</b></div>
                            </div>
                        </div>""", unsafe_allow_html=True)
                except Exception:
                    st.error(f"Unable to fetch {sym} data")

    try:
        mkt = get_market_status()
        emoji = "🟢" if "Open" in mkt.get('market_state', '') else "🔴"
        st.caption(f"{emoji} Market: {mkt.get('market_state','Unknown')} | {mkt.get('timestamp','')}")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("""
<div style='text-align:center;color:#666;padding:1.5rem;'>
    <p style='font-size:1.1rem;'><b>Professional GEX Terminal v2.1</b></p>
    <p>Advanced Options Analytics • Real-Time Greeks • Intelligent Signals</p>
    <p style='font-size:0.85rem;'>
        Data: NSE India · Kite Connect · nselib<br>
        Lot sizes & expiries fetched dynamically from Kite when connected
    </p>
    <p style='font-size:0.75rem;color:#999;'>
        ⚠️ For educational purposes only. Not financial advice. Trade at your own risk.
    </p>
</div>
""", unsafe_allow_html=True)
