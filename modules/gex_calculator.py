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
