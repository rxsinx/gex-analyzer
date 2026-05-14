"""
Professional GEX Terminal v3.1
Kite Connect v3 · NSE Live · Full Greeks · VIX + 1-Hr Chart · Dynamic S/R

Debug fixes in this version
----------------------------
* KiteError / KiteAuthError / KiteDataError displayed to user (not swallowed)
* set_access_token() returns (bool, str) – handled correctly
* All kite_mgr calls wrapped in try/except with clear error messages
* 🔍 Debug panel runs step-by-step test_connection() and shows each result
* chart_analysis.py correctly placed in modules/
* Charts tab: 1-hr index candlestick + India VIX + dynamic S/R lines
"""

import streamlit as st
import pandas as pd
import pytz  # <--- Add this line
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

from modules.data_fetcher import (
    fetch_option_chain, generate_sample_data,
    get_live_spot_price, get_index_quote, get_market_status,
)
from modules.gex_calculator import calculate_gex, find_gamma_levels
from modules.visualizations import (
    plot_gex_profile, plot_spot_gex_levels, plot_oi_analysis,
    plot_pcr_analysis, plot_iv_smile, plot_greeks_heatmap,
    create_summary_metrics, plot_index_vix_chart, build_levels_table,
)
from modules.utils import (
    get_next_expiry_for_symbol, get_expiries_for_symbol,
    get_atm_strike, format_number, filter_strikes,
    get_lot_size, get_strike_interval, has_weekly_expiry,
    calculate_time_to_expiry,
)
from modules.chart_analysis import analyse_levels
from modules.trade_recommendations import generate_trade_recommendations
from modules.kite_connector import (
    KiteManager, KiteError, KiteAuthError, KiteDataError,
)

try:
    import config as _cfg
    KITE_API_KEY         = _cfg.KITE_API_KEY
    KITE_API_SECRET      = _cfg.KITE_API_SECRET
    SPOT_REFRESH         = _cfg.SPOT_REFRESH_INTERVAL
    CHAIN_REFRESH        = _cfg.AUTO_REFRESH_INTERVAL
    RFR_DEFAULT          = _cfg.DEFAULT_RISK_FREE_RATE
    STRIKE_RANGE_DEFAULT = _cfg.DEFAULT_STRIKE_RANGE_PCT
except Exception:
    KITE_API_KEY = KITE_API_SECRET = ""
    SPOT_REFRESH, CHAIN_REFRESH    = 5, 15
    RFR_DEFAULT                    = 0.07
    STRIKE_RANGE_DEFAULT           = 10


