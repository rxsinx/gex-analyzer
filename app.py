"""
Professional GEX Terminal —  Live Engine Edition
=====================================================
Architecture
------------
Every Streamlit rerun is either:
  (a) user interaction  — normal flow
  (b) st_autorefresh    — live engine tick

On a live tick the script runs top-to-bottom but the LIVE ENGINE BLOCK
at the very top intercepts the rerun and:
  • every 5 s  → kite.ltp() spot  → recalculate GEX in-memory (no chain call)
  • every N s  → kite.quote() full chain re-fetch → rebuild gex_df from scratch

All slider/select values that the engine needs (strike_range, risk_free_rate,
expiry, symbol) are mirrored into session state so the engine can read them
without re-rendering widgets.
"""

import streamlit as st
import pandas as pd
import pytz
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

from modules.data_fetcher import (
    fetch_option_chain, generate_sample_data,
    get_live_spot_price, get_index_quote, get_market_status,
)
from modules.gex_calculator import calculate_gex, find_gamma_levels, calculate_gex_delta
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
from modules.menthorq_gex import plot_menthorq_gex, generate_gex_analysis
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

IST = pytz.timezone("Asia/Kolkata")
ticker_placeholder = st.empty()
metrics_placeholder = st.empty()

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="GEX Terminal", page_icon="📊",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
.block-container{padding-top:0.4rem !important;padding-bottom:0.2rem !important}
.main-header{font-size:1.6rem;font-weight:bold;
  background:linear-gradient(90deg,#1f77b4,#ff7f0e);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  text-align:center;margin:0;padding:0;line-height:1.2}
.sub-header{text-align:center;color:#888;font-size:0.76rem;
  margin:0 0 0.2rem 0;padding:0}
hr{margin:0.2rem 0 !important;border-color:rgba(49,51,63,0.25) !important}
[data-testid="stMetricValue"]{font-size:1.0rem !important;line-height:1.25 !important}
[data-testid="stMetricLabel"]{font-size:0.68rem !important;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-testid="stMetricDelta"]{font-size:0.62rem !important}
div[data-testid="metric-container"]{padding:0.1rem 0.35rem !important}
.stAlert{padding:0.25rem 0.6rem !important;font-size:0.76rem !important}

/* live pulse dot */
.live-dot{display:inline-block;width:9px;height:9px;background:#22c55e;
  border-radius:50%;margin-right:5px;animation:pulse 1.4s infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}
                 50%{opacity:.25;transform:scale(0.7)}}

/* live status bar */
.live-bar{
  display:flex;align-items:center;justify-content:space-between;
  background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.25);
  border-radius:8px;padding:0.35rem 1rem;margin-bottom:0.4rem;
  font-size:0.78rem;font-family:monospace}
