"""
Professional GEX Terminal v3.0
Advanced Options Analytics – Kite Connect v3, NSE Live, Full Greeks Suite

Key changes in this version
----------------------------
* Spot price refreshes independently via /quote/ltp (no full chain reload needed)
* BANKNIFTY shown as monthly-only; weekly tab disabled automatically
* Expiry list and lot size always pulled from Kite instruments (zero hardcoding)
* Weekly/monthly toggle hidden for symbols that don't have weekly expiry
* All instrument metadata derived from Kite – no numbers in app.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

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
    get_strike_interval,
    has_weekly_expiry,
    calculate_time_to_expiry,
)
from modules.trade_recommendations import generate_trade_recommendations
from modules.kite_connector import KiteManager, init_kite_session

try:
    import config as _cfg
    KITE_API_KEY    = _cfg.KITE_API_KEY
    KITE_API_SECRET = _cfg.KITE_API_SECRET
    SPOT_REFRESH    = _cfg.SPOT_REFRESH_INTERVAL
    CHAIN_REFRESH   = _cfg.AUTO_REFRESH_INTERVAL
    RFR_DEFAULT     = _cfg.DEFAULT_RISK_FREE_RATE
    STRIKE_RANGE_DEFAULT = _cfg.DEFAULT_STRIKE_RANGE_PCT
except Exception:
    KITE_API_KEY = KITE_API_SECRET = ""
    SPOT_REFRESH, CHAIN_REFRESH = 5, 15
    RFR_DEFAULT  = 0.07
    STRIKE_RANGE_DEFAULT = 10

# ---------------------------------------------------------------------------
# Page setup
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
    font-size:2.8rem; font-weight:bold;
    background:linear-gradient(90deg,#1f77b4,#ff7f0e);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    text-align:center; margin-bottom:0.5rem;
}
.sub-header { text-align:center; color:#888; font-size:1.1rem; margin-bottom:1.5rem; }
.live-dot {
    display:inline-block; width:10px; height:10px;
    background:#22c55e; border-radius:50%; margin-right:6px;
    animation:pulse 2s infinite;
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.spot-box {
    background:linear-gradient(135deg,#1e3a5f,#0f2027);
    border:1px solid #334155; border-radius:10px;
    padding:1rem; text-align:center; color:white;
}
.stTabs [data-baseweb="tab"] {
    height:46px; background:#f0f2f6;
    border-radius:5px 5px 0 0; padding:8px 18px; font-weight:600;
}
.stTabs [aria-selected="true"] {
    background:linear-gradient(135deg,#667eea,#764ba2); color:white;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "data_loaded":        False,
    "options_df":         None,
    "spot_price":         None,
    "spot_ohlc":          None,
    "last_update":        None,
    "last_spot_update":   None,
    "gex_df":             None,
    "gamma_levels":       None,
    "kite_authenticated": False,
    "kite_manager":       None,
    "lot_size":           None,
    "strike_interval":    None,
    "selected_expiry":    None,
    "selected_symbol":    "NIFTY",
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown('<p class="main-header">📊 Professional GEX Terminal</p>',
            unsafe_allow_html=True)
st.markdown('<p class="sub-header">Kite Connect v3 • Real-Time Greeks • Intelligent Signals</p>',
            unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuration")

    # ── Data source ──────────────────────────────────────────────────────────
    st.subheader("📡 Data Source")
    data_source = st.radio(
        "Source:",
        ["NSE Live (nselib)", "Kite Connect", "Sample Data"],
    )

    # ── Kite auth ────────────────────────────────────────────────────────────
    if data_source == "Kite Connect":
        st.markdown("---")
        st.subheader("🔐 Kite Authentication")
        if not st.session_state.kite_authenticated:
            api_key    = st.text_input("API Key",    value=KITE_API_KEY,    type="password")
            api_secret = st.text_input("API Secret", value=KITE_API_SECRET, type="password")
            if st.button("🔗 Connect to Kite", type="primary"):
                if api_key and api_secret:
                    km = KiteManager(api_key, api_secret)
                    url = km.get_login_url()
                    st.info(f"Login URL: {url}")
                    req_token = st.text_input("Paste Request Token:")
                    if req_token and km.set_access_token(req_token):
                        st.session_state.kite_manager       = km
                        st.session_state.kite_authenticated = True
                        st.rerun()
                else:
                    st.error("Enter API Key and Secret first.")
        else:
            st.success("✅ Kite Connected")
            if st.button("Disconnect"):
                st.session_state.kite_authenticated = False
                st.session_state.kite_manager       = None
                st.rerun()

    st.markdown("---")
    kite_mgr = (st.session_state.kite_manager
                if data_source == "Kite Connect" else None)

    # ── Symbol ───────────────────────────────────────────────────────────────
    symbol = st.selectbox(
        "📈 Index",
        ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"],
    )
    st.session_state.selected_symbol = symbol

    # ── Dynamic lot size & strike interval from Kite ─────────────────────────
    lot_size        = get_lot_size(symbol, kite_mgr)
    strike_interval = get_strike_interval(symbol, None, kite_mgr)
    st.session_state.lot_size        = lot_size
    st.session_state.strike_interval = strike_interval

    src_label = "🔗 Kite" if kite_mgr else "📋 estimate"
    col_a, col_b = st.columns(2)
    col_a.metric("📦 Lot Size",        f"{lot_size}",              help=src_label)
    col_b.metric("📏 Strike Interval", f"₹{strike_interval:.0f}", help=src_label)

    # ── Expiry type (hidden/forced for BANKNIFTY) ─────────────────────────────
    st.markdown("---")
    symbol_has_weekly = has_weekly_expiry(symbol, kite_mgr)

    if symbol_has_weekly:
        expiry_type_label = st.radio(
            "📅 Expiry Type",
            ["Weekly", "Monthly"],
            help="BANKNIFTY has monthly expiry only on NSE.",
        )
        expiry_type = "weekly" if expiry_type_label == "Weekly" else "monthly"
    else:
        st.info(f"📅 {symbol}: Monthly expiry only (no weekly on NSE)")
        expiry_type = "monthly"

    # ── Expiry selector ───────────────────────────────────────────────────────
    available_expiries = get_expiries_for_symbol(symbol, kite_mgr, expiry_type)
    if not available_expiries:
        available_expiries = [get_next_expiry_for_symbol(symbol, expiry_type)]

    expiry_date = st.selectbox(
        "Select Expiry",
        available_expiries,
        index=0,
        help="From Kite instruments" if kite_mgr else "Computed from NSE rules",
    )
    st.caption(
        f"Source: {'🔗 Kite instruments' if kite_mgr else '📋 NSE calendar rules'}"
    )
    st.session_state.selected_expiry = expiry_date

    # ── Analysis parameters ───────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📍 Parameters")

    strike_range = st.slider(
        "Strike Range (%)", min_value=5, max_value=25,
        value=STRIKE_RANGE_DEFAULT, step=1,
        help="±% around spot to include",
    )
    risk_free_rate = st.number_input(
        "Risk-Free Rate (%)",
        min_value=0.0, max_value=15.0,
        value=round(RFR_DEFAULT * 100, 1), step=0.1,
    ) / 100

    # ── Spot price refresh (lightweight /quote/ltp) ───────────────────────────
    st.markdown("---")
    st.subheader("💹 Spot Price")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Refresh Spot", use_container_width=True):
            with st.spinner("Fetching LTP..."):
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
                    # Recalculate GEX with new spot if chain already loaded
                    if (st.session_state.data_loaded
                            and st.session_state.options_df is not None):
                        df_f = filter_strikes(
                            st.session_state.options_df,
                            new_spot, strike_range
                        )
                        gex_df = calculate_gex(
                            df_f, new_spot, expiry_date, risk_free_rate
                        )
                        st.session_state.gex_df       = gex_df
                        st.session_state.gamma_levels = find_gamma_levels(gex_df, new_spot)
                    st.success(f"₹{new_spot:,.2f}")
                else:
                    st.warning("Could not fetch spot.")

    with col2:
        enable_spot_refresh = st.checkbox("Auto", value=False,
                                           help="Auto-refresh spot price")
    if enable_spot_refresh and kite_mgr:
        st_autorefresh(
            interval=SPOT_REFRESH * 1000,
            limit=None,
            key="spot_auto_refresh",
        )

    # ── Full data fetch ───────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🔄 Option Chain")

    enable_chain_refresh = st.checkbox("Auto-refresh chain", value=False)
    if enable_chain_refresh:
        chain_interval = st.slider(
            "Interval (s)", min_value=10, max_value=120,
            value=CHAIN_REFRESH, step=5,
        )
        st_autorefresh(
            interval=chain_interval * 1000,
            limit=None,
            key="chain_auto_refresh",
        )

    if st.button("📥 Fetch Option Chain", type="primary", use_container_width=True):
        _source_key = (
            "kite"   if data_source == "Kite Connect" else
            "nselib" if data_source == "NSE Live (nselib)" else
            "sample"
        )
        with st.spinner(f"Fetching {symbol} chain for {expiry_date}..."):
            df, spot = None, None
            fetch_ok = False

            if _source_key == "kite":
                if not kite_mgr:
                    st.error("Kite not connected.")
                else:
                    df, spot = fetch_option_chain(
                        symbol, expiry_date, "kite", kite_mgr, risk_free_rate
                    )
                    fetch_ok = df is not None and not df.empty and spot

            elif _source_key == "nselib":
                df, spot = fetch_option_chain(
                    symbol, expiry_date, "nselib", None, risk_free_rate
                )
                fetch_ok = df is not None and not df.empty and spot

            else:   # sample
                live_spot = get_live_spot_price(symbol, "nselib")
                df, spot  = generate_sample_data(symbol, live_spot, expiry_date, kite_mgr)
                fetch_ok  = True

            # Fallback to sample if live failed
            if not fetch_ok and _source_key != "sample":
                st.warning("⚠️ Live fetch failed – loading sample data.")
                live_spot = get_live_spot_price(symbol, "nselib")
                df, spot  = generate_sample_data(symbol, live_spot, expiry_date, kite_mgr)

            if df is not None and not df.empty and spot:
                df_filtered = filter_strikes(df, spot, strike_range)
                if df_filtered.empty:
                    st.warning(
                        f"No strikes within ±{strike_range}% – widening to ±15%."
                    )
                    df_filtered = filter_strikes(df, spot, 15)

                try:
                    gex_df       = calculate_gex(df_filtered, spot, expiry_date, risk_free_rate)
                    gamma_levels = find_gamma_levels(gex_df, spot)

                    st.session_state.options_df      = df
                    st.session_state.spot_price      = spot
                    st.session_state.gex_df          = gex_df
                    st.session_state.gamma_levels    = gamma_levels
                    st.session_state.data_loaded     = True
                    st.session_state.last_update     = datetime.now()
                    st.session_state.last_spot_update= datetime.now()

                    # Refresh lot size & interval now that we have expiry
                    st.session_state.lot_size = get_lot_size(symbol, kite_mgr)
                    st.session_state.strike_interval = get_strike_interval(
                        symbol, expiry_date, kite_mgr
                    )
                except Exception as exc:
                    st.error(f"GEX calculation error: {exc}")
            else:
                st.error("No data available. Check connection / expiry.")

    # ── Status panel ─────────────────────────────────────────────────────────
    if st.session_state.data_loaded:
        st.markdown("---")
        spot = st.session_state.spot_price
        st.markdown(f'<span class="live-dot"></span>**{symbol}**', unsafe_allow_html=True)
        if spot:
            st.metric("Spot", f"₹{spot:,.2f}")
        st.caption(f"📅 Expiry: {st.session_state.selected_expiry}")
        st.caption(f"📦 Lot: {st.session_state.lot_size}  |  📏 Interval: ₹{st.session_state.strike_interval:.0f}")
        if st.session_state.last_update:
            st.caption(f"🕐 Chain: {st.session_state.last_update.strftime('%H:%M:%S')}")
        if st.session_state.last_spot_update:
            st.caption(f"💹 Spot: {st.session_state.last_spot_update.strftime('%H:%M:%S')}")
        try:
            mkt = get_market_status()
            e   = "🟢" if "Open" in mkt.get("market_state", "") else "🔴"
            st.caption(f"{e} {mkt['market_state']}")
        except Exception:
            pass

# ===========================================================================
# Main content
# ===========================================================================
if st.session_state.data_loaded and st.session_state.gex_df is not None:

    spot_price   = st.session_state.spot_price
    gex_df       = st.session_state.gex_df
    gamma_levels = st.session_state.gamma_levels
    lot_size     = st.session_state.lot_size
    si           = st.session_state.strike_interval   # strike interval

    pcr        = gamma_levels.get("pcr", 1.0)
    max_pain   = gamma_levels.get("max_pain", spot_price)
    gamma_flip = gamma_levels.get("gamma_flip", spot_price)
    net_gex    = gamma_levels.get("total_gex", 0)
    max_call_oi_strike = gamma_levels.get("max_call_oi_strike", spot_price)
    max_put_oi_strike  = gamma_levels.get("max_put_oi_strike", spot_price)

    # ── Spot price banner ─────────────────────────────────────────────────────
    st.markdown("---")
    ohlc = st.session_state.spot_ohlc or {}
    ba, bb, bc, bd, be = st.columns(5)
    ba.metric("💰 Spot",  f"₹{spot_price:,.2f}")
    bb.metric("📈 Open",  f"₹{ohlc.get('open', 0):,.2f}"  if ohlc else "—")
    bc.metric("⬆ High",   f"₹{ohlc.get('high', 0):,.2f}"  if ohlc else "—")
    bd.metric("⬇ Low",    f"₹{ohlc.get('low', 0):,.2f}"   if ohlc else "—")
    be.metric("🔚 Prev",  f"₹{ohlc.get('close', 0):,.2f}" if ohlc else "—")

    if ohlc:
        st.caption("OHLC from Kite /quote/ohlc")

    # ── Key metrics row ───────────────────────────────────────────────────────
    st.markdown("---")
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    pcr_icon = "🐻" if pcr > 1.2 else "🐂" if pcr < 0.8 else "➡️"
    c1.metric(f"{pcr_icon} PCR",       f"{pcr:.3f}")
    c2.metric("🎯 Max Pain",   f"₹{max_pain:,.0f}",
              delta=f"{max_pain - spot_price:+.0f}")
    c3.metric("🔄 Gamma Flip", f"₹{gamma_flip:,.0f}",
              delta=f"{gamma_flip - spot_price:+.0f}")
    c4.metric("📊 GEX Regime",
              "🟢 Positive" if net_gex > 0 else "🔴 Negative")
    c5.metric("💹 Net GEX",    format_number(net_gex))
    c6.metric("📦 Lot Size",   f"{lot_size}",
              help="From Kite instruments" if st.session_state.kite_manager else "Estimate")

    st.markdown("---")
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("📈 Call OI",          f"{gamma_levels.get('total_call_oi', 0):,.0f}")
    d2.metric("📉 Put OI",           f"{gamma_levels.get('total_put_oi', 0):,.0f}")
    d3.metric("🚧 Max Call Strike",  f"₹{max_call_oi_strike:,.0f}")
    d4.metric("🛡️ Max Put Strike",   f"₹{max_put_oi_strike:,.0f}")

    # Context bar
    st.info(
        f"**{symbol}** · Lot {lot_size} · Interval ₹{si:.0f} · "
        f"Expiry {st.session_state.selected_expiry} · "
        f"Spot ₹{spot_price:,.2f}"
    )

    # ── Tabs ─────────────────────────────────────────────────────────────────
    st.markdown("---")
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 GEX", "📈 OI & Volume", "🎲 Greeks",
        "🎯 Signals", "📋 Chain", "ℹ️ Guide",
    ])

    # ── GEX ──────────────────────────────────────────────────────────────────
    with tab1:
        st.subheader("Gamma Exposure Profile")
        st.plotly_chart(
            plot_gex_profile(gex_df, spot_price, gamma_levels),
            use_container_width=True,
        )
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### Key Levels")
            atm = get_atm_strike(spot_price, si)
            support    = gamma_levels.get("support", "N/A")
            resistance = gamma_levels.get("resistance", "N/A")
            st.write(f"**ATM Strike:** ₹{atm:,.0f}")
            st.write(f"**Support (max +GEX):** "
                     f"{'₹{:,.0f}'.format(support) if isinstance(support, (int,float)) else support}")
            st.write(f"**Resistance (max –GEX):** "
                     f"{'₹{:,.0f}'.format(resistance) if isinstance(resistance, (int,float)) else resistance}")
            st.write(f"**Gamma Flip:** ₹{gamma_flip:,.0f}")
            st.write(f"**Max Pain:** ₹{max_pain:,.0f}")
        with c2:
            st.markdown("##### GEX Summary")
            st.write(f"**Call GEX:** {format_number(gex_df['call_gex'].sum())}")
            st.write(f"**Put GEX:**  {format_number(gex_df['put_gex'].sum())}")
            st.write(f"**Net GEX:**  {format_number(net_gex)}")
            st.write(f"**Above Spot:** {format_number(gamma_levels.get('net_gex_above_spot', 0))}")
            st.write(f"**Below Spot:** {format_number(gamma_levels.get('net_gex_below_spot', 0))}")

        st.markdown("---")
        st.subheader("Net GEX vs Spot Movement")
        st.plotly_chart(
            plot_spot_gex_levels(gex_df, spot_price, gamma_levels, 500),
            use_container_width=True,
        )

    # ── OI & Volume ──────────────────────────────────────────────────────────
    with tab2:
        st.subheader("Open Interest & Volume Analysis")
        st.plotly_chart(plot_oi_analysis(gex_df, spot_price), use_container_width=True)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### PCR by Strike")
            st.plotly_chart(plot_pcr_analysis(gex_df), use_container_width=True)
        with c2:
            st.markdown("##### Volatility Smile")
            st.plotly_chart(plot_iv_smile(gex_df), use_container_width=True)
        st.markdown("---")
        v1, v2, v3 = st.columns(3)
        cv = gamma_levels.get("total_call_volume", 0)
        pv = gamma_levels.get("total_put_volume", 0)
        v1.metric("Call Volume", f"{cv:,.0f}")
        v2.metric("Put Volume",  f"{pv:,.0f}")
        v3.metric("Volume PCR",  f"{pv/cv:.3f}" if cv > 0 else "—")

    # ── Greeks ───────────────────────────────────────────────────────────────
    with tab3:
        st.subheader("Greeks Analysis")
        greek = st.selectbox("Greek:", ["Gamma", "Delta", "Vega", "Theta", "Rho"])
        st.plotly_chart(
            plot_greeks_heatmap(gex_df, greek.lower()),
            use_container_width=True,
        )
        st.markdown("---")
        st.subheader("ATM Greeks")
        atm_idx = (gex_df["strike"] - spot_price).abs().idxmin()
        ar      = gex_df.loc[atm_idx]
        c1, c2  = st.columns(2)
        with c1:
            st.markdown("##### Call (ATM)")
            for g, v in [("Delta", "call_delta"), ("Gamma", "call_gamma"),
                          ("Vega",  "call_vega"),  ("Theta", "call_theta"),
                          ("Rho",   "call_rho")]:
                st.write(f"**{g}:** {ar[v]:.5f}")
            st.write(f"**Theo:** ₹{ar['call_theo']:.2f}  |  **LTP:** ₹{ar['call_ltp']:.2f}")
        with c2:
            st.markdown("##### Put (ATM)")
            for g, v in [("Delta", "put_delta"), ("Gamma", "put_gamma"),
                          ("Vega",  "put_vega"),  ("Theta", "put_theta"),
                          ("Rho",   "put_rho")]:
                st.write(f"**{g}:** {ar[v]:.5f}")
            st.write(f"**Theo:** ₹{ar['put_theo']:.2f}  |  **LTP:** ₹{ar['put_ltp']:.2f}")
        st.markdown("---")
        st.subheader("Portfolio Exposure")
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("ΔEX", format_number(gex_df["total_dex"].sum()))
        e2.metric("ΓEX", format_number(gex_df["total_gex"].sum()))
        e3.metric("νEX", f"{gex_df['total_vex'].sum():,.0f}")
        e4.metric("ΘEX/day", format_number(gex_df["total_tex"].sum()))

    # ── Trade Signals ─────────────────────────────────────────────────────────
    with tab4:
        st.subheader("🎯 Intelligent Trade Signals")
        recs = generate_trade_recommendations(gex_df, spot_price, gamma_levels)
        if recs:
            for i, r in enumerate(recs, 1):
                icon = {"HIGH": "🔴", "MEDIUM": "🟡", "INFO": "🔵"}.get(
                    r["confidence"], "⚪"
                )
                with st.expander(
                    f"{icon} {r['signal']} — {r['strategy']}",
                    expanded=(i <= 3),
                ):
                    st.markdown(f"**Confidence:** `{r['confidence']}`")
                    st.markdown(f"**Analysis:** {r['reasoning']}")
                    st.markdown(f"**Action:** {r['action']}")
        else:
            st.info("No strong signals – market appears balanced.")

        st.markdown("---")
        st.subheader("Risk Assessment")
        ra1, ra2 = st.columns(2)
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

    # ── Option Chain table ───────────────────────────────────────────────────
    with tab5:
        st.subheader("Options Chain with Greeks")

        cols_ordered = [
            "strike",
            "call_oi", "call_volume", "call_ltp", "call_iv",
            "call_delta", "call_gamma", "call_vega", "call_theta",
            "put_theta", "put_vega", "put_gamma", "put_delta",
            "put_iv", "put_ltp", "put_volume", "put_oi",
        ]
        display = gex_df[[c for c in cols_ordered if c in gex_df.columns]].copy()
        display.columns = [
            "Strike",
            "C-OI", "C-Vol", "C-LTP", "C-IV%",
            "C-Δ", "C-Γ", "C-ν", "C-Θ",
            "P-Θ", "P-ν", "P-Γ", "P-Δ",
            "P-IV%", "P-LTP", "P-Vol", "P-OI",
        ][:len(display.columns)]

        atm_strikes = (
            gex_df.iloc[(gex_df["strike"] - spot_price).abs().argsort()[:3]]
            ["strike"].values
        )

        def _highlight(row):
            return (
                ["background-color:rgba(255,165,0,0.3)"] * len(row)
                if row["Strike"] in atm_strikes
                else [""] * len(row)
            )

        fmt = {
            "C-OI": "{:,.0f}", "P-OI": "{:,.0f}",
            "C-Vol": "{:,.0f}", "P-Vol": "{:,.0f}",
            "C-LTP": "{:.2f}", "P-LTP": "{:.2f}",
            "C-IV%": "{:.2f}", "P-IV%": "{:.2f}",
            "C-Δ": "{:.4f}", "P-Δ": "{:.4f}",
            "C-Γ": "{:.6f}", "P-Γ": "{:.6f}",
            "C-ν": "{:.4f}", "P-ν": "{:.4f}",
            "C-Θ": "{:.2f}", "P-Θ": "{:.2f}",
        }
        valid_fmt = {k: v for k, v in fmt.items() if k in display.columns}

        st.dataframe(
            display.style.apply(_highlight, axis=1).format(valid_fmt),
            height=500,
            use_container_width=True,
        )
        csv = gex_df.to_csv(index=False)
        st.download_button(
            "📥 Download CSV", csv,
            file_name=(
                f"gex_{symbol}_{st.session_state.selected_expiry}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            ),
            mime="text/csv",
        )

    # ── Guide ─────────────────────────────────────────────────────────────────
    with tab6:
        st.subheader("ℹ️ Guide")
        st.markdown(f"""
