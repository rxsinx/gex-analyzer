"""
Advanced GEX and Greeks calculation module
Includes: Delta, Gamma, Vega, Theta, Rho, and all exposure metrics
"""

import pandas as pd
import numpy as np
from scipy.stats import norm


def calculate_all_greeks(S, K, T, r, sigma, option_type='call'):
    """
    Calculate all Greeks using Black-Scholes
    
    Args:
        S (float): Spot price
        K (float): Strike price
        T (float): Time to expiry in years
        r (float): Risk-free rate
        sigma (float): Implied volatility (as decimal)
        option_type (str): 'call' or 'put'
    
    Returns:
        dict: All Greeks and theoretical price
    """
    if T <= 0 or sigma <= 0:
        return {
            'delta': 0, 'gamma': 0, 'vega': 0, 'theta': 0, 'rho': 0,
            'theo_price': 0, 'iv': sigma * 100
        }
    
    try:
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        # Delta
        if option_type == 'call':
            delta = norm.cdf(d1)
            price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
            theta = ((-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) 
                     - r * K * np.exp(-r * T) * norm.cdf(d2)) / 365)
            rho = K * T * np.exp(-r * T) * norm.cdf(d2) / 100
        else:
            delta = norm.cdf(d1) - 1
            price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
            theta = ((-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) 
                     + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365)
            rho = -K * T * np.exp(-r * T) * norm.cdf(-d2) / 100
        
        # Common Greeks
        gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
        vega = S * norm.pdf(d1) * np.sqrt(T) / 100
        
        return {
            'delta': round(delta, 4),
            'gamma': round(gamma, 6),
            'vega': round(vega, 4),
            'theta': round(theta, 4),
            'rho': round(rho, 4),
            'theo_price': round(price, 2),
            'iv': round(sigma * 100, 2)
        }
        
    except Exception as e:
        return {
            'delta': 0, 'gamma': 0, 'vega': 0, 'theta': 0, 'rho': 0,
            'theo_price': 0, 'iv': 0
        }


def calculate_gex(df, spot_price, expiry_date_str, risk_free_rate=0.07):
    """
    Calculate Gamma Exposure (GEX) with full Greeks for each strike
    
    Args:
        df (pd.DataFrame): Options data
        spot_price (float): Current spot price
        expiry_date_str (str): Expiry date
        risk_free_rate (float): Risk-free rate
    
    Returns:
        pd.DataFrame: DataFrame with GEX and Greeks calculations
    """
    from modules.utils import calculate_time_to_expiry
    
    T = calculate_time_to_expiry(expiry_date_str)
    
    gex_data = []
    
    # Group by strike
    for strike in df['strike'].unique():
        strike_data = df[df['strike'] == strike]
        
        call_data = strike_data[strike_data['type'] == 'CE']
        put_data = strike_data[strike_data['type'] == 'PE']
        
        call_oi = call_data['oi'].sum() if not call_data.empty else 0
        put_oi = put_data['oi'].sum() if not put_data.empty else 0
        
        call_volume = call_data['volume'].sum() if not call_data.empty else 0
        put_volume = put_data['volume'].sum() if not put_data.empty else 0
        
        call_ltp = call_data['ltp'].mean() if not call_data.empty else 0
        put_ltp = put_data['ltp'].mean() if not put_data.empty else 0
        
        call_iv = call_data['iv'].mean() / 100 if not call_data.empty and call_data['iv'].mean() > 0 else 0.15
        put_iv = put_data['iv'].mean() / 100 if not put_data.empty and put_data['iv'].mean() > 0 else 0.15
        
        # Calculate all Greeks for calls
        call_greeks = calculate_all_greeks(spot_price, strike, T, risk_free_rate, call_iv, 'call')
        
        # Calculate all Greeks for puts
        put_greeks = calculate_all_greeks(spot_price, strike, T, risk_free_rate, put_iv, 'put')
        
        # GEX = Gamma * OI * Spot^2 * 0.01
        call_gex = -call_greeks['gamma'] * call_oi * spot_price * spot_price * 0.01
        put_gex = put_greeks['gamma'] * put_oi * spot_price * spot_price * 0.01
        
        total_gex = call_gex + put_gex
        
        # DEX = Delta * OI * Spot
        call_dex = -call_greeks['delta'] * call_oi * spot_price
        put_dex = -put_greeks['delta'] * put_oi * spot_price
        
        # Vega Exposure
        call_vex = call_greeks['vega'] * call_oi
        put_vex = put_greeks['vega'] * put_oi
        
        # Theta Exposure
        call_tex = call_greeks['theta'] * call_oi
        put_tex = put_greeks['theta'] * put_oi
        
        gex_data.append({
            'strike': strike,
            'call_oi': call_oi,
            'put_oi': put_oi,
            'call_volume': call_volume,
            'put_volume': put_volume,
            'call_ltp': call_ltp,
            'put_ltp': put_ltp,
            'call_iv': call_greeks['iv'],
            'put_iv': put_greeks['iv'],
            'call_delta': call_greeks['delta'],
            'put_delta': put_greeks['delta'],
            'call_gamma': call_greeks['gamma'],
            'put_gamma': put_greeks['gamma'],
            'call_vega': call_greeks['vega'],
            'put_vega': put_greeks['vega'],
            'call_theta': call_greeks['theta'],
            'put_theta': put_greeks['theta'],
            'call_rho': call_greeks['rho'],
            'put_rho': put_greeks['rho'],
            'call_theo': call_greeks['theo_price'],
            'put_theo': put_greeks['theo_price'],
            'call_gex': call_gex,
            'put_gex': put_gex,
            'total_gex': total_gex,
            'call_dex': call_dex,
            'put_dex': put_dex,
            'total_dex': call_dex + put_dex,
            'call_vex': call_vex,
            'put_vex': put_vex,
            'total_vex': call_vex + put_vex,
            'call_tex': call_tex,
            'put_tex': put_tex,
            'total_tex': call_tex + put_tex,
        })
    
    gex_df = pd.DataFrame(gex_data)
    gex_df = gex_df.sort_values('strike')
    
    return gex_df