.live-bar-off{
  display:flex;align-items:center;justify-content:space-between;
  background:rgba(100,116,139,0.08);border:1px solid rgba(100,116,139,0.2);
  border-radius:8px;padding:0.35rem 1rem;margin-bottom:0.4rem;
  font-size:0.78rem;font-family:monospace;color:#64748b}

/* ticker tape */
.ticker{
  font-size:1.1rem;font-weight:700;font-family:monospace;
  padding:0.15rem 0.5rem;border-radius:4px}
.tick-up{color:#22c55e}
.tick-dn{color:#ef4444}
.tick-flat{color:#94a3b8}

.stTabs [data-baseweb="tab"]{height:34px;background:#f0f2f6;
  border-radius:5px 5px 0 0;padding:4px 13px;font-weight:600;font-size:0.82rem}
.stTabs [aria-selected="true"]{
  background:linear-gradient(135deg,#667eea,#764ba2);color:white}
[data-testid="stHorizontalBlock"]{gap:0.4rem !important}
</style>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# SESSION STATE INIT
# ═══════════════════════════════════════════════════════════════════════════════
_defaults = {
    "data_loaded":            False,
    "options_df":             None,
    "spot_price":             None,
    "prev_spot":              None,          # previous tick spot (for Δ arrow)
    "spot_ohlc":              None,
    "last_update":            None,          # last full chain fetch time
    "last_spot_update":       None,
    "gex_df":                 None,
    "gamma_levels":           None,
    "kite_authenticated":     False,
    "kite_manager":           None,
    "lot_size":               None,
    "strike_interval":        None,
    "selected_expiry":        None,
    "selected_symbol":        "NIFTY",
    "chart_index_df":         None,
    "chart_vix_df":           None,
    "chart_levels":           None,
    # live engine
    "live_mode":              False,
    "strike_range_val":       STRIKE_RANGE_DEFAULT,
    "risk_free_rate_val":     RFR_DEFAULT,
    "chain_refresh_interval": 300,          # seconds between full chain re-fetches
    "live_error":             None,
    "chain_error":            None,
    "live_tick_count":        0,
    "chain_fetch_count":      0,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ═══════════════════════════════════════════════════════════════════════════════
# ⚡  LIVE ENGINE  — runs on EVERY rerun (both user-triggered and autorefresh)
# ═══════════════════════════════════════════════════════════════════════════════
def _live_engine_tick():
    """Fast tick: use delta calculation instead of full recalc"""
    km = st.session_state.kite_manager
    sym = st.session_state.selected_symbol
    exp = st.session_state.selected_expiry
    sr = st.session_state.strike_range_val
    rfr = st.session_state.risk_free_rate_val

    try:
        new_spot = km.get_spot_ltp(sym)
        ohlc = km.get_spot_ohlc(sym)

        if new_spot and st.session_state.gex_df is not None:
            old_spot = st.session_state.spot_price
            
            if new_spot != old_spot:
                # FAST PATH: Incremental GEX update (~200ms)
                gx = calculate_gex(
                    st.session_state.gex_df,
                    old_spot,
                    new_spot,
                    exp,
                    rfr
                )
                gl = find_gamma_levels(gx, new_spot)
                
                st.session_state.update({
                    "prev_spot": old_spot,
                    "spot_price": new_spot,
                    "spot_ohlc": ohlc,
                    "gex_df": gx,
                    "gamma_levels": gl,
                    "last_spot_update": datetime.now(IST),
                    "live_tick_count": st.session_state.live_tick_count + 1,
                })
    except Exception as e:
        st.session_state.live_error = str(e)

    # ── slow path: full chain re-fetch ────────────────────────────────────────
    now          = datetime.now(IST)
    last_chain   = st.session_state.last_update
    chain_age_s  = (
        (now - last_chain).total_seconds()
        if last_chain else 9999
    )
    chain_ivl    = st.session_state.chain_refresh_interval

    if chain_age_s >= chain_ivl:
        try:
            df, spot = km.get_option_chain(sym, exp, rfr)
            if df is not None and not df.empty and spot:
                df_f = filter_strikes(df, spot, sr)
                gx   = calculate_gex(df_f, spot, exp, rfr)
                gl   = find_gamma_levels(gx, spot)
                lot  = get_lot_size(sym, km)
                si   = get_strike_interval(sym, exp, km)
                st.session_state.update({
                    "options_df":        df,
                    "spot_price":        spot,
                    "gex_df":            gx,
                    "gamma_levels":      gl,
                    "last_update":       now,
                    "last_spot_update":  now,
                    "lot_size":          lot,
                    "strike_interval":   si,
                    "chain_error":       None,
                    "chain_fetch_count": st.session_state.chain_fetch_count + 1,
                })
        except KiteAuthError as e:
            st.session_state.chain_error = f"Session expired: {e}"
            st.session_state.live_mode   = False
        except Exception as e:
            st.session_state.chain_error = str(e)

  ##incse of error delete from 237 to 251 / FIXED: Get kite_mgr from session state
    if chain_age_s >= chain_ivl:
        try:
            km_chart = st.session_state.kite_manager  # ← GET FROM SESSION
            if km_chart:
                try:
                    new_spot = km_chart.get_spot_ltp(sym)
                except Exception:
                    new_spot = st.session_state.spot_price or spot_price
                
                index_df, vix_df = km_chart.get_index_and_vix_data(
                    sym, interval="60minute", days_back=22
                )
                levels = analyse_levels(index_df, new_spot)
                st.session_state.update({
                    "chart_index_df": index_df,
                    "chart_vix_df": vix_df,
                    "chart_levels": levels,
                })
        except Exception as e:
            st.session_state.chain_error = f"Chart data: {e}"
          
# ── TRIGGER AUTOREFRESH + UPDATE PLACEHOLDERS (smooth, no blink) ───────────────────
if (st.session_state.live_mode
        and st.session_state.kite_authenticated
        and st.session_state.data_loaded):

    # 5 second autorefresh      
    st_autorefresh(interval=5_000, limit=None, key="live_engine_ar")

    # Run the update logic      
    _live_engine_tick()


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE HEADER
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<p class="main-header">📊 Professional GEX Terminal</p>',
            unsafe_allow_html=True)
st.markdown(
    '<p class="sub-header">Kite Connect · Real-Time Greeks · Live Engine · VIX Chart</p>',
    unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR - UPDATED WITH SENSEX AND BANKEX SUPPORT
# ═══════════════════════════════════════════════════════════════════════════════
# Insert this section into your app.py sidebar (replace the existing symbol selection)

with st.sidebar:
    st.header("⚙️ Configuration")

    # ── ⚡ LIVE MODE (most prominent control) ──────────────────────────────────
    st.subheader("⚡ Live Engine")
    can_go_live = (st.session_state.kite_authenticated
                   and st.session_state.data_loaded)

    if st.session_state.live_mode:
        if st.button("🔴 STOP LIVE", type="primary", use_container_width=True):
            st.session_state.live_mode = False
            st.rerun()
        ticks = st.session_state.live_tick_count
        chains = st.session_state.chain_fetch_count
        st.caption(f"✅ Running · {ticks} spot ticks · {chains} chain fetches")

        chain_ivl = st.slider(
            "Chain refresh interval (s)", 60, 600,
            st.session_state.chain_refresh_interval, 30,
            key="chain_ivl_slider",
        )
        st.session_state.chain_refresh_interval = chain_ivl

        # surface any live errors
        if st.session_state.live_error:
            st.error(f"⚠️ Spot: {st.session_state.live_error}")
        if st.session_state.chain_error:
            st.warning(f"⚠️ Chain: {st.session_state.chain_error}")
    else:
        btn_help = (
            "Authenticate Kite and fetch option chain first"
            if not can_go_live else
            "5 s spot refresh · periodic chain refresh"
        )
        if st.button(
            "🟢 GO LIVE",
            type="primary",
            use_container_width=True,
            disabled=not can_go_live,
            help=btn_help,
        ):
            st.session_state.live_mode        = True
            st.session_state.live_tick_count  = 0
            st.session_state.chain_fetch_count = 0
            st.session_state.live_error       = None
            st.session_state.chain_error      = None
            st.rerun()

    st.markdown("---")

    # ── Kite auth ─────────────────────────────────────────────────────────────
    st.subheader("🔐 Kite Authentication")

    if not st.session_state.kite_authenticated:
        api_key    = st.text_input("API Key",    value=KITE_API_KEY,    type="password")
        api_secret = st.text_input("API Secret", value=KITE_API_SECRET, type="password")

        if api_key and api_secret:
            km_url    = KiteManager(api_key, api_secret)
            login_url = km_url.get_login_url()
            st.link_button("🔗 Connect to Kite", login_url,
                           type="primary", use_container_width=True)

        req_token = st.text_input("Paste Request Token from URL:")

        if req_token and st.button("✅ Generate Session", type="primary",
                                    use_container_width=True):
            if api_key and api_secret:
                km_temp = KiteManager(api_key, api_secret)
                ok, msg = km_temp.set_access_token(req_token)
                if ok:
                    st.session_state.kite_manager       = km_temp
                    st.session_state.kite_authenticated = True
                    st.success("✅ Connected")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")
    else:
        st.success("✅ Kite Connected")
        col_d, col_dbg = st.columns(2)
        if col_d.button("Disconnect", use_container_width=True):
            st.session_state.kite_authenticated = False
            st.session_state.kite_manager       = None
            st.session_state.live_mode          = False
            st.rerun()

        with st.expander("🔍 Debug Connection", expanded=False):
            st.caption("Tests each Kite API step independently")
            debug_sym = st.selectbox("Test symbol:", 
                                      ["NIFTY","BANKNIFTY","FINNIFTY","MIDCPNIFTY","SENSEX","BANKEX"],
                                      key="debug_sym")
            if st.button("▶ Run Diagnostics", key="run_diag"):
                km_d = st.session_state.kite_manager
                if km_d:
                    with st.spinner("Running tests…"):
                        results = km_d.test_connection(debug_sym)
                    for step, info in results.items():
                        icon = "✅" if info["ok"] else "❌"
                        (st.success if info["ok"] else st.error)(
                            f"{icon} **{info['label']}** — {info['msg']}")
                    if not all(v["ok"] for v in results.values()):
                        st.warning(
                            "**Common fixes:**\n"
                            "- Token expires at 6 AM daily → re-authenticate\n"
                            "- Instruments load takes ~30 s on first call\n"
                            "- API key must have F&O data permissions\n"
                            "- For BSE (SENSEX/BANKEX): check if BFO segment is enabled"
                        )

            if st.button("🗑 Clear Instrument Cache", key="clear_cache"):
                if st.session_state.kite_manager:
                    st.session_state.kite_manager.invalidate_cache()
                    st.success("Cache cleared.")

    st.markdown("---")
    kite_mgr = st.session_state.kite_manager

    # ── Symbol Selection (NOW WITH SENSEX & BANKEX) ───────────────────────────
    st.subheader("📈 Index Selection")
    
    symbol = st.selectbox(
        "Select Index",
        ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"],
        help="NSE: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY\nBSE: SENSEX, BANKEX"
    )
    st.session_state.selected_symbol = symbol
    
    # Index info display
    index_info = {
        "NIFTY":      "NSE · Lot: 65 · 50 pts",
        "BANKNIFTY":  "NSE · Lot: 30 · 100 pts",
        "FINNIFTY":   "NSE · Lot: 60 · 50 pts",
        "MIDCPNIFTY": "NSE · Lot: 120 · 25 pts",
        "SENSEX":     "BSE · Lot: 20 · 100 pts",
        "BANKEX":     "BSE · Lot: 30 · 100 pts",
    }
    st.caption(f"ℹ️ {index_info.get(symbol, 'Unknown')}")

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
    

    # ── Expiry ────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📅 Expiry Configuration")
    
    # Determine weekly/monthly availability for selected symbol
    sym_has_weekly = has_weekly_expiry(symbol, None)
    # Fallback to Kite if connected and NSE rules say False
    if not sym_has_weekly and kite_mgr:
        try:
            sym_has_weekly = kite_mgr.has_weekly_expiry(symbol)
        except KiteError:
            pass

    if sym_has_weekly:
        et_label    = st.radio("Expiry Type", ["Weekly","Monthly"], horizontal=True)
        expiry_type = "weekly" if et_label == "Weekly" else "monthly"
    else:
        expiry_type = "monthly"
        expiry_info = {
            "BANKNIFTY": "📅 BANKNIFTY: Monthly only",
            "FINNIFTY": "📅 FINNIFTY: Monthly only",
            "MIDCPNIFTY": "📅 MIDCPNIFTY: Monthly only",
            "BANKEX":    "📅 BANKEX: Monthly only",
        }
        if symbol in expiry_info:
            st.info(expiry_info[symbol])

    try:
        available_expiries = get_expiries_for_symbol(symbol, kite_mgr, expiry_type)
    except KiteError:
        available_expiries = get_expiries_for_symbol(symbol, None, expiry_type)

    if not available_expiries:
        available_expiries = [get_next_expiry_for_symbol(symbol, expiry_type)]

    expiry_date = st.selectbox(
        "Select Expiry", available_expiries, index=0,
        help="From Kite instruments" if kite_mgr else "Computed from NSE/BSE rules")
    st.session_state.selected_expiry = expiry_date

    # ── Parameters ───────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📍 Parameters")
    strike_range = st.slider(
        "Strike Range (%)", 5, 15, st.session_state.strike_range_val, 1)
    st.session_state.strike_range_val = strike_range

    risk_free_rate = st.number_input(
        "Risk-Free Rate (%)", 0.0, 15.0,
        round(st.session_state.risk_free_rate_val * 100, 1), 0.1
    ) / 100
    st.session_state.risk_free_rate_val = risk_free_rate

    # ── Manual spot refresh ───────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("💹 Spot Price")
    sc1, sc2 = st.columns(2)

    with sc1:
        if st.button("🔄 Refresh Spot", use_container_width=True,
                     disabled=st.session_state.live_mode):
            with st.spinner("Fetching LTP…"):
                try:
                    if kite_mgr:
                        new_spot = kite_mgr.get_spot_ltp(symbol)
                        ohlc     = kite_mgr.get_spot_ohlc(symbol)
                    else:
                        new_spot = get_live_spot_price(symbol, "nselib")
                        ohlc     = None
                    if new_spot:
                        st.session_state.prev_spot        = st.session_state.spot_price
                        st.session_state.spot_price       = new_spot
                        st.session_state.spot_ohlc        = ohlc
                        st.session_state.last_spot_update = datetime.now(IST)
                        if (st.session_state.data_loaded
                                and st.session_state.options_df is not None):
                            df_f = filter_strikes(
                                st.session_state.options_df, new_spot, strike_range)
                            gx   = calculate_gex(df_f, new_spot, expiry_date, risk_free_rate)
                            st.session_state.gex_df       = gx
                            st.session_state.gamma_levels = find_gamma_levels(gx, new_spot)
                        st.success(f"₹{new_spot:,.2f}")
                    else:
                        st.warning("Spot not available (market closed?)")
                except KiteAuthError as e:
                    st.error(f"🔐 Session expired: {e}")
                except KiteError as e:
                    st.error(f"Kite error: {e}")
                except Exception as e:
                    st.error(f"Error: {e}")
    with sc2:
        if st.session_state.live_mode:
            st.markdown("🟢 **AUTO**", help="Spot auto-refreshing every 5 s")
        else:
            enable_spot_refresh = st.checkbox("Auto", value=False)
            if enable_spot_refresh and kite_mgr:
                st_autorefresh(interval=SPOT_REFRESH*1000, limit=None, key="spot_ar")

    # ── Option chain fetch ────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🔄 Option Chain")

    if st.button("📥 Fetch Option Chain", type="primary", use_container_width=True):
        with st.spinner(f"Fetching {symbol} chain for {expiry_date}…"):
            df, spot = None, None
            fetch_ok = False

            if not kite_mgr:
                st.error("Kite not connected. Authenticate first.")
            else:
                try:
                    df, spot = kite_mgr.get_option_chain(
                        symbol, expiry_date, risk_free_rate)
                    fetch_ok = True
                    st.success(f"✅ {len(df):,} contracts · spot ₹{spot:,.2f}")
                except KiteAuthError as e:
                    st.error(f"🔐 Session expired:\n{e}")
                except KiteDataError as e:
                    st.error(f"📊 Data error:\n{e}")
                except KiteError as e:
                    st.error(f"Kite error: {e}")
                except Exception as e:
                    st.error(f"Unexpected error: {e}")

            if not fetch_ok and df is None:
                st.warning("⚠️ Falling back to sample data.")
                try:
                    from modules.utils import get_fallback_spot
                    live_spot = get_live_spot_price(symbol, "nselib") or get_fallback_spot(symbol)
                    df, spot  = generate_sample_data(symbol, live_spot, expiry_date, kite_mgr)
                    fetch_ok  = True
                    st.info(f"📊 Sample data · spot ₹{spot:,.2f}")
                except Exception as e:
                    st.error(f"Sample fallback failed: {e}")

            if df is not None and not df.empty and spot:
                df_f = filter_strikes(df, spot, strike_range)
                if df_f.empty:
                    df_f = filter_strikes(df, spot, 15)
                    st.warning("Widened strike range to ±15%.")
                try:
                    gx  = calculate_gex(df_f, spot, expiry_date, risk_free_rate)
                    gl  = find_gamma_levels(gx, spot)
                    now = datetime.now(IST)
                    # Fetch OHLC now if not already fetched
                    if not st.session_state.get("spot_ohlc") and kite_mgr:
                        try:
                            ohlc_init = kite_mgr.get_spot_ohlc(symbol)
                        except Exception:
                            ohlc_init = None
                    else:
                        ohlc_init = st.session_state.get("spot_ohlc")
                    prev_close = (ohlc_init["close"]
                                  if ohlc_init and ohlc_init.get("close")
                                  else spot)
                    st.session_state.update({
                        "options_df":         df,
                        "spot_price":         spot,
                        "prev_spot":          prev_close,
                        "spot_ohlc":          ohlc_init,
                        "gex_df":             gx,
                        "gamma_levels":       gl,
                        "data_loaded":        True,
                        "last_update":        now,
                        "last_spot_update":   now,
                        "lot_size":           get_lot_size(symbol, kite_mgr if fetch_ok else None),
                        "strike_interval":    get_strike_interval(symbol, expiry_date,
                                                                   kite_mgr if fetch_ok else None),
                        "live_tick_count":    0,
                        "chain_fetch_count":  0,
                        "live_error":         None,
                        "chain_error":        None,
                    })
                except Exception as e:
                    st.error(f"GEX calculation error: {e}")

    # ── Sidebar status ────────────────────────────────────────────────────────
    


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN CONTENT
# ═══════════════════════════════════════════════════════════════════════════════
if st.session_state.data_loaded and st.session_state.gex_df is not None:

    spot_price   = st.session_state.spot_price
    prev_spot    = st.session_state.prev_spot or spot_price
    gex_df       = st.session_state.gex_df
    gamma_levels = st.session_state.gamma_levels
    lot_size     = st.session_state.lot_size
    si           = st.session_state.strike_interval
    symbol       = st.session_state.selected_symbol

    # ── ⚡ LIVE STATUS BAR ────────────────────────────────────────────────────
    with ticker_placeholder.container():
        tick_delta = spot_price - prev_spot

        ohlc       = st.session_state.spot_ohlc or {}
        day_close  = ohlc.get("close") or prev_spot          # prev session close
        spot_delta     = spot_price - day_close
        spot_delta_pct = (spot_delta / day_close * 100) if day_close else 0
    
        # Arrow direction tracks tick-to-tick momentum, not day change
        tick_arrow  = "▲" if tick_delta > 0 else "▼" if tick_delta < 0 else "●"
        tick_class  = "tick-up" if tick_delta > 0 else "tick-dn" if tick_delta < 0 else "tick-flat"

        now_ist = datetime.now(IST)
        chain_age_s = int((now_ist - st.session_state.last_update).total_seconds()) \
                      if st.session_state.last_update else 0
        spot_age_s  = int((now_ist - st.session_state.last_spot_update).total_seconds()) \
                      if st.session_state.last_spot_update else 0
    
        chain_ivl   = st.session_state.chain_refresh_interval
        chain_eta   = max(0, chain_ivl - chain_age_s)

        if st.session_state.live_mode:
            bar_class = "live-bar"
            mode_tag  = '<span class="live-dot"></span><b>LIVE</b>'
        else:
            bar_class = "live-bar-off"
            mode_tag  = "⏸ PAUSED"

        st.markdown(f"""
<div class="{bar_class}">
  <span>{mode_tag}&nbsp;&nbsp;
    <span class="ticker {tick_class}">
      {symbol} &nbsp; ₹{spot_price:,.2f} &nbsp; {tick_arrow} {abs(spot_delta):,.2f}
      ({spot_delta_pct:+.2f}%)
    </span>
  </span>
  <span>
    Spot age: <b>{spot_age_s}s</b> &nbsp;|&nbsp;
    Chain age: <b>{chain_age_s}s</b> &nbsp;|&nbsp;
    Next chain: <b>{chain_eta}s</b> &nbsp;|&nbsp;
    Ticks: <b>{st.session_state.live_tick_count}</b>
  </span>
</div>""", unsafe_allow_html=True)

    # ✅ UPDATE METRICS IN PLACEHOLDER (NO BLINK!)
    with metrics_placeholder.container():
        pcr                = gamma_levels.get("pcr", 1.0)
        max_pain           = gamma_levels.get("max_pain", spot_price)
        gamma_flip         = gamma_levels.get("gamma_flip", spot_price)
        net_gex            = gamma_levels.get("total_gex", 0)
        max_call_oi_strike = gamma_levels.get("max_call_oi_strike", spot_price)
        max_put_oi_strike  = gamma_levels.get("max_put_oi_strike", spot_price)

        # ATM PCR
        atm_idx = (gex_df["strike"] - spot_price).abs().idxmin()
        atm_row = gex_df.loc[atm_idx]
        atm_pcr = atm_row["put_oi"] / atm_row["call_oi"] if atm_row["call_oi"] > 0 else 0.00
        
        # ── metrics rows ──────────────────────────────────────────────────────────
        ohlc = st.session_state.spot_ohlc or {}
    
        m1,m2,m3,m4,m5,m6,m7,m8,m9 = st.columns(9)
        spot_delta_disp = f"{spot_delta:+.1f}" if spot_delta != 0 else None
        m1.metric("💰 Spot",       f"₹{spot_price:,.0f}", delta=spot_delta_disp)
        m2.metric("Open",          f"₹{ohlc['open']:,.0f}"  if ohlc else "—")
        m3.metric("High",          f"₹{ohlc['high']:,.0f}"  if ohlc else "—")
        m4.metric("Low",           f"₹{ohlc['low']:,.0f}"   if ohlc else "—")
        m5.metric("Prev",          f"₹{ohlc['close']:,.0f}" if ohlc else "—")
        m6.metric("➡️ PCR (ATM)", f"{atm_pcr:.2f}", help="Put/Call OI at ATM strike")
        m7.metric("🎯 Max Pain",   f"₹{max_pain:,.0f}",
                  delta=f"{max_pain - spot_price:+.0f}")
        m8.metric("🔄 Gamma Flip", f"₹{gamma_flip:,.0f}",
                  delta=f"{gamma_flip - spot_price:+.0f}")
        m9.metric("📊 Regime",     "🟢 +GEX" if net_gex>0 else "🔴 -GEX")
    
        n1,n2,n3,n4,n5,n6,n7,n8 = st.columns(8)
        n1.metric("🔴 Call GEX",        format_number(gex_df['call_gex'].sum()))
        n2.metric("🟢 Put GEX",         format_number(gex_df['put_gex'].sum()))
        n3.metric("💹 Net GEX",         format_number(net_gex))
        n4.metric("📦 Lot / Interval",  f"{lot_size} / ₹{si:.0f}")
        n5.metric("📈 Total Call OI",   f"{gamma_levels.get('total_call_oi',0)/1e5:.1f}L")
        n6.metric("📉 Total Put OI",    f"{gamma_levels.get('total_put_oi',0)/1e5:.1f}L")
        n7.metric("🚧 Call Wall",       f"₹{max_call_oi_strike:,.0f}")
        n8.metric("🛡️ Put Wall",        f"₹{max_put_oi_strike:,.0f}")

    # surface live errors inline (non-blocking)
    if st.session_state.live_error:
        st.error(f"⚠️ Live spot error: {st.session_state.live_error}", icon="⚡")
    if st.session_state.chain_error:
        st.warning(f"⚠️ Chain refresh error: {st.session_state.chain_error}")

    # ── tabs ──────────────────────────────────────────────────────────────────
    st.markdown("---")
    tab1,tab2,tab3,tab4,tab5,tab6,tab7 = st.tabs([
        "📊 GEX","📈 OI & Volume","🎲 Greeks",
        "📉 Charts","🎯 Signals","📋 Chain","ℹ️ Guide",
    ])

    with tab1:
        # ─── a. Gamma Exposure Profile (Chart) ───
        st.subheader("Gamma Exposure Profile")
        st.plotly_chart(plot_gex_profile(gex_df, spot_price, gamma_levels), use_container_width=True)
        
        # ─── b. Strike-by-Strike GEX & Positioning Matrix ───
        st.subheader("🏁 Strike-by-Strike GEX & Positioning Matrix")
    
        # 1. Sort options chain chronological order
        matrix_df = gex_df.sort_values(by="strike").copy()
        matrix_df['strike'] = matrix_df['strike'].astype(int)
    
        # 2. Add strike-level PCR safely
        matrix_df['pcr_strike'] = matrix_df.apply(
            lambda r: r['put_oi'] / r['call_oi'] if r['call_oi'] > 0 else 0, axis=1
        )
    
        # 3. Transpose parameters into rows & scale units to Cr and L
        grid_data = {
            "Strike Price": matrix_df["strike"].tolist(),
            "Call GEX (Cr)": (matrix_df["call_gex"] / 1e7).tolist(),
            "Put GEX (Cr)": (matrix_df["put_gex"] / 1e7).tolist(),
            "NET GEX (Cr)": ((matrix_df["call_gex"] + matrix_df["put_gex"]) / 1e7).tolist(),
            "Put OI (L)": (matrix_df["put_oi"] / 1e5).tolist(),
            "Call OI (L)": (matrix_df["call_oi"] / 1e5).tolist(),
            "PCR": matrix_df["pcr_strike"].tolist(),
            "Call Prem": matrix_df["call_theo"].tolist(),      # CHANGED: theo instead of ltp
            "Put Prem": matrix_df["put_theo"].tolist()         # CHANGED: theo instead of ltp
        }
    
        display_matrix = pd.DataFrame(grid_data).set_index("Strike Price").T
    
        # 4. Append Total / Net Calculations Column on Right Margin
        display_matrix["TOTAL / NET"] = [
            gex_df['call_gex'].sum() / 1e7,
            gex_df['put_gex'].sum() / 1e7,
            net_gex / 1e7,
            gamma_levels.get('total_put_oi', 0) / 1e5,
            gamma_levels.get('total_call_oi', 0) / 1e5,
            pd.NA,  # PCR Total
            pd.NA,  # <── ADDED: Blanks out Call Premium Total
            pd.NA   # <── ADDED: Blanks out Put Premium Total
        ]
        
        # String format converter with suffix markers (Catches pd.NA entries cleanly)
        display_matrix_fmt = display_matrix.map(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
        
        # Find precise ATM strike nearest to spot
        atm_strike = int(get_atm_strike(spot_price, si))
        strikes_only = display_matrix.columns.drop("TOTAL / NET")
    
        # Pre-calculate highlight positions from numeric values
        top1_call_gex = display_matrix.loc["Call GEX (Cr)", strikes_only].abs().nlargest(1).index[0]
        top2_call_gex = display_matrix.loc["Call GEX (Cr)", strikes_only].abs().nlargest(2).index[-1]
    
        top1_put_gex = display_matrix.loc["Put GEX (Cr)", strikes_only].abs().nlargest(1).index[0]
        top2_put_gex = display_matrix.loc["Put GEX (Cr)", strikes_only].abs().nlargest(2).index[-1]
    
        # Filter and isolate -ve/lowest NET GEX
        net_neg_series = display_matrix.loc["NET GEX (Cr)", strikes_only]
        net_neg_series = net_neg_series[net_neg_series < 0]
        top1_net_neg = net_neg_series.nsmallest(1).index[0] if not net_neg_series.empty else None
        top2_net_neg = net_neg_series.nsmallest(2).index[-1] if len(net_neg_series) >= 2 else None
    
        # Filter and isolate +ve/highest NET GEX
        net_pos_series = display_matrix.loc["NET GEX (Cr)", strikes_only]
        net_pos_series = net_pos_series[net_pos_series > 0]
        top1_net_pos = net_pos_series.nlargest(1).index[0] if not net_pos_series.empty else None
        top2_net_pos = net_pos_series.nlargest(2).index[-1] if len(net_pos_series) >= 2 else None
    
        # Open Interest ranking checks
        top1_put_oi = display_matrix.loc["Put OI (L)", strikes_only].nlargest(1).index[0]
        top2_put_oi = display_matrix.loc["Put OI (L)", strikes_only].nlargest(2).index[-1]
    
        top1_call_oi = display_matrix.loc["Call OI (L)", strikes_only].nlargest(1).index[0]
        top2_call_oi = display_matrix.loc["Call OI (L)", strikes_only].nlargest(2).index[-1]
    
        # String format converter with suffix markers
        display_matrix_fmt = display_matrix.map(lambda x: f"{x:.2f}")
        display_matrix_fmt.loc["Call GEX (Cr)", top1_call_gex] += " (R)"
        display_matrix_fmt.loc["Call GEX (Cr)", top2_call_gex] += " (R)"
        display_matrix_fmt.loc["Put GEX (Cr)", top1_put_gex] += " (S)"
        display_matrix_fmt.loc["Put GEX (Cr)", top2_put_gex] += " (S)"
    
        if top1_net_neg: display_matrix_fmt.loc["NET GEX (Cr)", top1_net_neg] += " (R)"
        if top2_net_neg: display_matrix_fmt.loc["NET GEX (Cr)", top2_net_neg] += " (R)"
        if top1_net_pos: display_matrix_fmt.loc["NET GEX (Cr)", top1_net_pos] += " (S)"
        if top2_net_pos: display_matrix_fmt.loc["NET GEX (Cr)", top2_net_pos] += " (S)"
    
        display_matrix_fmt.loc["Put OI (L)", top1_put_oi] += " (S)"
        display_matrix_fmt.loc["Put OI (L)", top2_put_oi] += " (S)"
        display_matrix_fmt.loc["Call OI (L)", top1_call_oi] += " (R)"
        display_matrix_fmt.loc["Call OI (L)", top2_call_oi] += " (R)"
    
        # Styler layout generation engine
        def style_matrix_cells(df_matrix):
            styles = pd.DataFrame('', index=df_matrix.index, columns=df_matrix.columns)
            
            if atm_strike in df_matrix.columns:
                styles.loc[:, atm_strike] = 'background-color: rgba(255, 170, 0, 0.15); border: 2px solid #ffaa00;'
    
            styles.loc["Call GEX (Cr)", top1_call_gex] = 'background-color: rgba(239, 68, 68, 0.6); color: white; font-weight: bold;'
            styles.loc["Call GEX (Cr)", top2_call_gex] = 'background-color: rgba(239, 68, 68, 0.35); color: white;'
            
            styles.loc["Put GEX (Cr)", top1_put_gex] = 'background-color: rgba(34, 197, 94, 0.6); color: white; font-weight: bold;'
            styles.loc["Put GEX (Cr)", top2_put_gex] = 'background-color: rgba(34, 197, 94, 0.35); color: white;'
            
            if top1_net_neg: styles.loc["NET GEX (Cr)", top1_net_neg] = 'background-color: rgba(139, 92, 246, 0.6); color: white; font-weight: bold;'
            if top2_net_neg: styles.loc["NET GEX (Cr)", top2_net_neg] = 'background-color: rgba(139, 92, 246, 0.35); color: white;'
            if top1_net_pos: styles.loc["NET GEX (Cr)", top1_net_pos] = 'background-color: rgba(34, 197, 94, 0.6); color: white; font-weight: bold;'
            if top2_net_pos: styles.loc["NET GEX (Cr)", top2_net_pos] = 'background-color: rgba(34, 197, 94, 0.35); color: white;'
            
            styles.loc["Put OI (L)", top1_put_oi] = 'background-color: rgba(59, 130, 246, 0.6); color: white; font-weight: bold;'
            styles.loc["Put OI (L)", top2_put_oi] = 'background-color: rgba(59, 130, 246, 0.35); color: white;'
            styles.loc["Call OI (L)", top1_call_oi] = 'background-color: rgba(245, 158, 11, 0.6); color: white; font-weight: bold;'
            styles.loc["Call OI (L)", top2_call_oi] = 'background-color: rgba(245, 158, 11, 0.35); color: white;'
            
            styles["TOTAL / NET"] = 'background-color: rgba(148, 163, 184, 0.15); font-weight: bold; border-left: 2px solid gray;'
            return styles
    
        st.markdown("""
            <style>
                /* Column Headers (Strikes) Styling */
                .stDataFrame th, [data-testid="stDataFrame"] div[role="row"] div[role="columnheader"] p {
                    font-weight: 800 !important;
                    color: #000000 !important;
                    font-size: 0.72rem !important;
                    background-color: rgba(241, 245, 249, 0.7) !important;
                }
                /* Row Headers (Metrics Label Column) Styling */
                [data-testid="stDataFrame"] div[role="rowheader"] p, [data-testid="stDataFrame"] div[role="rowheader"] {
                    font-weight: 800 !important;
                    color: #000000 !important;
                    font-size: 0.72rem !important;
                    background-color: rgba(241, 245, 249, 0.7) !important;
                }
                /* Grid Values Scaling */
                [data-testid="stDataFrame"] div[role="gridcell"] {
                    font-weight: 500;
                    font-size: 0.72rem !important;
                }
            </style>
        """, unsafe_allow_html=True)
    
        st.dataframe(display_matrix_fmt.style.apply(style_matrix_cells, axis=None), use_container_width=True)
        st.markdown("---")
        
        # ─── c. Cumulative GEX Profile — Dealer Hedging Pressure (Chart) ───
        st.subheader("Cumulative GEX Profile — Dealer Hedging Pressure")
        st.plotly_chart(plot_spot_gex_levels(gex_df, spot_price, gamma_levels, 500), use_container_width=True)
        st.markdown("---")
    
        # ─── d. 📝 Technical Reference Note ───
        st.markdown("### 📝 Technical Reference Note: GEX Matrix Trading Architecture")
        st.markdown("""
        The **Strike-by-Strike GEX & Positioning Matrix** processes open options interest parameters directly into 
        dealer hedging obligations. Because options market makers must sustain directional delta neutrality, their automated, 
        systematic hedging tasks establish strict friction zones and breakout corridors across the daily tape.
        
        * **The Short-Call GEX Wall:** Located at strikes displaying the highest negative (**-ve**) Call GEX values, 
            marked with the **`(R)`** resistance suffix. As the spot engine edges into this boundary, index gamma hits its peak slope and flattens. 
            Concurrently, Implied Volatility ($IV$) undergoes compression against institutional overhead paper. This environment halts the dealers' 
            need to purchase additional index futures to hedge, causing upward momentum to break down or compress.
        * **The Long-Put GEX Wall:** Located at strikes displaying the highest positive (**+ve**) Put GEX values, 
            marked with the **`(S)`** support suffix. As the spot engine slides downward into these nodes, index options transition into At-The-Money structures. 
            Because dealers carry net-long inventory across these structures, their underlying systemic delta builds directional exposure. 
            To level out books, dealers fire size buy programs in the cash or futures asset class, establishing a structural floor.
        """)
        st.markdown("---")
    
        # ─── e. Summary Cheat Sheet for Intraday Monitoring ───
        st.markdown("### 🏁 Summary Cheat Sheet for Intraday Monitoring")
        st.markdown("""
        | MATRIX COONDITIONS | STRUCTURAL STATE | MARKET VELOCITY IMPACT | TACTICAL ACTION |
        | :--- | :--- | :--- | :--- |
        | **Spot in unhighlighted matrix spaces** | Minimal Dealer Friction | Elevated velocity; chart slices through zones cleanly | Avoid opening directional entries within empty pockets. |
        | **Spot tracking into Red `(R)` Call GEX Wall** | Gamma Deceleration / $IV$ Crush | Upward momentum gridlocks near the strike | Exit long momentum frames; scale into structural credit spreads above. |
        | **Spot clearing cleanly ABOVE Red `(R)` Call GEX Wall** | Short-Call Gamma Squeeze | Aggressive, non-linear vertical melt-up | Stop out overhead shorts immediately; trade long via ATM Call instruments. |
        | **Spot trending into Green `(S)` Put GEX Wall** | Negative Gamma Acceleration | Fear parameters expand; downward run speeds up | Keep target short structures running until the exact wall coordinates are hit. |
        | **Spot landing on Green `(S)` Put GEX Wall** | Institutional Buy Program | Immediate downward halt; volume blocks print | Flat intraday shorts; observe structural candle wick patterns for trend reversal. |
        """)

    with tab2:
        st.subheader("Open Interest & Volume Analysis")
        st.plotly_chart(plot_oi_analysis(gex_df, spot_price), use_container_width=True)
        st.plotly_chart(plot_iv_smile(gex_df), use_container_width=True)
        st.markdown("---")
        st.subheader("📊 OI Change Heatmap — Top 8 Movers")
        
        # Get OI change data from original options_df
        try:
            import plotly.graph_objects as go
            
            options_df = st.session_state.options_df
            
            # Separate calls and puts and get OI changes
            calls_oi_change = options_df[options_df['type'] == 'CE'].groupby('strike').agg({
                'oi_change': 'sum',
                'strike': 'first'
            }).reset_index(drop=True).drop_duplicates(subset=['strike'])
            
            puts_oi_change = options_df[options_df['type'] == 'PE'].groupby('strike').agg({
                'oi_change': 'sum',
                'strike': 'first'
            }).reset_index(drop=True).drop_duplicates(subset=['strike'])
            
            # Get top 2 gainers
            top_call_oi = calls_oi_change.nlargest(4, 'oi_change')
            top_put_oi = puts_oi_change.nlargest(4, 'oi_change')
            
            fig_oi = go.Figure()
            
            # Call OI changes (red)
            if not top_call_oi.empty:
                fig_oi.add_trace(go.Bar(
                    y=[f"Call ₹{int(s)}" for s in top_call_oi['strike']],
                    x=top_call_oi['oi_change'],
                    orientation='h',
                    name='Call OI Change',
                    marker=dict(
                        color=top_call_oi['oi_change'].values,
                        colorscale='Reds',
                        showscale=False,
                        line=dict(width=1, color='#ef4444')
                    ),
                    text=[f"{v/1e5:.2f}" for v in top_call_oi['oi_change']],
                    textposition='outside',
                    hovertemplate='<b>Call Strike ₹%{label}</b><br>OI Change: %{text}<extra></extra>'
                ))
            
            # Put OI changes (green)
            if not top_put_oi.empty:
                fig_oi.add_trace(go.Bar(
                    y=[f"Put ₹{int(s)}" for s in top_put_oi['strike']],
                    x=top_put_oi['oi_change'],
                    orientation='h',
                    name='Put OI Change',
                    marker=dict(
                        color=top_put_oi['oi_change'].values,
                        colorscale='Greens',
                        showscale=False,
                        line=dict(width=1, color='#22c55e')
                    ),
                    text=[f"{v/1e5:.2f}" for v in top_put_oi['oi_change']],
                    textposition='outside',
                    hovertemplate='<b>Put Strike ₹%{label}</b><br>OI Change: %{text}<extra></extra>'
                ))
            
            fig_oi.update_layout(
                title="🔴 Top 4 Call + 🟢 Top 4 Put OI Gainers (Current Session)",
                barmode='group',
                template='plotly_dark',
                height=320,
                xaxis_title='OI Change in Lacs (Contracts)',
                yaxis_title='Strike Level',
                showlegend=True,
                hovermode='y unified',
                margin=dict(l=120, r=120, t=60, b=40)
            )
            
            st.plotly_chart(fig_oi, use_container_width=True)
            
        except Exception as e:
            st.warning(f"⚠️ Could not load OI change data: {str(e)}")
        
        st.markdown("---")
        v1,v2,v3 = st.columns(3)
        cv = gamma_levels.get("total_call_volume",0)
        pv = gamma_levels.get("total_put_volume",0)
        v1.metric("Call Volume", f"{cv:,.0f}")
        v2.metric("Put Volume",  f"{pv:,.0f}")
        v3.metric("Volume PCR",  f"{pv/cv:.3f}" if cv>0 else "—")

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

    # TAB 4 — MenthorQ-Style GEX Chart  (replace the existing tab4 block)
    with tab4:
 
        # ── MenthorQ main chart ───────────────────────────────────────────────
        st.subheader("📊 Net GEX Profile — Dealer Positioning")
 
        fig_mq = plot_menthorq_gex(
            gex_df       = gex_df,
            spot_price   = spot_price,
            gamma_levels = gamma_levels,
            symbol       = symbol,
        )
        st.plotly_chart(fig_mq, use_container_width=True)
 
        # ── Auto-generated analysis text ──────────────────────────────────────
        analysis_lines = generate_gex_analysis(
            gex_df       = gex_df,
            spot_price   = spot_price,
            gamma_levels = gamma_levels,
            symbol       = symbol,
        )
 
        # render as a styled box matching MenthorQ's bottom summary
        list_items = "".join(f"<li style='margin:6px 0; font-size:13px; color:#E2E8F0; line-height:1.55;'>{line}</li>" for line in analysis_lines)
        analysis_html = f"<ul style='margin:0; padding-left:20px;'>{list_items}</ul>"
        
        st.markdown(f"""
          <div style='
              background:rgba(15,23,42,0.85);
              border:1px solid rgba(100,116,139,0.35);
              border-left:3px solid #EAB308;
              border-radius:6px;
              padding:14px 18px;
              margin-top:4px;
              font-family:sans-serif;
          '>
              {analysis_html}
          </div>""", unsafe_allow_html=True)
 
        st.markdown("---")
 
        # ── Quick-reference metrics under the chart ───────────────────────────
        qa, qb, qc, qd, qe = st.columns(5)
        qa.metric("🚧 Call Wall",   f"₹{gamma_levels.get('max_call_oi_strike', spot_price):,.0f}",
                  delta=f"{(gamma_levels.get('max_call_oi_strike', spot_price) - spot_price):+.0f}")
        qb.metric("🛡️ Put Wall",    f"₹{gamma_levels.get('max_put_oi_strike', spot_price):,.0f}",
                  delta=f"{(gamma_levels.get('max_put_oi_strike', spot_price) - spot_price):+.0f}")
        qc.metric("🔄 HVL / Flip",  f"₹{gamma_levels.get('gamma_flip', spot_price):,.0f}",
                  delta=f"{(gamma_levels.get('gamma_flip', spot_price) - spot_price):+.0f}")
        qd.metric("📊 Net GEX",     format_number(gamma_levels.get('total_gex', 0)))
        qe.metric("📐 PCR",         f"{atm_pcr:.2f}")
 
        st.markdown("---")
 
        # ── Gamma Confusion Matrix (kept below the main chart) ────────────────
        with st.expander("📋 Gamma Confusion Matrix", expanded=False):
            import plotly.graph_objects as _go
 
            c_gex      = gex_df['call_gex'].sum()
            p_gex      = gex_df['put_gex'].sum()
            call_state = "+ve" if c_gex  > 0 else "-ve"
            put_state  = "+ve" if p_gex  > 0 else "-ve"
            net_state  = "+ve" if net_gex > 0 else "-ve"
 
            matrix_data = [
                {
                    "Call Γ": "+ve", "Put Γ": "+ve", "Net GEX": "+ve",
                    "Nature": "Ultra-Stable",
                    "Dealer Logic": "Long both; volatility suppressed.",
                },
                {
                    "Call Γ": "+ve", "Put Γ": "-ve", "Net GEX": "+ve",
                    "Nature": "Bullish Support",
                    "Dealer Logic": "Long Calls > Short Puts; floor exists.",
                },
                {
                    "Call Γ": "+ve", "Put Γ": "-ve", "Net GEX": "-ve",
                    "Nature": "Volatility Trap",
                    "Dealer Logic": "Short Puts dominate; rapid sell-off risk.",
                },
                {
                    "Call Γ": "-ve", "Put Γ": "+ve", "Net GEX": "+ve",
                    "Nature": "Bearish Resistance",
                    "Dealer Logic": "Short Calls cap upside.",
                },
                {
                    "Call Γ": "-ve", "Put Γ": "+ve", "Net GEX": "-ve",
                    "Nature": "The Squeeze",
                    "Dealer Logic": "Short Calls dominate; breakout triggers melt-up.",
                },
                {
                    "Call Γ": "-ve", "Put Γ": "-ve", "Net GEX": "-ve",
                    "Nature": "Maximum Chaos",
                    "Dealer Logic": "Short both; dealers amplify moves.",
                },
            ]
 
            matrix_df = pd.DataFrame(matrix_data)
 
            def _hl_active(row):
                if (row["Call Γ"] == call_state
                        and row["Put Γ"] == put_state
                        and row["Net GEX"] == net_state):
                    return ["background-color:rgba(234,179,8,0.28)"] * len(row)
                return [""] * len(row)
 
            st.table(matrix_df.style.apply(_hl_active, axis=1))
 
            st.markdown("---")
 
            

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
            if pcr > 1.2:   st.error("🐻 Bearish PCR")
            elif pcr < 0.8: st.error("🐂 Bullish PCR")
            else:            st.info("➡️ Neutral PCR")
        with ra2:
            st.markdown("##### Key Levels")
            st.write(f"**Max Pain:**   ₹{max_pain:,.0f}")
            st.write(f"**Gamma Flip:** ₹{gamma_flip:,.0f}")
            st.write(f"**Call Wall:**  ₹{max_call_oi_strike:,.0f}")
            st.write(f"**Put Wall:**   ₹{max_put_oi_strike:,.0f}")

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

        atm_strikes = (gex_df.iloc[
            (gex_df["strike"]-spot_price).abs().argsort()[:3]
        ]["strike"].values)

        def _hl(row):
            styles = [""] * len(row)
            strike = row["Strike"]
            lo, hi = spot_price * 0.97, spot_price * 1.03
            in_range = lo <= strike <= hi
            for i, col in enumerate(disp.columns):
                if col.startswith("C-"):
                    if col == "C-LTP" and row["C-LTP"] < 10 and in_range:
                        styles[i] = "background-color:rgba(255,255,0,0.6);color:black;font-weight:bold"
                    elif strike < spot_price:
                        styles[i] = "background-color:rgba(34,197,94,0.15)"
                if col.startswith("P-"):
                    if col == "P-LTP" and row["P-LTP"] < 10 and in_range:
                        styles[i] = "background-color:rgba(255,255,0,0.6);color:black;font-weight:bold"
                    elif strike > spot_price:
                        styles[i] = "background-color:rgba(239,68,68,0.15)"
            if strike in atm_strikes:
                styles[0] = "background-color:rgba(255,165,0,0.4);font-weight:bold"
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
        ist_now = datetime.now(IST)
        st.download_button(
            "📥 Download CSV", gex_df.to_csv(index=False),
            file_name=f"gex_{symbol}_{st.session_state.selected_expiry}_"
                      f"{ist_now.strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv")

    with tab7:
        st.subheader("ℹ️ Guide")
        st.markdown(f"""
### ⚡ Live Engine — How it works

| Layer | Interval | What happens |
|-------|----------|--------------|
| **Spot tick** | every 5 s | `kite.ltp()` → new spot → recalculate GEX from stored chain (instant) |
| **Chain refresh** | configurable (60–600 s) | `kite.quote()` → full chain re-fetch → rebuild GEX from scratch |

**Why two speeds?**  
A full chain fetch hits 500+ Kite quote endpoints in chunks.  
A spot LTP call is a single lightweight request.  
GEX levels shift when OI changes (slowly); GEX *magnitude* shifts when spot moves (every tick).

### Expiry Calendar (NSE)
| Index | Weekly / Monthly | Expiry Day | Min. Lot Qty |
|-------|--------|------------| ------------|
| NIFTY | ✅ / ✅ | Tuesday | 65 | 
| BANKNIFTY | ❌ / ✅ | Last Tuesday | 30 |
| FINNIFTY | ❌ / ✅ | Last Tuesday | 60 |
| MIDCPNIFTY | ❌ / ✅ | Last Tuesday | 120 |

### Debug: Why is Kite fetch failing?
1. Token expires at **6:00 AM daily** — reconnect each morning
2. Run 🔍 Debug Connection in sidebar
3. Clear Instrument Cache and retry if stale
4. Market closed → `/quote` may return 0 OI / LTP

⚠️ Educational only. Not financial advice.
        """)

# ── welcome screen ────────────────────────────────────────────────────────────
else:
    st.info("👈 Authenticate Kite, fetch option chain, then click **🟢 GO LIVE**.")
    c1,c2 = st.columns(2)
    for col, sym, grad in [
        (c1,"NIFTY",     "linear-gradient(135deg,#667eea,#764ba2)"),
        (c2,"BANKNIFTY", "linear-gradient(135deg,#f093fb,#f5576c)"),
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

# ── footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style='text-align:center;color:#888;padding:1rem'>
  <b>Professional GEX Terminal — Live Engine Edition</b><br>
  5s spot ticks · Configurable chain refresh · Kite Connect <br>
  <span style='font-size:.75rem'>⚠️ Educational only. Not financial advice.</span>
</div>""", unsafe_allow_html=True)