### Expiry Calendar (NSE – as at May 2025)

| Index        | Weekly Expiry | Day       |
|--------------|---------------|-----------|
| NIFTY        | ✅ Yes        | Thursday  |
| BANKNIFTY    | ❌ No (monthly only) | Last Wednesday |
| FINNIFTY     | ✅ Yes        | Tuesday   |
| MIDCPNIFTY   | ✅ Yes        | Monday    |

When **Kite is connected**, the terminal fetches actual expiry dates from
NFO instruments — holiday-adjusted dates are captured automatically.

### Lot Size & Strike Interval

Both are read from the **Kite NFO instruments CSV** when connected.
Shown in the sidebar and the info bar above each tab.

Current session: **{symbol}** · Lot {lot_size} · Interval ₹{si:.0f}

### Spot Price

* **🔄 Refresh Spot** calls Kite `/quote/ltp` — up to 1,000 instruments,
  very fast.  Recalculates GEX immediately with the new spot.
* **Auto** checkbox repeats this every {SPOT_REFRESH} s automatically.
* Full option chain refresh is separate (heavier, `/quote` endpoint).

### IV Calculation

Kite does not return Implied Volatility.  The terminal **back-solves IV
from each contract's LTP** using Brent's method on the Black-Scholes
formula — the standard approach used by professional terminals.