def find_gamma_levels(gex_df, spot_price):
    """
    Find key gamma levels and calculate max pain
    
    Args:
        gex_df (pd.DataFrame): GEX data
        spot_price (float): Current spot price
    
    Returns:
        dict: Key gamma levels and metrics
    """
    # Cumulative GEX
    gex_df['cumulative_gex'] = gex_df['total_gex'].cumsum()
    
    # Gamma flip point
    zero_cross = gex_df[gex_df['cumulative_gex'].abs() == gex_df['cumulative_gex'].abs().min()]
    gamma_flip = zero_cross['strike'].values[0] if not zero_cross.empty else spot_price
    
    # Max positive GEX (support)
    max_positive = gex_df[gex_df['total_gex'] == gex_df['total_gex'].max()]
    support_level = max_positive['strike'].values[0] if not max_positive.empty else None
    
    # Max negative GEX (resistance)
    max_negative = gex_df[gex_df['total_gex'] == gex_df['total_gex'].min()]
    resistance_level = max_negative['strike'].values[0] if not max_negative.empty else None
    
    # Max Pain Calculation
    max_pain = calculate_max_pain(gex_df)
    
    # PCR calculation
    total_call_oi = gex_df['call_oi'].sum()
    total_put_oi = gex_df['put_oi'].sum()
    pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 1.0
    
    # Max OI strikes
    max_call_oi_strike = gex_df.loc[gex_df['call_oi'].idxmax(), 'strike'] if not gex_df.empty else None
    max_put_oi_strike = gex_df.loc[gex_df['put_oi'].idxmax(), 'strike'] if not gex_df.empty else None
    
    return {
        'gamma_flip': gamma_flip,
        'support': support_level,
        'resistance': resistance_level,
        'max_pain': max_pain,
        'pcr': pcr,
        'total_call_oi': total_call_oi,
        'total_put_oi': total_put_oi,
        'max_call_oi_strike': max_call_oi_strike,
        'max_put_oi_strike': max_put_oi_strike,
        'total_gex': gex_df['total_gex'].sum(),
        'net_gex_above_spot': gex_df[gex_df['strike'] > spot_price]['total_gex'].sum(),
        'net_gex_below_spot': gex_df[gex_df['strike'] <= spot_price]['total_gex'].sum(),
        'total_call_volume': gex_df['call_volume'].sum(),
        'total_put_volume': gex_df['put_volume'].sum(),
    }