# ── page ─────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="GEX Terminal", page_icon="📊",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
/* remove Streamlit default top padding */
.block-container{padding-top:0.4rem !important;padding-bottom:0.2rem !important}
/* compact header */
.main-header{font-size:1.6rem;font-weight:bold;
  background:linear-gradient(90deg,#1f77b4,#ff7f0e);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  text-align:center;margin:0;padding:0;line-height:1.2}
.sub-header{text-align:center;color:#888;font-size:0.76rem;
  margin:0 0 0.2rem 0;padding:0}
/* thin dividers */
hr{margin:0.2rem 0 !important;border-color:rgba(49,51,63,0.25) !important}
/* smaller metric values */
[data-testid="stMetricValue"]{font-size:1.0rem !important;line-height:1.25 !important}
[data-testid="stMetricLabel"]{font-size:0.68rem !important;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-testid="stMetricDelta"]{font-size:0.62rem !important}
div[data-testid="metric-container"]{padding:0.1rem 0.35rem !important}
/* compact alerts/info */
.stAlert{padding:0.25rem 0.6rem !important;font-size:0.76rem !important}
/* live dot */
.live-dot{display:inline-block;width:8px;height:8px;background:#22c55e;
  border-radius:50%;margin-right:4px;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
/* tabs */
.stTabs [data-baseweb="tab"]{height:34px;background:#f0f2f6;
  border-radius:5px 5px 0 0;padding:4px 13px;font-weight:600;font-size:0.82rem}
.stTabs [aria-selected="true"]{
  background:linear-gradient(135deg,#667eea,#764ba2);color:white}
/* tighten column gaps */
[data-testid="stHorizontalBlock"]{gap:0.4rem !important}
</style>""", unsafe_allow_html=True)

# ── session state ─────────────────────────────────────────────────────────────
for k, v in {
    "data_loaded": False, "options_df": None, "spot_price": None,
    "spot_ohlc": None, "last_update": None, "last_spot_update": None,
    "gex_df": None, "gamma_levels": None,
    "kite_authenticated": False, "kite_manager": None,
    "lot_size": None, "strike_interval": None,
    "selected_expiry": None, "selected_symbol": "NIFTY",
    "chart_index_df": None, "chart_vix_df": None, "chart_levels": None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

st.markdown('<p class="main-header">📊 Professional GEX Terminal</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Kite Connect v3 · Real-Time Greeks · VIX Chart · Dynamic S/R</p>',
            unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ Configuration")

    # ── Data source ───────────────────────────────────────────────────────────
    st.subheader("📡 Data Source")
    data_source = "Kite Connect"

    # ── Kite auth ─────────────────────────────────────────────────────────────
    if data_source == "Kite Connect":
        st.markdown("---")
        st.subheader("🔐 Kite Authentication")

        if not st.session_state.kite_authenticated:
            api_key    = st.text_input("API Key",    value=KITE_API_KEY,    type="password")
            api_secret = st.text_input("API Secret", value=KITE_API_SECRET, type="password")

            if st.button("🔗 Connect to Kite", type="primary"):
                if api_key and api_secret:
                    km  = KiteManager(api_key, api_secret)
                    url = km.get_login_url()
                    st.info(f"**Step 1:** [Login to Kite]({url})")
                    st.info("**Step 2:** Copy the `request_token` from the redirect URL")
                else:
                    st.error("Enter API Key and Secret first.")

            req_token = st.text_input("Paste Request Token here:")
            if req_token and st.button("✅ Generate Session", type="primary"):
                if api_key and api_secret:
                    km_temp = KiteManager(api_key, api_secret)
                    ok, msg = km_temp.set_access_token(req_token)
                    if ok:
                        st.session_state.kite_manager       = km_temp
                        st.session_state.kite_authenticated = True
                        st.success(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ Authentication failed: {msg}")
                else:
                    st.error("Enter API Key and Secret first.")
        else:
            st.success("✅ Kite Connected")
            col_r, col_d = st.columns(2)
            with col_d:
                if st.button("Disconnect", use_container_width=True):
                    st.session_state.kite_authenticated = False
                    st.session_state.kite_manager       = None
                    st.rerun()

            # ── 🔍 Debug panel ──────────────────────────────────────────────
            with st.expander("🔍 Debug Connection", expanded=False):
                st.caption("Tests each Kite API step independently")
                debug_sym = st.selectbox("Test symbol:", ["NIFTY","BANKNIFTY","FINNIFTY"],
                                          key="debug_sym")
                if st.button("▶ Run Diagnostics", key="run_diag"):
                    km_d = st.session_state.kite_manager
                    if km_d:
                        with st.spinner("Running tests…"):
                            results = km_d.test_connection(debug_sym)
                        for step, info in results.items():
                            icon = "✅" if info["ok"] else "❌"
                            if info["ok"]:
                                st.success(f"{icon} **{info['label']}** — {info['msg']}")
                            else:
                                st.error(f"{icon} **{info['label']}** — {info['msg']}")
                        if not all(v["ok"] for v in results.values()):
                            st.warning(
                                "**Common fixes:**\n"
                                "- Token expires at 6 AM daily → re-authenticate\n"
                                "- Use correct redirect URL in Kite app settings\n"
                                "- API key must have F&O data permissions\n"
                                "- Instruments load takes ~30 s on first call"
                            )

                if st.button("🗑 Clear Instrument Cache", key="clear_cache"):
                    if st.session_state.kite_manager:
                        st.session_state.kite_manager.invalidate_cache()
                        st.success("Cache cleared – next fetch will reload from Kite.")

    st.markdown("---")
    kite_mgr = (st.session_state.kite_manager
                if data_source == "Kite Connect" else None)

    # ── Symbol ────────────────────────────────────────────────────────────────
    symbol = st.selectbox("📈 Index", ["NIFTY","BANKNIFTY","FINNIFTY","MIDCPNIFTY"])
    st.session_state.selected_symbol = symbol

    # ── Lot size / strike interval ────────────────────────────────────────────
    try:
        lot_size        = get_lot_size(symbol, kite_mgr)
        strike_interval = get_strike_interval(symbol, None, kite_mgr)
    except KiteError:
        lot_size        = get_lot_size(symbol, None)
        strike_interval = get_strike_interval(symbol, None, None)

    st.session_state.lot_size        = lot_size
    st.session_state.strike_interval = strike_interval
    src_lbl = "🔗 Kite" if kite_mgr else "📋 estimate"
    ca, cb  = st.columns(2)
    ca.metric("📦 Lot Size",        str(lot_size),              help=src_lbl)
    cb.metric("📏 Interval",        f"₹{strike_interval:.0f}", help=src_lbl)

    # ── Expiry type ───────────────────────────────────────────────────────────
    st.markdown("---")
    try:
        sym_has_weekly = has_weekly_expiry(symbol, kite_mgr)
    except KiteError:
        sym_has_weekly = has_weekly_expiry(symbol, None)

    if sym_has_weekly:
        et_label   = st.radio("📅 Expiry Type", ["Weekly","Monthly"])
        expiry_type = "weekly" if et_label == "Weekly" else "monthly"
    else:
        st.info(f"📅 {symbol}: Monthly only (no weekly on NSE)")
        expiry_type = "monthly"

    # ── Expiry selector ───────────────────────────────────────────────────────
    try:
        available_expiries = get_expiries_for_symbol(symbol, kite_mgr, expiry_type)
    except KiteError:
        available_expiries = get_expiries_for_symbol(symbol, None, expiry_type)

    if not available_expiries:
        available_expiries = [get_next_expiry_for_symbol(symbol, expiry_type)]

    expiry_date = st.selectbox(
        "Select Expiry", available_expiries, index=0,
        help="From Kite instruments" if kite_mgr else "Computed from NSE rules")
    st.caption(f"Source: {'🔗 Kite' if kite_mgr else '📋 NSE calendar'}")
    st.session_state.selected_expiry = expiry_date

    # ── Parameters ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📍 Parameters")
    strike_range   = st.slider("Strike Range (%)", 5, 25, STRIKE_RANGE_DEFAULT, 1)
    risk_free_rate = st.number_input("Risk-Free Rate (%)", 0.0, 15.0,
                                      round(RFR_DEFAULT*100,1), 0.1) / 100

    # ── Spot refresh ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("💹 Spot Price")
    sc1, sc2 = st.columns(2)

    with sc1:
        if st.button("🔄 Refresh Spot", use_container_width=True):
            with st.spinner("Fetching LTP…"):
                try:
                    if kite_mgr:
                        new_spot = kite_mgr.get_spot_ltp(symbol)
                        ohlc     = kite_mgr.get_spot_ohlc(symbol)
                    else:
                        new_spot = get_live_spot_price(symbol, "nselib")
                        ohlc     = None

                    if new_spot:
                        st.session_state.spot_price       = new_spot
                        st.session_state.spot_ohlc        = ohlc
                        st.session_state.last_spot_update = datetime.now()
                        if (st.session_state.data_loaded
                                and st.session_state.options_df is not None):
                            df_f = filter_strikes(st.session_state.options_df,
                                                  new_spot, strike_range)
                            gx   = calculate_gex(df_f, new_spot, expiry_date,
                                                  risk_free_rate)
                            st.session_state.gex_df       = gx
                            st.session_state.gamma_levels = find_gamma_levels(gx, new_spot)
                        st.success(f"₹{new_spot:,.2f}")
                    else:
                        st.warning("Spot not available (market closed?)")

                except KiteAuthError as e:
                    st.error(f"🔐 Session expired: {e}\n\nRe-authenticate in the sidebar.")
                except KiteError as e:
                    st.error(f"Kite error: {e}")
                except Exception as e:
                    st.error(f"Error: {e}")

    with sc2:
        enable_spot_refresh = st.checkbox("Auto", value=False,
                                           help="Auto-refresh spot every few seconds")
    if enable_spot_refresh and kite_mgr:
        st_autorefresh(interval=SPOT_REFRESH*1000, limit=None, key="spot_ar")

    # ── Option chain fetch ────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🔄 Option Chain")
    enable_chain_ar = st.checkbox("Auto-refresh chain", value=False)
    if enable_chain_ar:
        ci = st.slider("Interval (s)", 10, 120, CHAIN_REFRESH, 5)
        st_autorefresh(interval=ci*1000, limit=None, key="chain_ar")

    if st.button("📥 Fetch Option Chain", type="primary", use_container_width=True):
        src = ("kite"   if data_source == "Kite Connect" else
               "nselib" if data_source == "NSE Live (nselib)" else "sample")
        with st.spinner(f"Fetching {symbol} chain for {expiry_date}…"):
            df, spot = None, None
            fetch_ok = False

            # ── Kite ─────────────────────────────────────────────────────────
            if src == "kite":
                if not kite_mgr:
                    st.error("Kite not connected. Select Kite Connect and authenticate.")
                else:
                    try:
                        df, spot = kite_mgr.get_option_chain(
                            symbol, expiry_date, risk_free_rate)
                        fetch_ok = True
                        st.success(f"✅ {len(df):,} contracts · spot ₹{spot:,.2f}")
                    except KiteAuthError as e:
                        st.error(
                            f"🔐 **Session expired or invalid:**\n{e}\n\n"
                            "**Fix:** Disconnect and re-authenticate. "
                            "Kite tokens reset at 6 AM daily.")
                    except KiteDataError as e:
                        st.error(f"📊 **Data error:**\n{e}")
                        st.info("Run **🔍 Debug Connection** in the sidebar to diagnose.")
                    except KiteError as e:
                        st.error(f"Kite error: {e}")
                    except Exception as e:
                        st.error(f"Unexpected error: {e}")

            # ── NSE ──────────────────────────────────────────────────────────
            elif src == "nselib":
                try:
                    df, spot = fetch_option_chain(
                        symbol, expiry_date, "nselib", None, risk_free_rate)
                    fetch_ok = df is not None and not df.empty and spot
                    if not fetch_ok:
                        st.warning("NSE live fetch returned no data (rate-limited or closed).")
                except Exception as e:
                    st.error(f"NSE error: {e}")

            # ── Sample ───────────────────────────────────────────────────────
            else:
                try:
                    live_spot = get_live_spot_price(symbol, "nselib")
                    df, spot  = generate_sample_data(symbol, live_spot,
                                                      expiry_date, kite_mgr)
                    fetch_ok  = True
                    st.info(f"📊 Sample data · spot ₹{spot:,.2f}")
                except Exception as e:
                    st.error(f"Sample data error: {e}")

            # Fallback to sample if live failed
            if not fetch_ok and src != "sample" and df is None:
                st.warning("⚠️ Falling back to sample data.")
                try:
                    live_spot = get_live_spot_price(symbol, "nselib")
                    df, spot  = generate_sample_data(symbol, live_spot,
                                                      expiry_date, kite_mgr)
                except Exception as e:
                    st.error(f"Sample fallback failed: {e}")

            # Store + calculate
            if df is not None and not df.empty and spot:
                df_f = filter_strikes(df, spot, strike_range)
                if df_f.empty:
                    st.warning(f"No strikes within ±{strike_range}% – widening to ±15%.")
                    df_f = filter_strikes(df, spot, 15)
                try:
                    gx   = calculate_gex(df_f, spot, expiry_date, risk_free_rate)
                    gl   = find_gamma_levels(gx, spot)
                    st.session_state.update({
                        "options_df": df, "spot_price": spot,
                        "gex_df": gx, "gamma_levels": gl,
                        "data_loaded": True, "last_update": datetime.now(),
                        "last_spot_update": datetime.now(),
                        "lot_size":       get_lot_size(symbol, kite_mgr if fetch_ok else None),
                        "strike_interval":get_strike_interval(symbol, expiry_date,
                                                               kite_mgr if fetch_ok else None),
                    })
                except Exception as e:
                    st.error(f"GEX calculation error: {e}")

    # ── Status ────────────────────────────────────────────────────────────────
    if st.session_state.data_loaded:
        st.markdown("---")
        st.markdown(f'<span class="live-dot"></span>**{symbol}**', unsafe_allow_html=True)
        if st.session_state.spot_price:
            st.metric("Spot", f"₹{st.session_state.spot_price:,.2f}")
        st.caption(f"📅 {st.session_state.selected_expiry}")
        st.caption(f"📦 Lot {st.session_state.lot_size} · 📏 ₹{st.session_state.strike_interval:.0f}")
        if st.session_state.last_update:
            ist_chain = st.session_state.last_update.astimezone(pytz.timezone('Asia/Kolkata'))
            st.caption(f"🕐 Chain: {ist_chain.strftime('%H:%M:%S')}")
        if st.session_state.last_spot_update:
            ist_spot = st.session_state.last_spot_update.astimezone(pytz.timezone('Asia/Kolkata'))
            st.caption(f"💹 Spot: {ist_spot.strftime('%H:%M:%S')}")
        
        try:
            mkt = get_market_status()
            e   = "🟢" if "Open" in mkt.get("market_state","") else "🔴"
            st.caption(f"{e} {mkt['market_state']}")
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN CONTENT
# ═══════════════════════════════════════════════════════════════════════════════
if st.session_state.data_loaded and st.session_state.gex_df is not None:
    st.markdown("---")   # single thin line below header
    spot_price   = st.session_state.spot_price
    gex_df       = st.session_state.gex_df
    gamma_levels = st.session_state.gamma_levels
    lot_size     = st.session_state.lot_size
    si           = st.session_state.strike_interval

    pcr               = gamma_levels.get("pcr", 1.0)
    max_pain          = gamma_levels.get("max_pain", spot_price)
    gamma_flip        = gamma_levels.get("gamma_flip", spot_price)
    net_gex           = gamma_levels.get("total_gex", 0)
    max_call_oi_strike= gamma_levels.get("max_call_oi_strike", spot_price)
    max_put_oi_strike = gamma_levels.get("max_put_oi_strike", spot_price)

    # ── All metrics in one compact block (no dividers between rows) ───────────
    ohlc = st.session_state.spot_ohlc or {}

    # Row 1: OHLC + PCR + Max Pain + Gamma Flip + GEX Regime in one 9-col row
    m1,m2,m3,m4,m5,m6,m7,m8,m9 = st.columns(9)
    m1.metric("💰 Spot",        f"₹{spot_price:,.0f}")
    m2.metric("Open",           f"₹{ohlc['open']:,.0f}"  if ohlc else "—")
    m3.metric("High",           f"₹{ohlc['high']:,.0f}"  if ohlc else "—")
    m4.metric("Low",            f"₹{ohlc['low']:,.0f}"   if ohlc else "—")
    m5.metric("Prev",           f"₹{ohlc['close']:,.0f}" if ohlc else "—")
    pcr_icon = "🐻" if pcr>1.2 else "🐂" if pcr<0.8 else "➡️"
    m6.metric(f"{pcr_icon} PCR",f"{pcr:.3f}")
    m7.metric("🎯 Max Pain",    f"₹{max_pain:,.0f}",  delta=f"{max_pain -spot_price:+.0f}")
    m8.metric("🔄 Gamma Flip",  f"₹{gamma_flip:,.0f}",delta=f"{gamma_flip-spot_price:+.0f}")
    m9.metric("📊 Regime",      "🟢 +GEX" if net_gex>0 else "🔴 -GEX")

    # Row 2: Net GEX + Lot + Call OI + Put OI + Max Call + Max Put + Symbol info
    n1,n2,n3,n4,n5,n6,n7,n8 = st.columns(8)
    n1.metric("💹 Net GEX",          format_number(net_gex))
    n2.metric("📦 Lot / Interval",   f"{lot_size} / ₹{si:.0f}")
    n3.metric("📈 Call OI",          f"{gamma_levels.get('total_call_oi',0)/1e5:.1f}L")
    n4.metric("📉 Put OI",           f"{gamma_levels.get('total_put_oi',0)/1e5:.1f}L")
    n5.metric("🚧 Call Wall",        f"₹{max_call_oi_strike:,.0f}")
    n6.metric("🛡️ Put Wall",         f"₹{max_put_oi_strike:,.0f}")
    n7.metric("📅 Expiry",           st.session_state.selected_expiry or "—")
    n8.metric("🕐 Updated",
              st.session_state.last_update.astimezone(pytz.timezone('Asia/Kolkata')).strftime("%H:%M:%S") 
              if st.session_state.last_update else "—")
    
    
    # ── Tabs ──────────────────────────────────────────────────────────────────
    st.markdown("---")
    tab1,tab2,tab3,tab4,tab5,tab6,tab7 = st.tabs([
        "📊 GEX","📈 OI & Volume","🎲 Greeks",
        "📉 Charts","🎯 Signals","📋 Chain","ℹ️ Guide",
    ])

    # ── Tab 1: GEX ────────────────────────────────────────────────────────────
    with tab1:
        st.subheader("Gamma Exposure Profile")
        st.plotly_chart(plot_gex_profile(gex_df, spot_price, gamma_levels),
                        use_container_width=True)
        c1,c2 = st.columns(2)
        with c1:
            st.markdown("##### Key Levels")
            atm        = get_atm_strike(spot_price, si)
            support    = gamma_levels.get("support","N/A")
            resistance = gamma_levels.get("resistance","N/A")
            st.write(f"**ATM Strike:** ₹{atm:,.0f}")
            st.write(f"**Support (max +GEX):** " +
                     (f"₹{support:,.0f}" if isinstance(support,(int,float)) else str(support)))
            st.write(f"**Resistance (max –GEX):** " +
                     (f"₹{resistance:,.0f}" if isinstance(resistance,(int,float)) else str(resistance)))
            st.write(f"**Gamma Flip:** ₹{gamma_flip:,.0f}")
            st.write(f"**Max Pain:** ₹{max_pain:,.0f}")
        with c2:
            st.markdown("##### GEX Summary")
            st.write(f"**Call GEX:** {format_number(gex_df['call_gex'].sum())}")
            st.write(f"**Put GEX:**  {format_number(gex_df['put_gex'].sum())}")
            st.write(f"**Net GEX:**  {format_number(net_gex)}")
            st.write(f"**Above Spot:** {format_number(gamma_levels.get('net_gex_above_spot',0))}")
            st.write(f"**Below Spot:** {format_number(gamma_levels.get('net_gex_below_spot',0))}")
        st.markdown("---")
        st.subheader("Net GEX vs Spot Movement")
        st.plotly_chart(plot_spot_gex_levels(gex_df,spot_price,gamma_levels,500),
                        use_container_width=True)

    # ── Tab 2: OI & Volume ───────────────────────────────────────────────────
    with tab2:
        st.subheader("Open Interest & Volume Analysis")
        st.plotly_chart(plot_oi_analysis(gex_df, spot_price), use_container_width=True)
        c1,c2 = st.columns(2)
        with c1:
            st.markdown("##### PCR by Strike")
            st.plotly_chart(plot_pcr_analysis(gex_df), use_container_width=True)
        with c2:
            st.markdown("##### Volatility Smile")
            st.plotly_chart(plot_iv_smile(gex_df), use_container_width=True)
        st.markdown("---")
        v1,v2,v3 = st.columns(3)
        cv = gamma_levels.get("total_call_volume",0)
        pv = gamma_levels.get("total_put_volume",0)
        v1.metric("Call Volume", f"{cv:,.0f}")
        v2.metric("Put Volume",  f"{pv:,.0f}")
        v3.metric("Volume PCR",  f"{pv/cv:.3f}" if cv>0 else "—")

    # ── Tab 3: Greeks ─────────────────────────────────────────────────────────
    with tab3:
        st.subheader("Greeks Analysis")
        greek = st.selectbox("Greek:", ["Gamma","Delta","Vega","Theta","Rho"])
        st.plotly_chart(plot_greeks_heatmap(gex_df, greek.lower()), use_container_width=True)
        st.markdown("---")
        st.subheader("ATM Greeks")
        ai = (gex_df["strike"]-spot_price).abs().idxmin()
        ar = gex_df.loc[ai]
        gc1,gc2 = st.columns(2)
        with gc1:
            st.markdown("##### Call (ATM)")
            for g,v in [("Delta","call_delta"),("Gamma","call_gamma"),
                        ("Vega","call_vega"),("Theta","call_theta"),("Rho","call_rho")]:
                st.write(f"**{g}:** {ar[v]:.5f}")
            st.write(f"**Theo:** ₹{ar['call_theo']:.2f} · **LTP:** ₹{ar['call_ltp']:.2f}")
        with gc2:
            st.markdown("##### Put (ATM)")
            for g,v in [("Delta","put_delta"),("Gamma","put_gamma"),
                        ("Vega","put_vega"),("Theta","put_theta"),("Rho","put_rho")]:
                st.write(f"**{g}:** {ar[v]:.5f}")
            st.write(f"**Theo:** ₹{ar['put_theo']:.2f} · **LTP:** ₹{ar['put_ltp']:.2f}")
        st.markdown("---")
        st.subheader("Portfolio Exposure")
        e1,e2,e3,e4 = st.columns(4)
        e1.metric("ΔEX", format_number(gex_df["total_dex"].sum()))
        e2.metric("ΓEX", format_number(gex_df["total_gex"].sum()))
        e3.metric("νEX", f"{gex_df['total_vex'].sum():,.0f}")
        e4.metric("ΘEX/day", format_number(gex_df["total_tex"].sum()))

    # ── Tab 4: Charts ─────────────────────────────────────────────────────────
    # -- Tab 4: Charts & Matrix --------------------------------------------------------
    with tab4:
        st.subheader("📋 Gamma Confusion Matrix & Exposure Overlap")
    
        # 1. Logic to define the Current Market State
        c_gex = gex_df['call_gex'].sum()
        p_gex = gex_df['put_gex'].sum()
        n_gex = net_gex
        
        call_state = "+ve" if c_gex > 0 else "-ve"
        put_state = "+ve" if p_gex > 0 else "-ve"
        net_state = "+ve" if n_gex > 0 else "-ve"
    
        # 2. Define the Matrix Data
        matrix_data = [
            {"Call G": "+ve", "Put G": "+ve", "Net GEX": "+ve", "Nature": "Ultra-Stable", "Dealer Logic": "Dealers Long both; Volatility suppressed."},
            {"Call G": "+ve", "Put G": "-ve", "Net GEX": "+ve", "Nature": "Bullish Support", "Dealer Logic": "Long Calls > Short Puts; Market floor exists."},
            {"Call G": "+ve", "Put G": "-ve", "Net GEX": "-ve", "Nature": "Volatility Trap", "Dealer Logic": "Short Puts dominate; Risk of rapid sell-off."},
            {"Call G": "-ve", "Put G": "+ve", "Net GEX": "+ve", "Nature": "Bearish Resistance", "Dealer Logic": "Short Calls act as 'Negative Force' capping upside."},
            {"Call G": "-ve", "Put G": "+ve", "Net GEX": "-ve", "Nature": "The Squeeze", "Dealer Logic": "Short Calls dominate; Breakout triggers 'Melt-up'."},
            {"Call G": "-ve", "Put G": "-ve", "Net GEX": "-ve", "Nature": "Maximum Chaos", "Dealer Logic": "Short everything; Dealers amplify moves both ways."}
        ]
        
        matrix_df = pd.DataFrame(matrix_data)
    
        # 3. Highlight the Active Regime
        def highlight_active(row):
            if row['Call G'] == call_state and row['Put G'] == put_state and row['Net GEX'] == net_state:
                return ['background-color: rgba(255, 165, 0, 0.3)'] * len(row)
            return [''] * len(row)
    
        st.table(matrix_df.style.apply(highlight_active, axis=1))
    
        st.markdown("---")
        
        # 4. Gamma Overlap Chart (Call vs Put)
        st.subheader("📊 Gamma Exposure Overlap (Call vs Put)")
        
        import plotly.graph_objects as go
        
        fig_overlap = go.Figure()
    
        # Call Gamma Bar
        fig_overlap.add_trace(go.Bar(
            x=gex_df['strike'],
            y=gex_df['call_gex'],
            name='Call GEX (Negative Force)',
            marker_color='#ef4444', # Red for Short Gamma pressure
            opacity=0.7
        ))
    
        # Put Gamma Bar
        fig_overlap.add_trace(go.Bar(
            x=gex_df['strike'],
            y=gex_df['put_gex'],
            name='Put GEX (Support/Hedging)',
            marker_color='#22c55e', # Green for Long Gamma support
            opacity=0.7
        ))
    
        fig_overlap.update_layout(
            template="plotly_dark",
            barmode='overlay',
            xaxis_title="Strike Price",
            yaxis_title="GEX (Cr)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=20, r=20, t=40, b=20),
            xaxis=dict(range=[spot_price * 0.95, spot_price * 1.05]) # Zoomed to ±5%
        )
        
        # Add Spot Line
        fig_overlap.add_vline(x=spot_price, line_dash="dash", line_color="white", annotation_text=f"Spot: {spot_price}")
    
        st.plotly_chart(fig_overlap, use_container_width=True)
    
        st.info("""
        **💡 How to Read:** - **Call GEX (-ve):** Represents the 'Negative Force' where dealers are short calls. High bars here act as resistance.
        - **Put GEX (+ve):** Represents dealer support. High bars here act as structural price floors.
        - **Overlap:** Areas where both are high create high-friction zones and possible 'Gamma Explosions' if the net balance flips.
        """)
    # ── Tab 5: Signals ────────────────────────────────────────────────────────
    with tab5:
        st.subheader("🎯 Intelligent Trade Signals")
        recs = generate_trade_recommendations(gex_df, spot_price, gamma_levels)
        if recs:
            for i,r in enumerate(recs,1):
                icon = {"HIGH":"🔴","MEDIUM":"🟡","INFO":"🔵"}.get(r["confidence"],"⚪")
                with st.expander(f"{icon} {r['signal']} — {r['strategy']}",
                                  expanded=(i<=3)):
                    st.markdown(f"**Confidence:** `{r['confidence']}`")
                    st.markdown(f"**Analysis:** {r['reasoning']}")
                    st.markdown(f"**Action:** {r['action']}")
        else:
            st.info("No strong signals – market appears balanced.")
        st.markdown("---")
        st.subheader("Risk Assessment")
        ra1,ra2 = st.columns(2)
        with ra1:
            st.markdown("##### Market Regime")
            if net_gex > 0:
                st.success("✅ Positive Gamma – range-bound, stabilising")
            else:
                st.warning("⚠️ Negative Gamma – trending, volatile")
            if pcr > 1.2:
                st.error("🐻 Bearish PCR")
            elif pcr < 0.8:
                st.error("🐂 Bullish PCR")
            else:
                st.info("➡️ Neutral PCR")
        with ra2:
            st.markdown("##### Key Levels")
            st.write(f"**Max Pain:**   ₹{max_pain:,.0f}")
            st.write(f"**Gamma Flip:** ₹{gamma_flip:,.0f}")
            st.write(f"**Call Wall:**  ₹{max_call_oi_strike:,.0f}")
            st.write(f"**Put Wall:**   ₹{max_put_oi_strike:,.0f}")

    # ── Tab 6: Chain ──────────────────────────────────────────────────────────
    with tab6:
        st.subheader("Options Chain with Greeks")
        cols_ord = [
            "strike","call_oi","call_volume","call_ltp","call_iv",
            "call_delta","call_gamma","call_vega","call_theta",
            "put_theta","put_vega","put_gamma","put_delta",
            "put_iv","put_ltp","put_volume","put_oi",
        ]
        disp = gex_df[[c for c in cols_ord if c in gex_df.columns]].copy()
        disp.columns = [
            "Strike","C-OI","C-Vol","C-LTP","C-IV%",
            "C-Δ","C-Γ","C-ν","C-Θ",
            "P-Θ","P-ν","P-Γ","P-Δ",
            "P-IV%","P-LTP","P-Vol","P-OI",
        ][:len(disp.columns)]

        atm_strikes = (gex_df.iloc[(gex_df["strike"]-spot_price).abs()
                        .argsort()[:3]]["strike"].values)

        def _hl(row):
            # Initialize with empty strings
            styles = [""] * len(row)
            strike = row["Strike"]
            
            # Calculate 3% range boundaries
            lower_bound = spot_price * 0.97
            upper_bound = spot_price * 1.03
            is_in_range = lower_bound <= strike <= upper_bound

            # 1. Call side logic
            for i, col in enumerate(disp.columns):
                if col.startswith("C-"):
                    # Highlight Yellow if Premium < 10 AND strike is within +/- 3% range
                    if col == "C-LTP" and row["C-LTP"] < 10 and is_in_range:
                        styles[i] = "background-color: rgba(255, 255, 0, 0.6); color: black; font-weight: bold"
                    # Else fall back to ITM Green
                    elif strike < spot_price:
                        styles[i] = "background-color: rgba(34, 197, 94, 0.15)"
            
            # 2. Put side logic
            for i, col in enumerate(disp.columns):
                if col.startswith("P-"):
                    # Highlight Yellow if Premium < 10 AND strike is within +/- 3% range
                    if col == "P-LTP" and row["P-LTP"] < 10 and is_in_range:
                        styles[i] = "background-color: rgba(255, 255, 0, 0.6); color: black; font-weight: bold"
                    # Else fall back to ITM Red
                    elif strike > spot_price:
                        styles[i] = "background-color: rgba(239, 68, 68, 0.15)"

            # 3. ATM Highlight (Orange overlay on Strike column)
            if strike in atm_strikes:
                styles[0] = "background-color: rgba(255, 165, 0, 0.4); font-weight: bold"
                
            return styles

        fmt = {
            "Strike":"{:.0f}","C-OI":"{:,.0f}","P-OI":"{:,.0f}",
            "C-Vol":"{:,.0f}","P-Vol":"{:,.0f}",
            "C-LTP":"{:.2f}","P-LTP":"{:.2f}","C-IV%":"{:.2f}","P-IV%":"{:.2f}",
            "C-Δ":"{:.4f}","P-Δ":"{:.4f}","C-Γ":"{:.6f}","P-Γ":"{:.6f}",
            "C-ν":"{:.4f}","P-ν":"{:.4f}","C-Θ":"{:.2f}","P-Θ":"{:.2f}",
        }
        vf = {k:v for k,v in fmt.items() if k in disp.columns}
        
        st.dataframe(disp.style.apply(_hl, axis=1).format(vf),
                     height=500, use_container_width=True)
        
        # Ensure download timestamp is also in IST
        ist_now = datetime.now(pytz.timezone('Asia/Kolkata'))
        st.download_button(
            "📥 Download CSV", gex_df.to_csv(index=False),
            file_name=f"gex_{symbol}_{st.session_state.selected_expiry}_"
                      f"{ist_now.strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv")
        
    # ── Tab 7: Guide ──────────────────────────────────────────────────────────
    with tab7:
        st.subheader("ℹ️ Guide")
        st.markdown(f"""
### Expiry Calendar (NSE – May 2025)
| Index | Weekly | Day |
|-------|--------|-----|
| NIFTY | ✅ Yes | Thursday |
| BANKNIFTY | ❌ No (monthly) | Last Wednesday |
| FINNIFTY | ✅ Yes | Tuesday |
| MIDCPNIFTY | ✅ Yes | Monday |

### Debug: Why is Kite fetch failing?
1. **Token expired** – Kite tokens reset at **6:00 AM daily**. Reconnect each morning.
2. **Run 🔍 Debug Connection** in the sidebar – it tests session, LTP, instruments, quote step by step.
3. **Instrument cache** – if the cache is stale, click "🗑 Clear Instrument Cache" and retry.
4. **Market closed** – `/quote` may return 0 OI / LTP outside trading hours. The terminal still works but GEX may show zeros.

### Charts Tab
Requires Kite Connect. Fetches historical OHLCV via `kite.historical_data()`.
- **INDIA VIX** instrument token: 264969 (stable NSE-assigned)
- VIX zones: Calm (<12) · Low (<15) · Normal (<20) · Elevated (<25) · High Fear (<35)
- S/R detection: swing highs/lows (configurable lookback), clustered within 0.15%, plus classical pivots and previous-day levels

### IV Calculation
Kite does not provide IV. Terminal back-solves from LTP using Brent's method on Black-Scholes.

---
⚠️ Educational only. Not financial advice.
        """)

# ─── Welcome screen ───────────────────────────────────────────────────────────
else:
    st.info("👈 Authenticate Kite / select data source, then click **📥 Fetch Option Chain**.")
    st.markdown("""
| Feature | Detail |
|---------|--------|
| Spot refresh | `/quote/ltp` – fast, independent of chain |
| Expiries | From Kite NFO instruments (holiday-aware) |
| Lot size & interval | From Kite instruments |
| BANKNIFTY | Monthly-only on NSE |
| Charts | 1-hr index + VIX + dynamic S/R via `historical_data()` |
| Debug | 🔍 panel tests session → LTP → instruments → quote |
    """)

    c1,c2 = st.columns(2)
    for col, sym, grad in [
        (c1,"NIFTY",    "linear-gradient(135deg,#667eea,#764ba2)"),
        (c2,"BANKNIFTY","linear-gradient(135deg,#f093fb,#f5576c)"),
    ]:
        with col:
            try:
                q = get_index_quote(sym)
                if q:
                    arrow = "🟢" if q["change"]>=0 else "🔴"
                    label = "NIFTY 50" if sym=="NIFTY" else "BANK NIFTY"
                    st.markdown(f"""
<div style='background:{grad};padding:1.4rem;border-radius:12px;color:white;text-align:center'>
  <h3 style='margin:0;color:white'>{label}</h3>
  <h1 style='margin:.4rem 0;color:white;font-size:2.2rem'>₹{q['last']:,.2f}</h1>
  <p style='margin:0;font-size:1.2rem'>{arrow} {q['change']:+.2f}%</p>
  <hr style='margin:.7rem 0;border-color:rgba(255,255,255,.3)'>
  <div style='display:flex;justify-content:space-around'>
    <div><small>Open</small><br><b>₹{q['open']:,.0f}</b></div>
    <div><small>High</small><br><b>₹{q['high']:,.0f}</b></div>
    <div><small>Low</small><br><b>₹{q['low']:,.0f}</b></div>
  </div>
</div>""", unsafe_allow_html=True)
            except Exception:
                st.error(f"Could not load {sym}")

    try:
        mkt = get_market_status()
        e   = "🟢" if "Open" in mkt.get("market_state","") else "🔴"
        st.caption(f"{e} Market: {mkt['market_state']} | {mkt['timestamp']}")
    except Exception:
        pass

# ─── Footer ───────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style='text-align:center;color:#888;padding:1rem'>
  <b>Professional GEX Terminal v3.1</b><br>
  Kite Connect v3 · /quote/ltp spot · /quote chain · historical_data charts<br>
  <span style='font-size:.75rem'>
    ⚠️ Educational only. Not financial advice. Trade at your own risk.
  </span>
</div>""", unsafe_allow_html=True)