### GEX Regimes

**🟢 Positive Gamma** — Dealers sell rallies / buy dips → range-bound.
Prefer Iron Condors, Credit Spreads.

**🔴 Negative Gamma** — Dealers buy rallies / sell dips → trending.
Prefer Straddles, directional trades.

---
⚠️ Educational purposes only. Not financial advice. Trade at your own risk.
        """)

# ---------------------------------------------------------------------------
# Welcome screen
# ---------------------------------------------------------------------------
else:
    st.info("👈 Configure the terminal and click **📥 Fetch Option Chain** to begin.")
    st.markdown("""
## Welcome to Professional GEX Terminal 🚀

| Feature | Detail |
|---------|--------|
| Data sources | NSE Live · Kite Connect v3 · Sample |
| Spot refresh | `/quote/ltp` (lightweight, independent of chain) |
| Expiry dates | From Kite NFO instruments (holiday-aware) |
| Lot size      | From Kite NFO instruments (always current) |
| BANKNIFTY     | Monthly-only on NSE since Sept 2023 |
| IV            | Back-solved from LTP via Black-Scholes inverse |
    """)

    c1, c2 = st.columns(2)
    for col, sym, grad in [
        (c1, "NIFTY",     "linear-gradient(135deg,#667eea,#764ba2)"),
        (c2, "BANKNIFTY", "linear-gradient(135deg,#f093fb,#f5576c)"),
    ]:
        with col:
            with st.spinner(f"Loading {sym}..."):
                try:
                    q = get_index_quote(sym)
                    if q:
                        arrow = "🟢" if q["change"] >= 0 else "🔴"
                        label = "NIFTY 50" if sym == "NIFTY" else "BANK NIFTY"
                        st.markdown(f"""