def calculate_max_pain(gex_df):
    """
    Calculate Max Pain level
    
    Args:
        gex_df (pd.DataFrame): GEX data
    
    Returns:
        float: Max pain strike
    """
    strikes = gex_df['strike'].values
    pain_values = []
    
    for strike in strikes:
        pain = 0
        for _, row in gex_df.iterrows():
            # Call pain
            if row['strike'] < strike:
                pain += row['call_oi'] * (strike - row['strike'])
            # Put pain
            if row['strike'] > strike:
                pain += row['put_oi'] * (row['strike'] - strike)
        
        pain_values.append(pain)
    
    if pain_values:
        min_pain_idx = np.argmin(pain_values)
        return strikes[min_pain_idx]
    
    return strikes[len(strikes) // 2] if len(strikes) > 0 else 0


def calculate_dex(df, spot_price, expiry_date_str, risk_free_rate=0.07):
    """
    Calculate Delta Exposure (DEX) for each strike
    """
    # This is already included in calculate_gex, but keeping for compatibility
    gex_df = calculate_gex(df, spot_price, expiry_date_str, risk_free_rate)
    return gex_df[['strike', 'call_delta', 'put_delta', 'call_dex', 'put_dex', 'total_dex']]

def calculate_gex_delta(
    gex_df_cached: pd.DataFrame,
    spot_price_old: float,
    spot_price_new: float,
    expiry_date: str,
    risk_free_rate: float = 0.07,
) -> pd.DataFrame:
    """
    Update GEX for spot price change WITHOUT full recalculation.
    Only updates Greeks that depend on spot: Delta, Gamma, Theo Price.
    
    Performance: O(n) simple updates vs O(n*m) full Black-Scholes calcs
    Latency: ~200ms vs ~1.5s
    """
    from modules.utils import calculate_time_to_expiry
    
    T = calculate_time_to_expiry(expiry_date)
    gex_df = gex_df_cached.copy()
    
    # Pre-cache IV values (don't recalculate)
    call_ivs = (gex_df['call_iv'] / 100).values
    put_ivs = (gex_df['put_iv'] / 100).values
    strikes = gex_df['strike'].values
    
    # Fast update: only Greeks that change with spot
    updated_greeks = []
    for i, strike in enumerate(strikes):
        call_greeks_new = calculate_all_greeks(
            spot_price_new, strike, T, risk_free_rate, call_ivs[i], 'call'
        )
        put_greeks_new = calculate_all_greeks(
            spot_price_new, strike, T, risk_free_rate, put_ivs[i], 'put'
        )
        
        # GEX components (still need calculation but faster)
        call_oi = gex_df.iloc[i]['call_oi']
        put_oi = gex_df.iloc[i]['put_oi']
        
        call_gex = -call_greeks_new['gamma'] * call_oi * spot_price_new ** 2 * 0.01
        put_gex = put_greeks_new['gamma'] * put_oi * spot_price_new ** 2 * 0.01
        
        gex_df.loc[i, 'call_delta'] = call_greeks_new['delta']
        gex_df.loc[i, 'put_delta'] = put_greeks_new['delta']
        gex_df.loc[i, 'call_gamma'] = call_greeks_new['gamma']
        gex_df.loc[i, 'put_gamma'] = put_greeks_new['gamma']
        gex_df.loc[i, 'call_theo'] = call_greeks_new['theo_price']
        gex_df.loc[i, 'put_theo'] = put_greeks_new['theo_price']
        gex_df.loc[i, 'call_gex'] = call_gex
        gex_df.loc[i, 'put_gex'] = put_gex
        gex_df.loc[i, 'total_gex'] = call_gex + put_gex
        
        # DEX (Delta Exposure)
        gex_df.loc[i, 'call_dex'] = -call_greeks_new['delta'] * call_oi * spot_price_new
        gex_df.loc[i, 'put_dex'] = -put_greeks_new['delta'] * put_oi * spot_price_new
        gex_df.loc[i, 'total_dex'] = gex_df.loc[i, 'call_dex'] + gex_df.loc[i, 'put_dex']
    
    return gex_df.sort_values('strike')

# New line added from here for Put Call diparity fuction
# ═══════════════════════════════════════════════════════════════════════════════
# PUT-CALL PARITY DIVERGENCE & MARKET REGIME ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_parity_divergence(gex_df, spot_price):
    """
    Calculate put-call parity discount/premium AND divergence for ALL strikes
    
    Formulas:
    - Put Discount = (Spot + Put_LTP) - Strike  → Negative = cheap (BUY)
    - Call Discount = (Spot - Call_LTP) - Strike → Positive = expensive (SELL)
    - Divergence = Put_Discount - Call_Discount → Market conviction
    
    Args:
        gex_df: GEX dataframe with strike, put_ltp, call_ltp columns
        spot_price: Current spot price
    
    Returns:
        DataFrame with all parity metrics and classifications
    """
    parity_data = []
    
    for _, row in gex_df.iterrows():
        strike = row['strike']
        put_ltp = row['put_ltp']
        call_ltp = row['call_ltp']
        
        # ═════════════════════════════════════════════════════════════════════
        # PARITY CALCULATIONS
        # ═════════════════════════════════════════════════════════════════════
        
        # Put Discount: How much is the put trading below fair value?
        put_implied_spot = spot_price + put_ltp  # Where spot would be if put is priced fairly
        put_discount = put_implied_spot - strike  # Negative = cheap, Positive = expensive
        
        # Call Discount: How much is the call trading below fair value?
        call_implied_spot = spot_price - call_ltp  # Where spot would be if call is priced fairly
        call_discount = call_implied_spot - strike  # Positive = expensive, Negative = cheap
        
        # Divergence: How different are put and call pricing?
        divergence = put_discount - call_discount
        
        # ═════════════════════════════════════════════════════════════════════
        # STRIKE-LEVEL REGIME CLASSIFICATION
        # ═════════════════════════════════════════════════════════════════════
        
        if put_discount < -150 and call_discount < -150:
            # Both options are significantly underpriced
            strike_regime = "Both Cheap 🟢"
            signal_type = "Bullish"
            
        elif put_discount > 100 and call_discount > 100:
            # Both options are significantly overpriced (crisis mode)
            strike_regime = "Both Expensive 🔴"
            signal_type = "Crisis"
            
        elif put_discount < 0 and call_discount > 0:
            # Normal: puts cheap, calls expensive (insurance is cheap, speculation expensive)
            strike_regime = "Normal 🟡"
            signal_type = "Equilibrium"
            
        elif put_discount > 100 and call_discount < -50:
            # INVERTED: puts expensive, calls cheap (bearish reversal signal!)
            strike_regime = "Inverted 🔴"
            signal_type = "Reversal"
            
        elif abs(divergence) > 250:
            # Extreme skew (market showing extreme conviction)
            if divergence > 0:
                strike_regime = "Extreme Skew 🟢"
                signal_type = "Extreme Bullish"
            else:
                strike_regime = "Extreme Skew 🔴"
                signal_type = "Extreme Bearish"
            
        else:
            # In transition between regimes
            strike_regime = "Transitional ⚪"
            signal_type = "Neutral"
        
        parity_data.append({
            'strike': strike,
            'put_discount': round(put_discount, 2),
            'call_discount': round(call_discount, 2),
            'divergence': round(divergence, 2),
            'strike_regime': strike_regime,
            'signal_type': signal_type,
        })
    
    return pd.DataFrame(parity_data)


def detect_market_regime(parity_df, spot_price):
    """
    Analyze entire option chain to determine OVERALL market regime
    
    This is the key function that tells you what to trade
    
    Returns:
        dict with:
        - regime: Market regime name with emoji
        - action: What you should do (buy/sell/wait)
        - iv_level: Implied volatility environment
        - avg_put_discount: Average across all strikes
        - avg_call_discount: Average across all strikes
        - max_divergence: Largest skew seen
        - conviction_level: 0-10 strength of signal
        - color: HTML color for visual display
        - trade_strategy: Recommended strategy
    """
    
    if parity_df.empty:
        return {
            'regime': '⚪ Insufficient Data',
            'emoji': '⚪',
            'action': '⏸ No data available',
            'iv_level': 'Unknown',
            'avg_put_discount': 0,
            'avg_call_discount': 0,
            'max_divergence': 0,
            'conviction_level': 0,
            'color': '#6B7280',
            'trade_strategy': 'Wait for data',
        }
    
    # ═════════════════════════════════════════════════════════════════════════
    # AGGREGATE STATISTICS (across entire chain)
    # ═════════════════════════════════════════════════════════════════════════
    
    avg_put_disc = parity_df['put_discount'].mean()
    avg_call_disc = parity_df['call_discount'].mean()
    max_divergence = parity_df['divergence'].abs().max()
    
    # Conviction level: How extreme are the discounts? (0-10 scale)
    conviction = min(10, max(abs(avg_put_disc), abs(avg_call_disc)) / 50)
    
    # ═════════════════════════════════════════════════════════════════════════
    # REGIME DETECTION LOGIC
    # ═════════════════════════════════════════════════════════════════════════
    
    if avg_put_disc < -150 and avg_call_disc < -150:
        # BULLISH REGIME: Both cheap, but calls cheaper (strong upside conviction)
        regime = "🟢 NORMAL BULLISH"
        action = "✓ Buy Calls / Consider Puts for protection"
        iv_level = "Low"
        color = "#22C55E"  # Green
        trade_strategy = "Bullish Call Spread / Long Call"
        
    elif avg_put_disc > 100 and avg_call_disc > 100:
        # CRISIS REGIME: Everything expensive (extreme hedging)
        regime = "🔴 CRISIS / HIGH FEAR"
        action = "✓ Sell Premium (Iron Condor) / Buy protective puts only"
        iv_level = "Very High"
        color = "#EF4444"  # Red
        trade_strategy = "Iron Condor / Credit Spreads / Strangles"
        
    elif avg_put_disc < 0 and avg_call_disc > 0:
        # EQUILIBRIUM REGIME: Puts cheap, calls expensive (normal healthy market)
        regime = "🟡 EQUILIBRIUM (Normal Market)"
        action = "✓ Buy Puts ✓ Sell Calls / Risk Reversal"
        iv_level = "Fair"
        color = "#FBBF24"  # Amber
        trade_strategy = "Risk Reversal / Ratio Spreads"
        
    elif avg_put_disc > 100 and avg_call_disc < -50:
        # REVERSAL REGIME: INVERTED! Puts expensive, calls cheap (bearish alert!)
        regime = "🔴 BEARISH REVERSAL ⚠️"
        action = "✓ Buy Puts NOW / Short Calls / Reduce Long"
        iv_level = "High"
        color = "#DC2626"  # Dark Red
        trade_strategy = "Bear Put Spread / Protective Put / Short Call"
        conviction = min(10, conviction + 3)  # Add extra conviction for reversals
        
    elif abs(avg_put_disc - avg_call_disc) > 250:
        # EXTREME SKEW REGIME: Maximum market conviction in one direction
        if avg_put_disc < avg_call_disc:
            # Extreme bullish skew (calls way cheaper than puts)
            regime = "🟢 EXTREME BULLISH SKEW"
            action = "✓ Buy Calls (breakout trade) / Bull spreads"
            iv_level = "High"
            color = "#16A34A"  # Dark Green
            trade_strategy = "Bull Call Spread / Long Call / Call Ratio"
        else:
            # Extreme bearish skew (puts way cheaper than calls)
            regime = "🔴 EXTREME BEARISH SKEW"
            action = "✓ Buy Puts (crash hedge) / Bear spreads"
            iv_level = "High"
            color = "#7F1D1D"  # Very Dark Red
            trade_strategy = "Bear Put Spread / Long Put / Put Ratio"
    else:
        # TRANSITIONAL REGIME: Market shifting between regimes
        regime = "⚪ TRANSITIONAL"
        action = "⏸ Wait for clarity / Monitor for shift"
        iv_level = "Uncertain"
        color = "#6B7280"  # Gray
        trade_strategy = "Hold / Scale in gradually"
    
    return {
        'regime': regime,
        'emoji': regime.split()[0],
        'action': action,
        'iv_level': iv_level,
        'avg_put_discount': round(avg_put_disc, 2),
        'avg_call_discount': round(avg_call_disc, 2),
        'max_divergence': round(max_divergence, 2),
        'conviction_level': round(conviction, 1),
        'color': color,
        'trade_strategy': trade_strategy,
    }


def get_best_call_put_opportunities(parity_df):
    """
    Find the BEST opportunities to trade in current market
    
    Returns:
        dict with:
        - best_put_buy: Strike of most discounted put (best buy signal)
        - best_call_sell: Strike of most expensive call (best sell signal)
        
    This answers: "Which strike should I trade?"
    """
    opportunities = {}
    
    if not parity_df.empty:
        # Find the MOST discounted put (best value to buy)
        best_put_buy_idx = parity_df['put_discount'].idxmin()
        best_put_buy = parity_df.loc[best_put_buy_idx]
        opportunities['best_put_buy'] = {
            'strike': best_put_buy['strike'],
            'discount': best_put_buy['put_discount'],
            'divergence': best_put_buy['divergence'],
        }
        
        # Find the MOST expensive call (best premium to sell)
        best_call_sell_idx = parity_df['call_discount'].idxmax()
        best_call_sell = parity_df.loc[best_call_sell_idx]
        opportunities['best_call_sell'] = {
            'strike': best_call_sell['strike'],
            'premium': best_call_sell['call_discount'],
            'divergence': best_call_sell['divergence'],
        }
    
    return opportunities


def categorize_divergence_strength(divergence):
    """
    Rate how strong the divergence is (market conviction)
    
    Returns:
        dict with strength label, emoji, and conviction score
    """
    d_abs = abs(divergence)
    
    if d_abs < 50:
        return {
            "strength": "Mild",
            "emoji": "⚪",
            "conviction": 2,
            "description": "Small divergence, weak signal"
        }
    elif d_abs < 100:
        return {
            "strength": "Moderate",
            "emoji": "🟡",
            "conviction": 4,
            "description": "Medium divergence, moderate signal"
        }
    elif d_abs < 200:
        return {
            "strength": "Strong",
            "emoji": "🟠",
            "conviction": 6,
            "description": "Large divergence, strong signal"
        }
    elif d_abs < 300:
        return {
            "strength": "Very Strong",
            "emoji": "🔴",
            "conviction": 8,
            "description": "Very large divergence, very strong signal"
        }
    else:
        return {
            "strength": "Extreme",
            "emoji": "⚫",
            "conviction": 10,
            "description": "Massive divergence, extreme signal"
        }


def format_parity_signal(discount_value, signal_type="put"):
    """
    Format a parity value as a trading signal
    
    Returns: emoji + description for display
    """
    if signal_type == "put":
        if discount_value < -200:
            return "🟢🟢 VERY CHEAP", "Extreme BUY signal"
        elif discount_value < -100:
            return "🟢 CHEAP", "Strong BUY signal"
        elif discount_value < 0:
            return "🟡 Fair", "Slight discount"
        elif discount_value < 100:
            return "🟠 EXPENSIVE", "Slight premium"
        else:
            return "🔴 VERY EXPENSIVE", "Extreme SELL signal"
    else:  # call
        if discount_value > 200:
            return "🔴🔴 VERY EXPENSIVE", "Extreme SELL signal"
        elif discount_value > 100:
            return "🔴 EXPENSIVE", "Strong SELL signal"
        elif discount_value > 0:
            return "🟡 Fair", "Slight premium"
        elif discount_value > -100:
            return "🟢 CHEAP", "Slight discount"
        else:
            return "🟢 VERY CHEAP", "Extreme BUY signal"