<div style='background:{grad};padding:1.5rem;border-radius:12px;
            color:white;text-align:center;'>
  <h3 style='margin:0;color:white'>{label}</h3>
  <h1 style='margin:.5rem 0;color:white;font-size:2.4rem'>₹{q['last']:,.2f}</h1>
  <p style='margin:0;font-size:1.3rem'>{arrow} {q['change']:+.2f}%</p>
  <hr style='margin:.8rem 0;border-color:rgba(255,255,255,.3)'>
  <div style='display:flex;justify-content:space-around'>
    <div><small>Open</small><br><b>₹{q['open']:,.2f}</b></div>
    <div><small>High</small><br><b>₹{q['high']:,.2f}</b></div>
    <div><small>Low</small><br><b>₹{q['low']:,.2f}</b></div>
  </div>
</div>""", unsafe_allow_html=True)
                except Exception:
                    st.error(f"Could not load {sym}")

    try:
        mkt = get_market_status()
        st.caption(
            f"{'🟢' if 'Open' in mkt.get('market_state','') else '🔴'} "
            f"Market: {mkt['market_state']} | {mkt['timestamp']}"
        )
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("""
<div style='text-align:center;color:#888;padding:1rem'>
  <b>Professional GEX Terminal v3.0</b><br>
  Kite Connect v3 · /quote/ltp for spot · /quote for chain · NSE nselib<br>
  Lot sizes, strike intervals & expiry dates from Kite NFO instruments<br>
  <span style='font-size:.8rem'>
    ⚠️ Educational only. Not financial advice. Trade at your own risk.
  </span>
</div>
""", unsafe_allow_html=True)
